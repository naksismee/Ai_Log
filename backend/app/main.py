import os
import pathlib
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Any, Dict, List, Annotated, Optional
from collections import defaultdict
from datetime import datetime

from app.parser import parse_log_text
from app.cluster import cluster_messages
from app.summarize import summarize_clusters
from app.memory import KnownIssuesStore, match_known_issues, upsert_known_issues
from app.alerting import maybe_send_slack_alerts
from app.storage import AnalysisStore
from app.scheduler import analyze_file_path, start_scheduler
from app.vectordb import VectorStore, vector_id
from app.explain import explain_clusters

app = FastAPI(title="AI Log Analyzer", version="0.1.0")
known_issues = KnownIssuesStore()
analysis_store = AnalysisStore()
vector_store = VectorStore()
_scheduler = None

_static_dir = pathlib.Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    global _scheduler
    if os.getenv("ENABLE_SCHEDULER", "true").lower() in {"1", "true", "yes", "y"}:
        _scheduler = start_scheduler(known_issues=known_issues, store=analysis_store)


@app.get("/health")
def health() -> Dict[str, str]:
    demo = os.getenv('AI_LOG_ANALYZER_DEMO', '').lower() in {'1', 'true', 'yes'}
    return {"status": "ok", "mode": "demo" if demo else "semantic"}


@app.get('/sample-log')
def sample_log() -> FileResponse:
    sample = pathlib.Path(__file__).resolve().parents[2] / 'sample_logs' / 'recruiter.log'
    if not sample.is_file():
        raise HTTPException(status_code=404, detail='Sample log not found')
    return FileResponse(sample, media_type='text/plain', filename='recruiter.log')


@app.get("/")
def ui() -> FileResponse:
    index = _static_dir / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(str(index))


# =========================
# Timestamp-based trend analysis
# =========================
def extract_timestamp(log: str):
    try:
        return datetime.strptime(log[:19].replace('T', ' '), "%Y-%m-%d %H:%M:%S")
    except:
        return None


def analyze_trends(messages: List[str]):
    buckets = defaultdict(int)

    for log in messages:
        ts = extract_timestamp(log)
        if ts:
            key = ts.strftime("%Y-%m-%d %H:00")
            buckets[key] += 1

    return dict(buckets)


@app.post("/analyze-log")
async def analyze_log(
    file: Annotated[UploadFile, File(...)],
    background_tasks: BackgroundTasks,
    threshold: float = 0.80,
    model_name: str = "all-MiniLM-L6-v2",
    remember: bool = True,
    alert: bool = True,
) -> Dict[str, Any]:
    if threshold < 0.0 or threshold > 1.0:
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    text = content.decode("utf-8", errors="replace")

    entries = parse_log_text(text)
    if not entries:
        return {
            "filename": file.filename,
            "total_lines": len(text.splitlines()),
            "issues_found": 0,
            "clusters": [],
        }

    messages = [e.message for e in entries]

    # Keep timestamps available for trend buckets.
    trend_data = analyze_trends([entry.raw_log for entry in entries])

    try:
        clusters = cluster_messages(
            messages=messages,
            model_name=model_name,
            threshold=threshold,
            max_examples_per_cluster=5,
        )

        matches = match_known_issues(
            store=known_issues,
            clusters=clusters,
            model_name=model_name,
            threshold=max(0.75, threshold),
        )

        summaries = summarize_clusters(clusters)
        explanations = explain_clusters(clusters, source_name=file.filename)

        if remember:
            upsert_known_issues(
                store=known_issues,
                clusters=clusters,
                model_name=model_name,
            )

        if alert and background_tasks is not None:
            background_tasks.add_task(maybe_send_slack_alerts, clusters, file.filename)

        # vector DB
        try:
            vector_store.upsert_texts(
                model_name=model_name,
                ids=[vector_id("cluster", file.filename or "upload", c.cluster_id) for c in clusters],
                texts=[c.representative for c in clusters],
                metadatas=[
                    {
                        "kind": "cluster",
                        "source": file.filename or "upload",
                        "cluster_id": c.cluster_id,
                        "severity": c.severity,
                        "count": c.count,
                    }
                    for c in clusters
                ],
            )
        except Exception:
            pass

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Sort recurring clusters for the dashboard.
    sorted_clusters = sorted(clusters, key=lambda c: (c.count, c.severity == "HIGH"), reverse=True)

    result = {
        "filename": file.filename,
        "total_lines": len(text.splitlines()),
        "issues_found": len(entries),
        "threshold": threshold,
        "model_name": model_name,
        "summary": summaries.get("overall"),

        # Hourly issue counts.
        "trends": trend_data,

        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "severity": c.severity,
                "frequency": c.count,
                "count": c.count,
                "representative": c.representative,
                "examples": c.examples,
                "summary": summaries.get(c.cluster_id),
                "ai_explanation": explanations.get(c.cluster_id),
                "known_issue": matches.get(c.cluster_id),
            }
            for c in sorted_clusters
        ],
    }
    result['run_id'] = analysis_store.insert_run(
        source_name=file.filename,
        total_lines=result['total_lines'],
        issues_found=result['issues_found'],
        model_name=model_name,
        threshold=threshold,
        summary=result['summary'],
        clusters=result['clusters'],
    )
    return result


@app.post("/analyze-path")
def analyze_path(
    relative_path: str,
    threshold: float = 0.80,
    model_name: str = "all-MiniLM-L6-v2",
    remember: bool = True,
    alert: bool = True,
) -> Dict[str, Any]:

    watch_dir = os.getenv("LOG_WATCH_DIR", "../sample_logs")
    root = pathlib.Path(watch_dir).resolve()
    fp = (root / relative_path).resolve()

    if root not in fp.parents and fp != root:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    run_id = analyze_file_path(
        file_path=str(fp),
        threshold=threshold,
        model_name=model_name,
        known_issues=known_issues,
        store=analysis_store,
        remember=remember,
        alert=alert,
        source_name=str(fp.name),
    )

    return {"run_id": run_id}


@app.get("/recent-runs")
def recent_runs(limit: int = 25) -> Dict[str, Any]:
    return {"items": analysis_store.list_recent(limit=limit)}


@app.get("/runs/{run_id}")
def get_run(run_id: int) -> Dict[str, Any]:
    run = analysis_store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/semantic-search")
def semantic_search(
    q: str,
    k: int = 5,
    model_name: str = "all-MiniLM-L6-v2",
) -> Dict[str, Any]:
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")

    hits = vector_store.query(model_name=model_name, text=q, k=k)

    return {
        "available": vector_store.available(),
        "hits": [
            {
                "id": h.id,
                "score": h.score,
                "metadata": h.metadata,
                "document": h.document,
            }
            for h in hits
        ],
    }


@app.get("/known-issues")
def list_known_issues(limit: int = 100) -> Dict[str, Any]:
    return {"items": known_issues.list(limit=limit)}


@app.delete("/known-issues")
def clear_known_issues() -> Dict[str, str]:
    known_issues.clear()
    return {"status": "cleared"}
