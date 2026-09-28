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
