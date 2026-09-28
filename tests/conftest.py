import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CACHE_PERSIST_PATH"] = ""


@pytest.fixture(autouse=True)
def deterministic_pipeline(monkeypatch):
    if os.getenv("M3_TESTS_ALLOW_LLM") != "1":
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from backend.services import cache, llm_guard, relevance, telemetry
    relevance._llm_verdict.cache_clear()
    llm_guard.guard.reset()
    cache.clear()
    telemetry.metrics.reset()
    yield
    cache.clear()


@pytest.fixture
def fake_llm(monkeypatch):
    import re
    from dataclasses import replace

    from backend.services import llm_guard, orchestrator, query_enrichment, troubleshooting_engine

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(query_enrichment, "_call_llm_for_enrichment", lambda *a, **k: None)
    monkeypatch.setattr(troubleshooting_engine, "_call_llm_for_structure", lambda *a, **k: None)
    state = {"calls": [], "verdicts": {}, "default": '{"relevant": true}', "error": None}

    class Reply:
        def __init__(self, content):
            self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]

    class FakeClient:
        chat = property(lambda self: self)
        completions = property(lambda self: self)

        def create(self, **kwargs):
            text = kwargs["messages"][-1]["content"]
            found = re.search(r"<<<(.*)>>>", text, re.S)
            query = found.group(1).strip() if found else text
            state["calls"].append(query)
            if state["error"]:
                raise state["error"]
            return Reply(state["verdicts"].get(query, state["default"]))

    monkeypatch.setattr(llm_guard, "client", lambda timeout: FakeClient())
    state["strict"] = lambda: monkeypatch.setattr(
        orchestrator, "settings", replace(orchestrator.settings, relevance_llm_on_cache_hit=True)
    )
    return state
