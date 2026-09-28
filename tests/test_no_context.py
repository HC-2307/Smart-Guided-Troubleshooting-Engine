import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import cache
from backend.services.query_enrichment import _classify_domain
from backend.services.query_processor import has_topic_evidence, process_query
from backend.services.troubleshooting_engine import find_matching_siis, load_siis_data

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _official() -> list[tuple[str, dict]]:
    return [(re.sub(r"^\s*\d+[.)]\s*", "", item["original_query"]).strip(), item["siis_response"]) for item in load_siis_data()]


def test_vague_device_complaint_without_reference_gets_no_siis_context():
    response = client.post("/v1/troubleshoot", json={"query": "my galaxy has a problem"})
    assert response.status_code == 200
    assert response.json() == {"contexts": [], "query_variations": None, "fallback": "no_siis_context"}
    assert response.headers["X-Planner"] == "none"


def test_no_siis_context_is_not_cached():
    client.post("/v1/troubleshoot", json={"query": "my galaxy has a problem"})
    assert cache.stats()["entries"] == 0


def test_complaint_with_topic_evidence_still_gets_a_plan():
    body = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"}).json()
    assert body["contexts"] and body["fallback"] is None


def test_siis_reference_bypasses_the_no_context_rule():
    _, siis = _official()[0]
    body = process_query("my galaxy has a problem", siis)
    assert body["contexts"]


@pytest.mark.parametrize("query", ["wify keeps disconecting", "storge is full", "no sond from speker", "my phone is overheatng"])
def test_typos_still_count_as_topic_evidence(query):
    assert has_topic_evidence(query)


@pytest.mark.parametrize("query", ["something is wrong", "it is weird", "my galaxy has a problem"])
def test_queries_without_a_topic_have_no_evidence(query):
    assert not has_topic_evidence(query)


def test_every_official_and_paraphrase_query_keeps_its_plan_path():
    queries = [q for q, _ in _official()]
    paraphrases = json.loads((ROOT / "evaluation" / "m3_paraphrase_set.json").read_text(encoding="utf-8"))
    queries += [q for it in paraphrases["intents"] for q in [it["seed"], *it["paraphrases"]]]
    refused = [q for q in queries if not has_topic_evidence(q) and find_matching_siis(q) is None]
    assert refused == []


def test_every_official_query_maps_to_its_own_reference_article():
    for query, siis in _official():
        assert find_matching_siis(query) is siis


@pytest.mark.parametrize("query", ["help", "my", "screen", "my cat is sick and I am sad", "tell me what to do with my phone"])
def test_short_or_unrelated_queries_do_not_borrow_a_reference_article(query):
    assert find_matching_siis(query) is None


def test_long_paraphrase_of_official_query_still_finds_its_article():
    found = find_matching_siis("My Galaxy S22 screen turns completely blank or white when I use apps")
    assert found is not None and "Blank or black display" in found["title"]


@pytest.mark.parametrize("query,domain", [
    ("change to light mode", "system"),
    ("my program keeps crashing", "performance"),
    ("Touch screen is laggy and slow to respond", "performance"),
    ("my phone is overheatng constantly", "battery"),
    ("screens keep flickering", "display"),
])
def test_domain_keywords_match_word_starts_not_word_fragments(query, domain):
    assert _classify_domain(query) == domain


@pytest.mark.parametrize("query", ["'; DROP TABLE users; --", "make everything bigger and simpler to use", "the drop was huge"])
def test_word_fragments_and_short_words_are_not_topic_evidence(query):
    assert not has_topic_evidence(query)


@pytest.mark.parametrize("query", ["change phone to light mode", "change to light mode"])
def test_known_words_are_not_typo_corrected_into_topic_words(query):
    assert not has_topic_evidence(query)
