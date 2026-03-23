from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional

from app.cluster import ClusterResult


def _post_json(url: str, payload: dict, timeout_s: int = 5) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as _resp:
        return


def maybe_send_slack_alerts(clusters: List[ClusterResult], source_name: Optional[str] = None) -> None:
    """
    Sends Slack webhook alerts for HIGH severity clusters if `SLACK_WEBHOOK_URL` is set.
    This is best-effort: failures are swallowed to avoid breaking analysis.
    """
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return

    highs = [c for c in clusters if c.severity == "HIGH"]
    if not highs:
        return

    title = "AI Log Analyzer alert"
    if source_name:
        title += f" ({source_name})"

    lines = [f"*{title}*"]
    for c in highs[:10]:
        rep = c.representative.replace("\n", " ").strip()
        if len(rep) > 180:
            rep = rep[:180] + "…"
        lines.append(f"- Cluster #{c.cluster_id}: {c.count} occurrences. `{rep}`")

    payload = {"text": "\n".join(lines)}
    try:
        _post_json(webhook, payload)
    except Exception:
        # Best-effort alerting only.
        return

