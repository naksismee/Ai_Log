from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


class AnalysisStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        base = os.getenv("AI_LOG_ANALYZER_DATA_DIR", "")
        if db_path is None:
            db_path = os.path.join(base, "analysis_runs.sqlite3") if base else "analysis_runs.sqlite3"
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT,
                    analyzed_ts INTEGER NOT NULL,
                    total_lines INTEGER NOT NULL,
                    issues_found INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    summary TEXT,
                    clusters_json TEXT NOT NULL
                );
                """
            )

    def insert_run(
        self,
        *,
        source_name: Optional[str],
        total_lines: int,
        issues_found: int,
        model_name: str,
        threshold: float,
        summary: Optional[str],
        clusters: List[Dict[str, Any]],
        analyzed_ts: Optional[int] = None,
    ) -> int:
        ts = int(analyzed_ts or time.time())
        payload = json.dumps(clusters, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO analysis_runs
                (source_name, analyzed_ts, total_lines, issues_found, model_name, threshold, summary, clusters_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    source_name,
                    ts,
                    int(total_lines),
                    int(issues_found),
                    str(model_name),
                    float(threshold),
                    summary,
                    payload,
                ),
            )
            return int(cur.lastrowid)

    def list_recent(self, limit: int = 25) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, source_name, analyzed_ts, total_lines, issues_found, model_name, threshold, summary
                FROM analysis_runs
                ORDER BY analyzed_ts DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT *
                FROM analysis_runs
                WHERE id = ?;
                """,
                (int(run_id),),
            )
            row = cur.fetchone()
        if row is None:
            return None
        out = dict(row)
        try:
            out["clusters"] = json.loads(out.pop("clusters_json") or "[]")
        except Exception:
            out["clusters"] = []
        return out

