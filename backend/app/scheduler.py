from __future__ import annotations

import os
import pathlib
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app.alerting import maybe_send_slack_alerts
from app.cluster import cluster_messages
from app.memory import KnownIssuesStore, match_known_issues, upsert_known_issues
from app.parser import parse_log_text
from app.storage import AnalysisStore
from app.summarize import summarize_clusters
from app.vectordb import VectorStore, vector_id
from app.explain import explain_clusters



def _safe_join(root: str, relative: str) -> Optional[str]:
    try:
        root_path = pathlib.Path(root).resolve()
        p = (root_path / relative).resolve()
        if root_path not in p.parents and p != root_path:
            return None
        return str(p)
    except Exception:
        return None


def analyze_file_path(
    *,
    file_path: str,
    threshold: float,
    model_name: str,
    known_issues: KnownIssuesStore,
    store: AnalysisStore,
    remember: bool = True,
    alert: bool = True,
    source_name: Optional[str] = None,
) -> int:
    raw = pathlib.Path(file_path).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    entries = parse_log_text(text)
    messages = [e.message for e in entries]
    clusters = cluster_messages(messages=messages, model_name=model_name, threshold=threshold)
    matches = match_known_issues(store=known_issues, clusters=clusters, model_name=model_name, threshold=max(0.75, threshold))
    summaries = summarize_clusters(clusters)
    explanations = explain_clusters(clusters, source_name=source_name or os.path.basename(file_path))

    cluster_payload = [
        {
            "cluster_id": c.cluster_id,
            "severity": c.severity,
            "count": c.count,
            "representative": c.representative,
            "examples": c.examples,
            "summary": summaries.get(c.cluster_id),
            "ai_explanation": explanations.get(c.cluster_id),
            "known_issue": matches.get(c.cluster_id),
        }
        for c in clusters
    ]

    if remember:
        upsert_known_issues(store=known_issues, clusters=clusters, model_name=model_name)
    if alert:
        maybe_send_slack_alerts(clusters, source_name or os.path.basename(file_path))

    run_id = store.insert_run(
        source_name=source_name or os.path.basename(file_path),
        total_lines=len(text.splitlines()),
        issues_found=len(entries),
        model_name=model_name,
        threshold=threshold,
        summary=summaries.get("overall"),
        clusters=cluster_payload,
        analyzed_ts=int(time.time()),
    )

    # Upsert into vector DB for semantic search (best-effort).
    try:
        vs = VectorStore()
        vs.upsert_texts(
            model_name=model_name,
            ids=[vector_id("cluster", source_name or os.path.basename(file_path), c.cluster_id) for c in clusters],
            texts=[c.representative for c in clusters],
            metadatas=[
                {
                    "kind": "cluster",
                    "source": source_name or os.path.basename(file_path),
                    "cluster_id": c.cluster_id,
                    "severity": c.severity,
                    "count": c.count,
                    "run_id": run_id,
                }
                for c in clusters
            ],
        )
    except Exception:
        pass
    return run_id


def start_scheduler(
    *,
    known_issues: KnownIssuesStore,
    store: AnalysisStore,
) -> BackgroundScheduler:
    watch_dir = os.getenv("LOG_WATCH_DIR", "../sample_logs")
    interval_s = int(os.getenv("ANALYZE_INTERVAL_SECONDS", "60"))
    model_name = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
    threshold = float(os.getenv("CLUSTER_THRESHOLD", "0.80"))
    remember = os.getenv("REMEMBER_KNOWN_ISSUES", "true").lower() in {"1", "true", "yes", "y"}
    alert = os.getenv("ENABLE_ALERTS", "true").lower() in {"1", "true", "yes", "y"}

    def job() -> None:
        p = pathlib.Path(watch_dir)
        if not p.exists() or not p.is_dir():
            return
        # Pick the newest *.log file.
        candidates = sorted(p.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not candidates:
            return
        fp = str(candidates[0].resolve())
        analyze_file_path(
            file_path=fp,
            threshold=threshold,
            model_name=model_name,
            known_issues=known_issues,
            store=store,
            remember=remember,
            alert=alert,
            source_name=os.path.basename(fp),
        )

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(job, "interval", seconds=max(10, interval_s), id="log_analyzer_job", replace_existing=True)
    sched.start()
    return sched

