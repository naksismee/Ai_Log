from __future__ import annotations

from functools import lru_cache
from typing import Any
import hashlib
import os
import re
import numpy as np


class DemoEmbedder:
    """Small deterministic keyword vectors for the download-free product demo.

    This is deliberately not presented as a transformer or semantic model.
    """
    def encode(self, messages, normalize_embeddings=True):
        if isinstance(messages, str):
            messages = [messages]
        vectors = np.zeros((len(messages), 256), dtype=np.float32)
        for row, message in enumerate(messages):
            for token in re.findall(r'[a-z]{2,}', message.lower()):
                digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
                vectors[row, int.from_bytes(digest, 'big') % 256] += 1
        if normalize_embeddings:
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
        return vectors


@lru_cache(maxsize=4)
def get_embedder(model_name: str) -> Any:
    if os.getenv('AI_LOG_ANALYZER_DEMO', '').lower() in {'1', 'true', 'yes'}:
        return DemoEmbedder()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(
            'Semantic mode needs sentence-transformers. Run python run.py, '
            'or use python run.py --demo for the download-free preview.'
        ) from error
    return SentenceTransformer(model_name)

