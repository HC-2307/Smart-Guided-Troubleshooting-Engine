import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import llm_guard, telemetry
from backend.services.llm_guard import LLMGuard, LLMUnavailable, chat_json, request_options

client = TestClient(app)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_breaker_opens_after_consecutive_failures_and_recovers_after_cooldown():
    clock = Clock()
    guard = LLMGuard(clock=clock)
    telemetry.begin()
    guard.record_failure()
    assert guard.allow()
    guard.record_failure()
    assert not guard.allow()
    assert guard.state()["trips"] == 1
    clock.now += llm_guard.settings.llm_breaker_cooldown_seconds + 1
    assert guard.allow()


def test_success_resets_the_failure_count():
    guard = LLMGuard(clock=Clock())
    telemetry.begin()
    guard.record_failure()
    guard.record_success()
    guard.record_failure()
    assert guard.allow()


def test_spent_request_budget_blocks_further_calls():
    guard = LLMGuard(clock=Clock())
    trace = telemetry.begin()
    trace.started -= llm_guard.settings.llm_request_budget_seconds
    assert not guard.allow()


def test_call_timeout_shrinks_to_the_remaining_budget():
    guard = LLMGuard(clock=Clock())
    trace = telemetry.begin()
    trace.started -= llm_guard.settings.llm_request_budget_seconds - 2.0
    assert guard.timeout() == pytest.approx(2.0, abs=0.1)


def test_chat_json_does_not_call_or_count_when_the_breaker_is_open(monkeypatch):
    monkeypatch.setattr(llm_guard, "client", lambda timeout: pytest.fail("provider must not be called"))
    llm_guard.guard.open_until = time.monotonic() + 60
    trace = telemetry.begin()
    with pytest.raises(LLMUnavailable):
        chat_json([{"role": "user", "content": "hi"}], temperature=0)
    assert trace.llm_calls == 0


def test_invalid_extra_body_is_ignored(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", "{not json")
    assert "extra_body" not in request_options()


def _failing_provider(monkeypatch, error=TimeoutError("provider timed out")):
    calls = {"n": 0}

    class Failing:
        chat = property(lambda self: self)
        completions = property(lambda self: self)

        def create(self, **kwargs):
            calls["n"] += 1
            raise error

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_guard, "client", lambda timeout: Failing())
    return calls


def test_failing_provider_opens_breaker_and_next_request_skips_the_llm(monkeypatch):
    calls = _failing_provider(monkeypatch)
    first = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    assert first.status_code == 200 and first.json()["contexts"]
    assert llm_guard.guard.state()["open"]
    attempted = calls["n"]

    second = client.post("/v1/troubleshoot", json={"query": "my screen keeps flickering"})
    assert second.status_code == 200 and second.json()["contexts"]
    assert calls["n"] == attempted
    assert second.headers["X-LLM-Calls"] == "0"
    assert second.headers["X-Relevance"] in {"keywords", "semantic"}


def test_slow_provider_is_cut_off_by_the_request_budget(monkeypatch):
    patched = replace(llm_guard.settings, llm_request_budget_seconds=0.6, llm_min_call_seconds=0.2,
                      llm_breaker_failures=100)
    monkeypatch.setattr(llm_guard, "settings", patched)
    calls = {"n": 0}

    class Slow:
        chat = property(lambda self: self)
        completions = property(lambda self: self)

        def create(self, **kwargs):
            calls["n"] += 1
            time.sleep(0.3)
            raise TimeoutError("slow")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_guard, "client", lambda timeout: Slow())
    started = time.perf_counter()
    response = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    elapsed = time.perf_counter() - started
    assert response.json()["contexts"]
    assert calls["n"] <= 2
    assert elapsed < 1.5


def test_metrics_report_breaker_state(monkeypatch):
    _failing_provider(monkeypatch)
    client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    assert client.get("/v1/metrics").json()["llm_guard"]["open"] is True
