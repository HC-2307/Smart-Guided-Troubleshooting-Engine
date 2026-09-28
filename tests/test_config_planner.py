import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import cache, relevance
from backend.services.config_planner import build_plan, match
from backend.services.contract_validator import catalog_by_deeplink, validate_and_repair

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

SETTINGS_QUERIES = {
    "my phone time is in 24 hrs": ("bixby://masked/act/aa73a35e8d", "Switch Time Format"),
    "time setting is in 24 hrs": ("bixby://masked/act/aa73a35e8d", "Switch Time Format"),
    "how do I turn on dark mode": (None, "Adjust Dark mode settings"),
    "change my ringtone": (None, "Adjust Ringtone"),
    "turn on bluetooth": (None, "Enable Bluetooth"),
    "turn off bluetooth": (None, "Disable Bluetooth"),
    "turn off automatic date and time": ("bixby://masked/act/29c1d16f6b", "Disable Auto Time"),
    "turn on always on display": (None, "Enable Always On Display"),
    "turn off always on display": (None, "Disable Always On Display"),
    "enable mouse keys": ("bixby://masked/act/49ebf67303", "Enable Mouse Keys"),
    "show battery percentage": (None, "Check Battery Performance"),
    "increase screen timeout": (None, "Adjust Timeout"),
}

OFF_TOPIC = [
    "what is the capital of france", "who founded samsung", "what time is it", "what time is it in london",
    "dark chocolate recipe", "turn on the lights", "capital letters in english grammar", "tell me a joke",
]


def _troubleshooting_queries() -> list[str]:
    queries = [q.strip() for q in open(ROOT / "data" / "input.txt", encoding="utf-8") if q.strip()]
    paraphrases = json.loads((ROOT / "evaluation" / "m3_paraphrase_set.json").read_text(encoding="utf-8"))
    for intent in paraphrases["intents"]:
        queries += [intent["seed"], *intent["paraphrases"]]
    return queries


@pytest.mark.parametrize("query,expected", SETTINGS_QUERIES.items())
def test_settings_query_matches_expected_catalog_entry(query, expected):
    deeplink, message = expected
    found = match(query)
    assert found is not None
    assert found.entry["message"] == message
    if deeplink:
        assert found.entry["deeplink"] == deeplink


@pytest.mark.parametrize("query", SETTINGS_QUERIES)
def test_settings_plan_passes_contract_with_zero_repairs(query):
    repaired, report = validate_and_repair(build_plan(query))
    assert report.summary()["repaired"] == 0 and report.summary()["quarantined"] == 0
    goal = repaired["contexts"][0]
    assert goal["goal"].endswith(" Configuration")
    assert 8 <= len(repaired["query_variations"]) <= 10


@pytest.mark.parametrize("query", SETTINGS_QUERIES)
def test_settings_plan_copies_catalog_entry_verbatim(query):
    plan = build_plan(query)
    group = plan["contexts"][0]["actions"][0]["stepGroups"][0]
    entry = catalog_by_deeplink()[group["actionableDeeplink"]["deeplink"]]
    for field in ("description", "message", "originalType"):
        assert group["actionableDeeplink"][field] == entry[field]
    assert group["validationDeeplink"] == entry.get("validation")


def test_time_format_plan_is_built_from_catalog_text():
    action = build_plan("my phone time is in 24 hrs")["contexts"][0]["actions"][0]
    assert action["category"] == "auto"
    assert action["stepGroups"][0]["steps"] == ["Open the 24-hour time format settings page.", "Tap Use 24-hour format."]


def test_toggle_direction_follows_the_query():
    assert build_plan("turn on bluetooth")["contexts"][0]["actions"][0]["stepGroups"][0]["steps"] == ["Turn on Bluetooth."]
    assert build_plan("turn off bluetooth")["contexts"][0]["actions"][0]["stepGroups"][0]["steps"] == ["Turn off Bluetooth."]


def test_troubleshooting_queries_are_left_to_m1():
    claimed = [q for q in _troubleshooting_queries() if match(q) is not None]
    assert claimed == []


@pytest.mark.parametrize("query", OFF_TOPIC)
def test_off_topic_queries_get_no_settings_plan(query):
    assert match(query) is None


@pytest.mark.parametrize("query", ["phone is not charging", "bluetooth keeps disconnecting", "dark mode won't turn on"])
def test_fault_reports_are_not_treated_as_settings_requests(query):
    assert match(query) is None


def test_api_serves_settings_plan_from_catalog():
    response = client.post("/v1/troubleshoot", json={"query": "my phone time is in 24 hrs"})
    body = response.json()
    assert response.headers["X-Planner"] == "catalog"
    assert response.headers["X-Relevance"] == "keywords"
    assert body["fallback"] is None
    assert body["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"]["deeplink"] == "bixby://masked/act/aa73a35e8d"


def test_troubleshooting_request_still_uses_m1():
    response = client.post("/v1/troubleshoot", json={"query": "my wifi keeps disconnecting"})
    assert response.headers["X-Planner"] == "m1"


def test_siis_reference_bypasses_the_catalog_planner():
    siis = json.loads((ROOT / "data" / "siis_responses.json").read_text(encoding="utf-8"))
    sample = siis["responses"][0]["siis_response"]
    response = client.post("/v1/troubleshoot", json={"query": "turn on bluetooth", "siis_response": sample})
    assert response.headers["X-Planner"] == "m1"


def test_settings_plan_is_cached_and_opposite_toggle_is_not_reused():
    client.post("/v1/troubleshoot", json={"query": "turn on bluetooth"})
    assert client.post("/v1/troubleshoot", json={"query": "turn on bluetooth please"}).headers["X-Cache"] != "miss"
    off = client.post("/v1/troubleshoot", json={"query": "turn off bluetooth"})
    assert off.json()["contexts"][0]["actions"][0]["actionName"] == "Disable Bluetooth"


def test_catalog_plan_does_not_count_m1_llm_calls(fake_llm):
    cache.clear()
    response = client.post("/v1/troubleshoot", json={"query": "my phone time is in 24 hrs"})
    assert response.headers["X-Planner"] == "catalog"
    assert response.headers["X-LLM-Calls"] == "1"
