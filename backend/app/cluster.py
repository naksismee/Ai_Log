from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np

from app.embedder import get_embedder


@dataclass
class ClusterResult:
    cluster_id: int
    count: int
    severity: str
    representative: str
    examples: List[str]


def _cosine_sim_matrix(X: np.ndarray) -> np.ndarray:
    # cosine similarity: (X·X) / (||X|| ||X||)
    X = X.astype(np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    Xn = X / norms
    return Xn @ Xn.T


def _severity_from_count(count: int) -> str:
    # simple heuristic (tweak later)
    if count >= 20:
        return "HIGH"
    if count >= 5:
        return "MEDIUM"
    return "LOW"


def cluster_messages(
    messages: List[str],
    model_name: str = "all-MiniLM-L6-v2",
    threshold: float = 0.80,
    max_examples_per_cluster: int = 5,
) -> List[ClusterResult]:
    """
    Greedy clustering:
    - embed all messages
    - compute cosine sim
    - iterate messages, assign to first cluster whose representative similarity >= threshold
    """
    if not messages:
        return []

    model = get_embedder(model_name)
    embeddings = model.encode(messages, normalize_embeddings=True)
    E = np.array(embeddings, dtype=np.float32)

    # representative index per cluster
    reps: List[int] = []
    clusters: List[List[int]] = []

    for i in range(len(messages)):
        if not reps:
            reps.append(i)
            clusters.append([i])
            continue

        # compare with cluster representatives
        rep_vecs = E[reps]  # (k, d)
        sims = rep_vecs @ E[i]  # because normalized
        best_k = int(np.argmax(sims))
        best_sim = float(sims[best_k])

        if best_sim >= threshold:
            clusters[best_k].append(i)
        else:
            reps.append(i)
            clusters.append([i])

    # build results sorted by frequency desc
    results: List[ClusterResult] = []
    for cid, idxs in enumerate(clusters, start=1):
        count = len(idxs)
        rep_msg = messages[reps[cid - 1]]
        # pick up to N example messages from this cluster
        examples = [messages[j] for j in idxs[:max_examples_per_cluster]]
        results.append(
            ClusterResult(
                cluster_id=cid,
                count=count,
                severity=_severity_from_count(count),
                representative=rep_msg,
                examples=examples,
            )
        )

    results.sort(key=lambda r: r.count, reverse=True)
    return results