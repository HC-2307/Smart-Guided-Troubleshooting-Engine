import itertools
import json
import logging
import os
import re
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Optional

from backend.config import settings
from backend.services.query_enrichment import DOMAIN_KEYWORDS
from backend.services.query_enrichment import _classify_domain as classify_domain
from backend.services.text_similarity import QueryFingerprint, facets_conflict, fingerprint, similarity

logger = logging.getLogger("m3")


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def domain_evidence(query: str) -> frozenset[str]:
    lowered = query.lower()
    return frozenset(
        domain for domain, keywords in DOMAIN_KEYWORDS.items()
        if any(re.search(r"\b" + re.escape(k) + r"\b", lowered) for k in keywords)
    )


def domains_compatible(evidence: frozenset[str], entry_domain: str) -> bool:
    return not evidence or entry_domain in evidence


@dataclass
class _Key:
    entry_id: int
    fp: QueryFingerprint
    is_variation: bool


@dataclass
class _Entry:
    response: dict
    domain: str
    expires_at: float
    exact_key: str
    query: str = ""
    variations: list[str] = field(default_factory=list)
    pinned: bool = False
    facets: dict = field(default_factory=dict)
    key_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class CacheLookup:
    response: Optional[dict]
    tier: Optional[str]
    score: float = 0.0
    matched_query: Optional[str] = None


