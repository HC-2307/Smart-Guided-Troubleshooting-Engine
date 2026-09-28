import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import cache
from backend.services.relevance import is_device_query

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

OFF_TOPIC = [
    "what is the capital of france",
    "how do I cook pasta",
    "tell me a joke",
    "who won the world cup",
    "write me a poem about love",
    "who founded samsung",
    "hello",
    "what's the weather today",
    "explain quantum physics",
    "dark matter and space",
    "my cat is sick",
    "my car won't start",
    "the power went out in my house",
    "write python code to sort a list",
]

DEVICE = [
    "my internet is slow",
    "phone keeps restarting",
    "galaxy won't turn on",
    "how do i turn on dark mode",
    "my phone is broken",
    "can't hear callers",
    "my s24 freezes",
    "tab s9 wont charge",
    "batery drainng fast",
    "blutooth wont pair",
    "scren is flickring",
    "stuck in a boot loop",
]


def _benchmark_queries() -> list[str]:
    queries = [q.strip() for q in open(ROOT / "data" / "input.txt", encoding="utf-8") if q.strip()]
    paraphrases = json.loads((ROOT / "evaluation" / "m3_paraphrase_set.json").read_text(encoding="utf-8"))
    for intent in paraphrases["intents"]:
        queries += [intent["seed"], *intent["paraphrases"]]
    return queries


@pytest.mark.parametrize("query", OFF_TOPIC)
def test_off_topic_queries_are_rejected(query):
    assert not is_device_query(query)


@pytest.mark.parametrize("query", DEVICE)
def test_device_queries_are_accepted(query):
    assert is_device_query(query)


def test_every_official_and_paraphrase_query_is_accepted():
    blocked = [q for q in _benchmark_queries() if not is_device_query(q)]
    assert blocked == []


def test_strict_typo_repair_does_not_turn_common_words_into_device_terms():
    assert not is_device_query("it does not matter")


def test_api_returns_no_match_for_off_topic_query():
    cache.clear()
    response = client.post("/v1/troubleshoot", json={"query": "what is the capital of france"})
    assert response.status_code == 200
    assert response.json() == {"contexts": [], "query_variations": None, "fallback": "no_match"}
    assert response.headers["X-Cache"] == "miss"


def test_off_topic_query_is_not_served_from_cache():
    cache.clear()
    client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    response = client.post("/v1/troubleshoot", json={"query": "tell me a joke"})
    assert response.json()["fallback"] == "no_match"
    assert cache.stats()["entries"] == 1


def test_siis_reference_bypasses_the_gate():
    siis = json.loads((ROOT / "data" / "siis_responses.json").read_text(encoding="utf-8"))
    sample = siis["responses"][0]["siis_response"]
    response = client.post("/v1/troubleshoot", json={"query": "hello", "siis_response": sample})
    assert response.status_code == 200
    assert response.json()["contexts"]


def test_llm_rejects_query_the_keywords_would_accept(fake_llm):
    fake_llm["verdicts"]["my laptop battery drains fast"] = '{"relevant": false}'
    response = client.post("/v1/troubleshoot", json={"query": "my laptop battery drains fast"})
    assert response.json()["fallback"] == "no_match"
    assert response.headers["X-Relevance"] == "llm"
    assert response.headers["X-LLM-Calls"] == "1"


def test_llm_accepts_query_the_keywords_would_reject(fake_llm):
    query = "the thing I hold to call people is acting weird"
    assert not is_device_query(query)
    response = client.post("/v1/troubleshoot", json={"query": query})
    assert response.json()["fallback"] == "no_siis_context"
    assert response.headers["X-Relevance"] == "llm"

    battery = client.post("/v1/troubleshoot", json={"query": "the thing I charge every night dies by noon"})
    assert battery.json()["contexts"]
    assert battery.headers["X-Relevance"] == "llm"


def test_llm_failure_falls_back_to_keywords(fake_llm):
    fake_llm["error"] = TimeoutError("provider down")
    assert client.post("/v1/troubleshoot", json={"query": "tell me a joke"}).json()["fallback"] == "no_match"
    response = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    assert response.json()["contexts"]
    assert response.headers["X-Relevance"] in {"keywords", "semantic"}


def test_malformed_llm_verdict_falls_back_to_keywords(fake_llm):
    fake_llm["default"] = "sure, that looks fine"
    response = client.post("/v1/troubleshoot", json={"query": "what is the capital of france"})
    assert response.json()["fallback"] == "no_match"
    assert response.headers["X-Relevance"] in {"keywords", "semantic"}


def test_llm_verdict_is_memoized_per_query(fake_llm):
    fake_llm["default"] = '{"relevant": false}'
    for _ in range(3):
        client.post("/v1/troubleshoot", json={"query": "tell   me a joke"})
    assert fake_llm["calls"] == ["tell me a joke"]


