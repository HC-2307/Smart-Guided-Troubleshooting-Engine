import time
from typing import Optional

# Exact-string normalized cache for now. The graded target (>=80% hit rate on
# paraphrased queries) needs semantic keying (embedding similarity) instead of
# this normalization — tracked as a follow-up, not part of the basic skeleton.
_TTL_SECONDS = 3600
_store: dict[str, tuple[float, dict]] = {}


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def get(query: str) -> Optional[dict]:
    key = _normalize(query)
    entry = _store.get(key)
    if entry is None:
        return None

    expires_at, response = entry
    if time.time() > expires_at:
        del _store[key]
        return None

    return response


def set(query: str, response: dict) -> None:
    _store[_normalize(query)] = (time.time() + _TTL_SECONDS, response)