class SemanticCache:
    def __init__(
        self,
        ttl_seconds: int = settings.cache_ttl_seconds,
        max_entries: int = settings.cache_max_entries,
        threshold: float = settings.semantic_threshold,
        variation_threshold: float = settings.variation_threshold,
        seed_variations: bool = settings.seed_variations,
        semantic_enabled: bool = settings.semantic_cache_enabled,
        domain_guard: bool = True,
        facet_guard: bool = True,
        domain_fn: Callable[[str], str] = classify_domain,
        clock: Callable[[], float] = time.time,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.threshold = threshold
        self.variation_threshold = variation_threshold
        self.seed_variations = seed_variations
        self.semantic_enabled = semantic_enabled
        self.domain_guard = domain_guard
        self.facet_guard = facet_guard
        self.domain_fn = domain_fn
        self.clock = clock
        self._lock = threading.RLock()
        self._ids = itertools.count()
        self.clear()

    def clear(self) -> None:
        with self._lock:
            self._entries: "OrderedDict[int, _Entry]" = OrderedDict()
            self._exact: dict[str, int] = {}
            self._keys: dict[int, _Key] = {}
            self._index: dict[str, set[int]] = {}
            self._counters: Counter = Counter()
            self.dirty = False

    def __len__(self) -> int:
        return len(self._entries)

    def lookup(self, query: str) -> CacheLookup:
        with self._lock:
            now = self.clock()
            entry_id = self._exact.get(_normalize(query))
            if entry_id is not None and self._alive(entry_id, now):
                return self._hit(entry_id, "exact", 1.0, query)

            if self.semantic_enabled and self._keys:
                found = self._semantic_match(query, now)
                if found is not None:
                    return self._hit(*found)

            self._counters["miss"] += 1
            return CacheLookup(None, None)

    def store(
        self,
        query: str,
        response: dict,
        variations: Optional[list[str]] = None,
        pinned: bool = False,
        expires_at: Optional[float] = None,
    ) -> None:
        with self._lock:
            exact_key = _normalize(query)
            if exact_key in self._exact:
                self._remove(self._exact[exact_key])

            origin = fingerprint(query)
            entry_id = next(self._ids)
            expiry = expires_at if expires_at is not None else self.clock() + self.ttl_seconds
            entry = _Entry(
                response, self.domain_fn(query), expiry, exact_key, query, list(variations or []), pinned,
                origin.facets,
            )
            self._entries[entry_id] = entry
            self._exact[exact_key] = entry_id

            keys = [(origin, False)]
            if self.seed_variations:
                seen = {exact_key}
                for v in variations or []:
                    if not v or _normalize(v) in seen:
                        continue
                    seen.add(_normalize(v))
                    fp = fingerprint(v)
                    if self.facet_guard and facets_conflict(origin.facets, fp.facets):
                        self._counters["variation_filtered"] += 1
                        continue
                    keys.append((fp, True))

            for fp, is_variation in keys:
                key_id = next(self._ids)
                self._keys[key_id] = _Key(entry_id, fp, is_variation)
                entry.key_ids.append(key_id)
                for token in fp.vector:
                    self._index.setdefault(token, set()).add(key_id)

            while len(self._entries) > self.max_entries:
                oldest = next((i for i, e in self._entries.items() if not e.pinned), None)
                if oldest is None:
                    break
                self._remove(oldest)
                self._counters["evicted"] += 1
            self.dirty = True

    def contains(self, query: str) -> bool:
        with self._lock:
            entry_id = self._exact.get(_normalize(query))
            return entry_id is not None and self._alive(entry_id, self.clock())

    def snapshot(self) -> list[dict]:
        with self._lock:
            now = self.clock()
            return [
                {"query": e.query, "response": e.response, "variations": e.variations,
                 "pinned": e.pinned, "expires_at": e.expires_at}
                for e in self._entries.values() if e.pinned or e.expires_at > now
            ]

    def save(self, path: str) -> int:
        records = self.snapshot()
        target = os.path.abspath(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp = f"{target}.tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "entries": records}, handle, ensure_ascii=False)
        os.replace(temp, target)
        with self._lock:
            self.dirty = False
        return len(records)

    def load(self, path: str) -> int:
        if not os.path.exists(path):
            return 0
        try:
            with open(path, encoding="utf-8") as handle:
                records = json.load(handle)["entries"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("cache file %s unreadable, starting empty: %r", path, exc)
            return 0
        now, loaded = self.clock(), 0
        for record in records:
            try:
                pinned = bool(record.get("pinned"))
                if not pinned and record["expires_at"] <= now:
                    continue
                self.store(record["query"], record["response"], record.get("variations"), pinned,
                           None if pinned else record["expires_at"])
                loaded += 1
            except (KeyError, TypeError, AttributeError) as exc:
                logger.warning("skipping bad cache record: %r", exc)
        with self._lock:
            self.dirty = False
        return loaded

    def stats(self) -> dict:
        with self._lock:
            hits = sum(self._counters[t] for t in ("exact", "semantic", "variation"))
            total = hits + self._counters["miss"]
            return {
                "entries": len(self._entries),
                "keys": len(self._keys),
                "hits": hits,
                "misses": self._counters["miss"],
                "hit_rate": round(hits / total, 4) if total else 0.0,
                "hits_by_tier": {t: self._counters[t] for t in ("exact", "semantic", "variation")},
                "guard_rejections": {
                    "domain": self._counters["reject_domain"],
                    "facet": self._counters["reject_facet"],
                },
                "pinned": sum(1 for e in self._entries.values() if e.pinned),
                "variations_filtered": self._counters["variation_filtered"],
                "evicted": self._counters["evicted"],
            }

    def _semantic_match(self, query: str, now: float):
        fp = fingerprint(query)
        evidence = domain_evidence(query) if self.domain_guard else frozenset()
        candidates = set().union(*(self._index.get(t, set()) for t in fp.vector)) if fp.vector else set()

        best = None
        rejected: set[str] = set()
        for key_id in candidates:
            key = self._keys[key_id]
            if not self._alive(key.entry_id, now):
                continue
            score = similarity(fp, key.fp)
            limit = self.variation_threshold if key.is_variation else self.threshold
            if score < limit or (best is not None and score <= best[2]):
                continue
            if self.domain_guard and not domains_compatible(evidence, self._entries[key.entry_id].domain):
                rejected.add("reject_domain")
                continue
            entry_facets = self._entries[key.entry_id].facets
            if self.facet_guard and (facets_conflict(fp.facets, key.fp.facets) or facets_conflict(fp.facets, entry_facets)):
                rejected.add("reject_facet")
                continue
            tier = "variation" if key.is_variation else "semantic"
            best = (key.entry_id, tier, score, key.fp.text)

        if best is None:
            for reason in rejected:
                self._counters[reason] += 1
        return best

    def _hit(self, entry_id: int, tier: str, score: float, matched: str) -> CacheLookup:
        self._entries.move_to_end(entry_id)
        self._counters[tier] += 1
        return CacheLookup(self._entries[entry_id].response, tier, round(score, 4), matched)

    def _alive(self, entry_id: int, now: float) -> bool:
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        if not entry.pinned and now > entry.expires_at:
            self._remove(entry_id)
            return False
        return True

    def _remove(self, entry_id: int) -> None:
        entry = self._entries.pop(entry_id, None)
        if entry is None:
            return
        if self._exact.get(entry.exact_key) == entry_id:
            del self._exact[entry.exact_key]
        for key_id in entry.key_ids:
            key = self._keys.pop(key_id, None)
            if key is None:
                continue
            for token in key.fp.vector:
                bucket = self._index.get(token)
                if bucket is not None:
                    bucket.discard(key_id)
                    if not bucket:
                        del self._index[token]


_default = SemanticCache()


def lookup(query: str) -> CacheLookup:
    return _default.lookup(query)


def store(query: str, response: dict, variations: Optional[list[str]] = None, pinned: bool = False) -> None:
    _default.store(query, response, variations, pinned)


def contains(query: str) -> bool:
    return _default.contains(query)


def save(path: str = "") -> int:
    return _default.save(path or settings.cache_persist_path)


def load(path: str = "") -> int:
    return _default.load(path or settings.cache_persist_path)


def is_dirty() -> bool:
    return _default.dirty


def get(query: str) -> Optional[dict]:
    return _default.lookup(query).response


def clear() -> None:
    _default.clear()


def stats() -> dict:
    return _default.stats()