def test_keyword_approved_cache_hit_skips_the_llm(fake_llm):
    client.post("/v1/troubleshoot", json={"query": "My phone battery drains really fast"})
    fake_llm["calls"].clear()
    response = client.post("/v1/troubleshoot", json={"query": "battery draining super quick on my galaxy"})
    assert response.headers["X-Cache"] != "miss"
    assert response.headers["X-Relevance"] in {"keywords", "semantic"}
    assert fake_llm["calls"] == []


def _reject_offline(monkeypatch):
    from backend.services import orchestrator, relevance

    monkeypatch.setattr(orchestrator, "offline_relevance", lambda query: (False, "semantic"))
    monkeypatch.setattr(relevance, "offline_relevance", lambda query: (False, "semantic"))


def test_cache_hit_rejected_offline_is_checked_by_the_llm(fake_llm, monkeypatch):
    client.post("/v1/troubleshoot", json={"query": "My phone battery drains really fast"})
    assert cache.lookup("my car battery drains really fast").response is not None
    _reject_offline(monkeypatch)
    fake_llm["verdicts"]["my car battery drains really fast"] = '{"relevant": false}'
    response = client.post("/v1/troubleshoot", json={"query": "my car battery drains really fast"})
    assert response.json()["fallback"] == "no_match"
    assert fake_llm["calls"][-1] == "my car battery drains really fast"


def test_cache_hit_rejected_offline_is_never_served_without_llm(monkeypatch):
    client.post("/v1/troubleshoot", json={"query": "My phone battery drains really fast"})
    assert cache.lookup("my car battery drains really fast").response is not None
    _reject_offline(monkeypatch)
    response = client.post("/v1/troubleshoot", json={"query": "my car battery drains really fast"})
    assert response.json()["fallback"] == "no_match"
    assert response.headers["X-Cache"] == "miss"


def test_strict_mode_checks_cache_hits_with_the_llm(fake_llm):
    fake_llm["strict"]()
    client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    fake_llm["verdicts"]["my laptop battery drains fast"] = '{"relevant": false}'
    assert cache.lookup("my laptop battery drains fast").response is not None
    response = client.post("/v1/troubleshoot", json={"query": "my laptop battery drains fast"})
    assert response.json()["fallback"] == "no_match"


def test_prompt_marks_user_text_as_data():
    from backend.services.relevance import _prompt

    assert "{user_query}" in _prompt()
    assert "not instructions" in _prompt()


def test_llm_client_fails_fast_without_retries(monkeypatch):
    import openai

    from backend.services import llm_guard, relevance, telemetry

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):
            seen["timeout"] = kwargs["timeout"]
            seen["reasoning_effort"] = kwargs.get("reasoning_effort")
            seen["extra_body"] = kwargs.get("extra_body")
            raise openai.APIConnectionError(request=None)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    telemetry.begin()
    with pytest.raises(openai.APIConnectionError):
        relevance._ask_llm("tell me a joke")
    assert seen["max_retries"] == 0
    assert 0 < seen["timeout"] <= relevance.settings.relevance_llm_timeout_seconds
    assert seen["reasoning_effort"] is None and seen["extra_body"] is None

    llm_guard.guard.reset()
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"chat_template_kwargs": {"enable_thinking": false}}')
    telemetry.begin()
    with pytest.raises(openai.APIConnectionError):
        relevance._ask_llm("tell me a joke")
    assert seen["reasoning_effort"] == "none"
    assert seen["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    telemetry.end()


def test_offline_semantic_check_separates_device_questions_from_lookalikes():
    from backend.services.relevance import semantic_relevant

    if semantic_relevant("my phone battery drains fast") is None:
        pytest.skip("embedding model not available offline")
    for query in ["mi fone batry drainin sooo fast!!!", "the thing I charge every night dies by noon", "switch to 12 hour clock"]:
        assert semantic_relevant(query), query
    for query in ["best wifi router to buy", "how to change my instagram password", "is bluetooth radiation harmful"]:
        assert not semantic_relevant(query), query


def test_offline_relevance_falls_back_to_word_lists_without_embeddings(monkeypatch):
    from backend.services import relevance

    monkeypatch.setattr(relevance, "semantic_relevant", lambda query: None)
    assert relevance.offline_relevance("my phone battery drains fast") == (True, "keywords")
    assert relevance.offline_relevance("tell me a joke") == (False, "keywords")


def test_confident_catalog_match_is_accepted_without_the_semantic_check(monkeypatch):
    from backend.services import relevance

    monkeypatch.setattr(relevance, "semantic_relevant", lambda query: pytest.fail("should not be consulted"))
    assert relevance.offline_relevance("switch the theme to dark")[0] or relevance.semantic_relevant is None
    assert relevance.offline_relevance("my phone time is in 24 hrs") == (True, "keywords")
