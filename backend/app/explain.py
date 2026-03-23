from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from app.cluster import ClusterResult


def explain_clusters(
    clusters: List[ClusterResult],
    *,
    source_name: Optional[str] = None,
    max_clusters: int = 15,
) -> Dict[int, str]:
    """
    Returns per-cluster "AI Explanation" text.
    Uses an OpenAI-compatible endpoint if configured; otherwise uses heuristic explanations.
    """
    clusters = clusters[: max(0, int(max_clusters))]
    if not clusters:
        return {}

    endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    if api_key:
        try:
            return _explain_via_openai_compatible(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                clusters=clusters,
                source_name=source_name,
            )
        except Exception:
            # fall back to heuristic
            pass

    return {c.cluster_id: _heuristic_explain(c) for c in clusters}


def _explain_via_openai_compatible(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    clusters: List[ClusterResult],
    source_name: Optional[str],
) -> Dict[int, str]:
    prompt = _build_prompt(clusters, source_name=source_name)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior SRE helping explain production log clusters."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    obj = json.loads(raw)
    text = (
        obj.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return _parse_llm_response(text, clusters)


def _build_prompt(clusters: List[ClusterResult], *, source_name: Optional[str]) -> str:
    parts = []
    if source_name:
        parts.append(f"Source: {source_name}")
    parts.append(
        "For each cluster below, write an 'AI Explanation' and 'Possible causes' bullet list. "
        "Be concise and actionable. Output JSON: {cluster_id: \"...\"} with cluster_id as number keys."
    )
    for c in clusters:
        parts.append(
            f"\nCluster: {c.cluster_id}\n"
            f"Severity: {c.severity}\n"
            f"Occurrences: {c.count}\n"
            f"Representative: {c.representative}\n"
            f"Examples: {c.examples[:3]}\n"
        )
    return "\n".join(parts)


def _parse_llm_response(text: str, clusters: List[ClusterResult]) -> Dict[int, str]:
    # Try JSON first; otherwise fallback to heuristic.
    try:
        obj = json.loads(text)
        out: Dict[int, str] = {}
        for c in clusters:
            v = obj.get(str(c.cluster_id)) or obj.get(c.cluster_id)
            if isinstance(v, str) and v.strip():
                out[c.cluster_id] = v.strip()
        if len(out) == len(clusters):
            return out
    except Exception:
        pass
    return {c.cluster_id: _heuristic_explain(c) for c in clusters}


def _heuristic_explain(c: ClusterResult) -> str:
    msg = (c.representative or "").lower()
    causes: List[str] = []
    explanation = "The application is reporting this recurring issue."

    if any(k in msg for k in ["database", "postgres", "mysql", "sqlite", "connection", "timeout"]):
        explanation = "The application is failing to connect to the database or is timing out."
        causes = [
            "DB service unavailable or overloaded",
            "Incorrect connection string / credentials",
            "Network/DNS/firewall issue between app and DB",
            "Connection pool exhausted",
        ]
    elif any(k in msg for k in ["out of memory", "oom", "memory", "heap"]):
        explanation = "The process is running out of memory or experiencing high memory pressure."
        causes = [
            "Memory leak or unbounded cache growth",
            "Workload spike / large payloads",
            "Container limit too low",
        ]
    elif any(k in msg for k in ["permission", "unauthorized", "forbidden", "auth", "token", "jwt"]):
        explanation = "The request is failing due to authentication/authorization."
        causes = [
            "Expired/invalid token or credentials",
            "Role/permission misconfiguration",
            "Clock skew affecting token validation",
        ]
    elif any(k in msg for k in ["disk", "no space", "enospc", "io error"]):
        explanation = "The system is failing due to disk or I/O constraints."
        causes = [
            "Disk full / inode exhaustion",
            "Storage latency or transient I/O failures",
            "Log volume spike",
        ]
    elif any(k in msg for k in ["rate limit", "429", "throttle"]):
        explanation = "The service is being throttled or hitting rate limits."
        causes = [
            "Upstream rate limit reached",
            "Burst traffic without backoff",
            "Missing caching",
        ]
    elif any(k in msg for k in ["null", "none", "nil", "nullpointer", "attributeerror"]):
        explanation = "The application hit a null/None reference due to unexpected data flow."
        causes = [
            "Unexpected input / missing field",
            "Uninitialized object or race condition",
            "Backward-incompatible schema change",
        ]

    if not causes:
        # extract a couple of keywords as generic hints
        kws = [w for w in re.split(r"[^a-z0-9]+", msg) if len(w) >= 5][:4]
        if kws:
            causes = [f"Investigate related component: {', '.join(kws)}"]

    lines = [
        explanation,
        "Possible causes:",
        *[f"- {x}" for x in causes[:6]],
    ]
    return "\n".join(lines).strip()

