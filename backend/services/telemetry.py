import logging
import math
import os
import threading
import time
import uuid
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

from backend.config import settings

logger = logging.getLogger("m3")


@dataclass
class RequestTrace:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started: float = field(default_factory=time.perf_counter)
    stages_ms: dict[str, float] = field(default_factory=dict)
    cache_tier: str = "miss"
    cache_score: float = 0.0
    llm_calls: int = 0
    relevance: str = "skipped"
    validation: dict = field(default_factory=dict)
    fallback: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 3)

    @property
    def est_cost_usd(self) -> float:
        return round(self.llm_calls * settings.llm_cost_per_call_usd, 6)

    def headers(self) -> dict[str, str]:
        return {
            "X-Request-ID": self.request_id,
            "X-Cache": self.cache_tier,
            "X-Pipeline-Ms": f"{self.total_ms:.3f}",
            "X-LLM-Calls": str(self.llm_calls),
            "X-Relevance": self.relevance,
            "X-Est-Cost-USD": f"{self.est_cost_usd:.6f}",
        }


_current: ContextVar[Optional[RequestTrace]] = ContextVar("m3_trace", default=None)


def current() -> RequestTrace:
    trace = _current.get()
    if trace is None:
        trace = RequestTrace()
        _current.set(trace)
    return trace


def begin(request_id: Optional[str] = None) -> RequestTrace:
    trace = RequestTrace(request_id=request_id) if request_id else RequestTrace()
    _current.set(trace)
    return trace


def end() -> None:
    _current.set(None)


@contextmanager
def stage(name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        current().stages_ms[name] = round((time.perf_counter() - start) * 1000, 3)


def llm_provider_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(pct / 100 * len(ordered)) - 1))
    return round(ordered[index], 3)


class Metrics:
    def __init__(self, window: int = 2000):
        self._lock = threading.Lock()
        self._window = window
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self._latency = {"hit": deque(maxlen=self._window), "cold": deque(maxlen=self._window)}
            self._counters: Counter = Counter()
            self._codes: Counter = Counter()
            self._cost = 0.0

    def record(self, trace: RequestTrace) -> None:
        with self._lock:
            path = "cold" if trace.cache_tier == "miss" else "hit"
            self._latency[path].append(trace.total_ms)
            self._counters["requests"] += 1
            self._counters[f"cache_{trace.cache_tier}"] += 1
            self._counters["llm_calls"] += trace.llm_calls
            self._counters[f"relevance_{trace.relevance}"] += 1
            self._counters["errors"] += len(trace.errors)
            if trace.fallback:
                self._counters[f"fallback_{trace.fallback}"] += 1
            self._codes.update(trace.validation.get("codes", []))
            self._cost += trace.est_cost_usd

    def snapshot(self) -> dict:
        with self._lock:
            requests = self._counters["requests"]
            hits = requests - self._counters["cache_miss"]
            return {
                "requests": requests,
                "cache_hit_rate": round(hits / requests, 4) if requests else 0.0,
                "latency_ms": {
                    path: {"count": len(v), "p50": _percentile(list(v), 50), "p95": _percentile(list(v), 95)}
                    for path, v in self._latency.items()
                },
                "counters": dict(self._counters),
                "validation_codes": dict(self._codes),
                "est_cost_usd": round(self._cost, 6),
            }


metrics = Metrics()
