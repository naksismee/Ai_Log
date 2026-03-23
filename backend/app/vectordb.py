from __future__ import annotations

import json
import os
import pathlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.embedder import get_embedder

try:
    import chromadb
    from chromadb.config import Settings
except Exception:  # pragma: no cover
    chromadb = None  # type: ignore
    Settings = None  # type: ignore


@dataclass(frozen=True)
class VectorHit:
    id: str
    score: float
    metadata: Dict[str, Any]
    document: Optional[str]


class VectorStore:
    """
    Minimal vector database wrapper.

    - Uses ChromaDB (persistent) when available
    - Falls back to an in-memory brute-force store otherwise
    """

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        base = os.getenv("AI_LOG_ANALYZER_DATA_DIR", "")
        if persist_dir is None:
            persist_dir = os.path.join(base, "chroma") if base else "chroma"
        self.persist_dir = str(pathlib.Path(persist_dir).resolve())
        self._mem: Dict[str, Tuple[np.ndarray, Dict[str, Any], Optional[str]]] = {}

        self._client = None
        self._col = None
        if chromadb is not None:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False) if Settings is not None else None,
            )
            self._col = self._client.get_or_create_collection(
                name="ai_log_analyzer",
                metadata={"hnsw:space": "cosine"},
            )

    def available(self) -> bool:
        return self._col is not None

    def upsert_texts(
        self,
        *,
        model_name: str,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if not ids:
            return
        model = get_embedder(model_name)
        emb = model.encode(texts, normalize_embeddings=True)
        E = np.array(emb, dtype=np.float32)

        if self._col is not None:
            self._col.upsert(
                ids=ids,
                documents=texts,
                embeddings=E.tolist(),
                metadatas=[_json_safe(m) for m in metadatas],
            )
            return

        for i, vid in enumerate(ids):
            self._mem[vid] = (E[i], dict(metadatas[i]), texts[i])

    def query(
        self,
        *,
        model_name: str,
        text: str,
        k: int = 5,
    ) -> List[VectorHit]:
        k = max(1, min(int(k), 50))
        model = get_embedder(model_name)
        q = np.array(model.encode([text], normalize_embeddings=True), dtype=np.float32)[0]

        if self._col is not None:
            res = self._col.query(
                query_embeddings=[q.tolist()],
                n_results=k,
                include=["metadatas", "documents", "distances"],
            )
            hits: List[VectorHit] = []
            ids = res.get("ids", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            docs = res.get("documents", [[]])[0]
            dists = res.get("distances", [[]])[0]  # cosine distance
            for vid, meta, doc, dist in zip(ids, metas, docs, dists):
                score = float(1.0 - float(dist))
                hits.append(VectorHit(id=str(vid), score=score, metadata=dict(meta or {}), document=doc))
            return hits

        if not self._mem:
            return []
        ids: List[str] = []
        M: List[np.ndarray] = []
        for vid, (e, _m, _d) in self._mem.items():
            ids.append(vid)
            M.append(e)
        K = np.stack(M, axis=0).astype(np.float32)
        q = q / (np.linalg.norm(q) + 1e-12)
        K = K / (np.linalg.norm(K, axis=1, keepdims=True) + 1e-12)
        sims = K @ q
        order = np.argsort(-sims)[:k]
        hits = []
        for idx in order:
            vid = ids[int(idx)]
            e, meta, doc = self._mem[vid]
            hits.append(VectorHit(id=vid, score=float(sims[int(idx)]), metadata=dict(meta), document=doc))
        return hits


def _json_safe(d: Dict[str, Any]) -> Dict[str, Any]:
    # Chroma requires JSON-serializable metadata.
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[str(k)] = v
        else:
            out[str(k)] = json.dumps(v, ensure_ascii=False)
    return out


def vector_id(kind: str, source: str, cluster_id: int) -> str:
    # stable-ish id for upserts; include source in case multiple logs share cluster ids
    return f"{kind}:{source}:{cluster_id}"

