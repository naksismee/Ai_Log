from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from app.embedder import get_embedder

from app.cluster import ClusterResult


@dataclass(frozen=True)
class KnownIssueMatch:
    issue_id: int
    score: float
    representative: str
    occurrences: int
    last_seen_ts: int


class KnownIssuesStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        base = os.getenv("AI_LOG_ANALYZER_DATA_DIR", "")
        if db_path is None:
            db_path = os.path.join(base, "known_issues.sqlite3") if base else "known_issues.sqlite3"
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS known_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    representative TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    first_seen_ts INTEGER NOT NULL,
                    last_seen_ts INTEGER NOT NULL
                );
                """
            )

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, representative, occurrences, first_seen_ts, last_seen_ts
                FROM known_issues
                ORDER BY last_seen_ts DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {
                "id": rid,
                "representative": rep,
                "occurrences": occ,
                "first_seen_ts": fst,
                "last_seen_ts": lst,
            }
            for (rid, rep, occ, fst, lst) in rows
        ]

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM known_issues;")

    def fetch_all_embeddings(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, representative, embedding_json, occurrences, last_seen_ts
                FROM known_issues;
                """
            )
            rows = cur.fetchall()
        items: List[Dict[str, Any]] = []
        for rid, rep, emb_json, occ, last_seen_ts in rows:
            try:
                emb = np.array(json.loads(emb_json), dtype=np.float32)
            except Exception:
                continue
            items.append(
                {
                    "id": int(rid),
                    "representative": str(rep),
                    "embedding": emb,
                    "occurrences": int(occ),
                    "last_seen_ts": int(last_seen_ts),
                }
            )
        return items

    def upsert(self, representative: str, embedding: np.ndarray, add_occurrences: int) -> None:
        now = int(time.time())
        embedding_json = json.dumps([float(x) for x in embedding.astype(np.float32).tolist()])
        with self._connect() as conn:
            # Find best exact match by representative text first (cheap + deterministic).
            cur = conn.execute(
                "SELECT id, occurrences, first_seen_ts FROM known_issues WHERE representative = ?;",
                (representative,),
            )
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO known_issues (representative, embedding_json, occurrences, first_seen_ts, last_seen_ts)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (representative, embedding_json, int(add_occurrences), now, now),
                )
            else:
                rid, occ, fst = row
                conn.execute(
                    """
                    UPDATE known_issues
                    SET embedding_json = ?, occurrences = ?, first_seen_ts = ?, last_seen_ts = ?
                    WHERE id = ?;
                    """,
                    (
                        embedding_json,
                        int(occ) + int(add_occurrences),
                        int(fst),
                        now,
                        int(rid),
                    ),
                )


def _get_model(model_name: str) -> Any:
    return get_embedder(model_name)


def match_known_issues(
    store: KnownIssuesStore,
    clusters: List[ClusterResult],
    model_name: str,
    threshold: float = 0.80,
) -> Dict[int, Optional[Dict[str, Any]]]:
    if not clusters:
        return {}
    threshold = float(threshold)

    known = store.fetch_all_embeddings()
    if not known:
        return {c.cluster_id: None for c in clusters}

    model = _get_model(model_name)
    reps = [c.representative for c in clusters]
    emb = model.encode(reps, normalize_embeddings=True)
    Q = np.array(emb, dtype=np.float32)

    K = np.stack([item["embedding"] for item in known], axis=0).astype(np.float32)
    # embeddings were stored already normalized (we store normalized reps); but normalize again defensively
    Q = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
    K = K / (np.linalg.norm(K, axis=1, keepdims=True) + 1e-12)

    sims = Q @ K.T  # (n_clusters, n_known)
    out: Dict[int, Optional[Dict[str, Any]]] = {}
    for i, c in enumerate(clusters):
        j = int(np.argmax(sims[i]))
        score = float(sims[i, j])
        if score >= threshold:
            item = known[j]
            out[c.cluster_id] = {
                "issue_id": item["id"],
                "score": score,
                "representative": item["representative"],
                "occurrences": item["occurrences"],
                "last_seen_ts": item["last_seen_ts"],
            }
        else:
            out[c.cluster_id] = None
    return out


def upsert_known_issues(
    store: KnownIssuesStore,
    clusters: List[ClusterResult],
    model_name: str,
) -> None:
    if not clusters:
        return
    model = _get_model(model_name)
    reps = [c.representative for c in clusters]
    emb = model.encode(reps, normalize_embeddings=True)
    E = np.array(emb, dtype=np.float32)
    for i, c in enumerate(clusters):
        store.upsert(representative=c.representative, embedding=E[i], add_occurrences=c.count)

