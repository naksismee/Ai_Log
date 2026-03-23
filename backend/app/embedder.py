from __future__ import annotations

from functools import lru_cache
from typing import Any

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore


@lru_cache(maxsize=4)
def get_embedder(model_name: str) -> Any:
    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )
    return SentenceTransformer(model_name)

