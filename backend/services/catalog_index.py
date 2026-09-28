import hashlib
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from backend.config import settings

logger = logging.getLogger("m3")

Encoder = Callable[[list[str]], np.ndarray]


class DenseIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._encoder: Optional[Encoder] = None
        self._entries: list[dict] = []
        self._matrix: Optional[np.ndarray] = None
        self.status = "not_loaded"

    def _load_encoder(self) -> Encoder:
        from fastembed import TextEmbedding

        model = TextEmbedding(settings.embedding_model, cache_dir=str(settings.embedding_cache_dir))
        return lambda texts: np.asarray(list(model.embed(texts)), dtype=np.float32)

    def _vectors_path(self, texts: list[str]) -> Path:
        digest = hashlib.sha256("\n".join([settings.embedding_model, *texts]).encode("utf-8")).hexdigest()[:16]
        return Path(settings.embedding_cache_dir) / f"catalog_vectors_{digest}.npy"

    def _catalog_matrix(self, texts: list[str], persist: bool) -> np.ndarray:
        path = self._vectors_path(texts)
        if persist and path.exists():
            matrix = np.load(path)
            if matrix.shape[0] == len(texts):
                return matrix
        matrix = _normalize(self._encoder(texts))
        if persist:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, matrix)
        return matrix

    def build(self, entries: list[dict], texts: list[str], encoder: Optional[Encoder] = None) -> bool:
        with self._lock:
            if not settings.embeddings_enabled:
                self.status = "disabled"
                return False
            try:
                self._encoder = encoder or self._load_encoder()
                self._matrix = self._catalog_matrix(texts, persist=encoder is None)
                self._entries = list(entries)
                self.status = "ready"
                return True
            except Exception as exc:
                self._encoder, self._matrix, self._entries = None, None, []
                self.status = "unavailable"
                logger.warning("dense catalog index unavailable, using keyword matching only: %r", exc)
                return False

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def search(self, query: str, k: int = 10) -> list[tuple[float, dict]]:
        if not self.ready or not query.strip():
            return []
        try:
            vector = _normalize(self._encoder([query]))[0]
        except Exception as exc:
            logger.warning("dense query encoding failed, using keyword matching only: %r", exc)
            return []
        scores = self._matrix @ vector
        order = np.argsort(-scores)[:k]
        return [(float(scores[i]), self._entries[i]) for i in order]

    def reset(self) -> None:
        with self._lock:
            self._encoder, self._matrix, self._entries = None, None, []
            self.status = "not_loaded"


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.atleast_2d(np.asarray(matrix, dtype=np.float32))
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


dense_index = DenseIndex()
