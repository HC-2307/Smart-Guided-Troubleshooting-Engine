import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from backend.config import settings
from backend.services import telemetry

logger = logging.getLogger("m3")


class LLMUnavailable(RuntimeError):
    pass


class LLMGuard:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.failures = 0
            self.open_until = 0.0
            self.trips = 0

    def is_open(self) -> bool:
        with self._lock:
            return self._clock() < self.open_until

    def remaining_budget(self) -> float:
        elapsed = (time.perf_counter() - telemetry.current().started)
        return settings.llm_request_budget_seconds - elapsed

    def allow(self) -> bool:
        return not self.is_open() and self.remaining_budget() >= settings.llm_min_call_seconds

    def timeout(self, cap: Optional[float] = None) -> float:
        limit = min(settings.llm_call_timeout_seconds, cap or settings.llm_call_timeout_seconds)
        return max(0.5, min(limit, self.remaining_budget()))

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= settings.llm_breaker_failures:
                self.open_until = self._clock() + settings.llm_breaker_cooldown_seconds
                self.failures = 0
                self.trips += 1
                logger.warning("llm circuit opened for %.0fs", settings.llm_breaker_cooldown_seconds)

    def state(self) -> dict:
        with self._lock:
            return {"open": self._clock() < self.open_until, "consecutive_failures": self.failures, "trips": self.trips}


guard = LLMGuard()


def request_options() -> dict[str, Any]:
    options: dict[str, Any] = {}
    effort = os.getenv("LLM_REASONING_EFFORT", "").strip()
    if effort:
        options["reasoning_effort"] = effort
    extra = os.getenv("LLM_EXTRA_BODY", "").strip()
    if extra:
        try:
            body = json.loads(extra)
            if isinstance(body, dict):
                options["extra_body"] = body
        except ValueError:
            logger.warning("LLM_EXTRA_BODY is not valid JSON, ignoring it")
    return options


def client(timeout: float):
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        max_retries=0,
        timeout=timeout,
    )


def chat_json(messages: list[dict], temperature: float, max_tokens: Optional[int] = None, cap: Optional[float] = None) -> str:
    if not guard.allow():
        raise LLMUnavailable("llm skipped: circuit open or request budget spent")
    timeout = guard.timeout(cap)
    telemetry.current().llm_calls += 1
    kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}, "temperature": temperature, "timeout": timeout}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    try:
        response = client(timeout).chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"), messages=messages, **kwargs, **request_options()
        )
    except Exception:
        guard.record_failure()
        raise
    guard.record_success()
    return response.choices[0].message.content or ""
