from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from app.cluster import ClusterResult


def _keywords(texts: List[str], k: int = 6) -> List[str]:
    # Very lightweight keyword extraction (no extra deps).
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "at",
        "from",
        "as",
        "it",
        "this",
        "that",
        "failed",
        "error",
        "warning",
    }
    tokens: List[str] = []
    for t in texts:
        for raw in t.replace("/", " ").replace("_", " ").split():
            w = "".join(ch for ch in raw.lower() if ch.isalnum())
            if len(w) < 4:
                continue
            if w in stop:
                continue
            tokens.append(w)
    counts = Counter(tokens)
    return [w for (w, _c) in counts.most_common(k)]


def summarize_clusters(clusters: List[ClusterResult]) -> Dict[object, str]:
    """
    Returns:
      - key "overall": overall summary string
      - key cluster_id (int): per-cluster summary string
    """
    if not clusters:
        return {"overall": "No ERROR/WARNING lines detected."}

    total = sum(c.count for c in clusters)
    high = [c for c in clusters if c.severity == "HIGH"]
    top = clusters[:3]

    overall = (
        f"Found {total} issue lines grouped into {len(clusters)} clusters. "
        f"Top clusters: "
        + "; ".join(f"#{c.cluster_id} ({c.count}, {c.severity})" for c in top)
        + (f". High severity clusters: {', '.join('#'+str(c.cluster_id) for c in high)}" if high else ".")
    )

    out: Dict[object, str] = {"overall": overall}
    for c in clusters:
        kws = _keywords([c.representative] + c.examples, k=6)
        kw_part = f" Keywords: {', '.join(kws)}." if kws else ""
        out[c.cluster_id] = (
            f"{c.severity} severity. {c.count} occurrences. "
            f"Representative: {c.representative[:220].strip()}"
            + ("…" if len(c.representative) > 220 else "")
            + "."
            + kw_part
        )
    return out

