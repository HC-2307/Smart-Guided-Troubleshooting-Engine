import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.contract_validator import LINK_PATTERN, validate_and_repair
from backend.services.reference_parser import parse_reference

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

SPEC_QUERY = "phone swipe gestures wrong direction after app install"
SPEC_TEXT = (
    "## Step 1: Change navigation gestures\nOpen Settings, tap Display, and then tap Navigation bar. "
    "Select Swipe gestures.\n## Step 2: Restart the phone\nPress and hold the Side button, then tap Restart.\n"
    "For more details see the link at https://www.samsung.com/support."
)


def _references() -> list[dict]:
    data = json.loads((ROOT / "data" / "siis_responses.json").read_text(encoding="utf-8"))
    return [r["siis_response"] for r in data["responses"]]


def test_steps_are_split_into_single_interactions():
    plan = parse_reference({"title": "Navigation gestures", "content": SPEC_TEXT})
    first = plan["contexts"][0]["actions"][0]
    assert first["actionName"] == "Change Navigation Gestures"
    assert first["stepGroups"][0]["steps"] == ["Open Settings.", "Tap Display.", "Tap Navigation bar.", "Select Swipe gestures."]


def test_link_sentences_are_dropped():
    plan = parse_reference({"title": "Navigation gestures", "content": SPEC_TEXT})
    steps = [s for a in plan["contexts"][0]["actions"] for s in a["stepGroups"][0]["steps"]]
    assert not any(LINK_PATTERN.search(s) or "link" in s.lower() for s in steps)


def test_restart_sections_are_manual_and_resets_are_critical_and_last():
    text = "## Factory data reset\nOpen Settings, then tap Reset.\n## Restart the phone\nPress and hold the Side button.\n## Check battery usage\nOpen Settings, then tap Battery."
    actions = parse_reference({"title": "Battery drain", "content": text})["contexts"][0]["actions"]
    assert [a["category"] for a in actions] == ["auto", "manual", "critical"]


def test_text_without_instructions_gives_no_plan():
    assert parse_reference({"title": "About", "content": "Samsung makes great phones. They are popular."}) is None
    assert parse_reference(None) is None
    assert parse_reference({"title": "", "content": ""}) is None


def test_fragments_left_by_removed_link_labels_are_dropped():
    plan = parse_reference({"title": "Reset", "content": "## Reset network\nNavigate to. Open Settings, then tap General management."})
    assert plan["contexts"][0]["actions"][0]["stepGroups"][0]["steps"] == ["Open Settings.", "Tap General management."]


def test_glued_source_text_is_dropped():
    text = "## Fingerprint\nGo to Settings > Security,and then enteryourcurrentpin,passwordorpattern.Tap it."
    assert parse_reference({"title": "Fingerprint", "content": text}) is None


def test_every_parsed_official_reference_passes_the_contract_with_zero_repairs():
    parsed = [p for p in (parse_reference(r) for r in _references()) if p]
    assert len(parsed) >= 15
    for plan in parsed:
        _, report = validate_and_repair({**plan, "query_variations": None, "fallback": None})
        assert report.summary()["repaired"] == 0 and report.summary()["quarantined"] == 0


def test_every_parsed_step_comes_from_the_reference_text():
    for reference in _references():
        plan = parse_reference(reference)
        if not plan:
            continue
        source = re.sub(r"\s+", " ", reference["content"]).lower()
        for action in plan["contexts"][0]["actions"]:
            for step in action["stepGroups"][0]["steps"]:
                words = re.findall(r"[a-z0-9]+", step.lower())
                assert all(w in source for w in words), step


def test_spec_example_with_raw_text_reference_returns_its_steps():
    response = client.post("/v1/troubleshoot", json={"query": SPEC_QUERY, "siis_response": SPEC_TEXT})
    assert response.status_code == 200
    actions = response.json()["contexts"][0]["actions"]
    assert actions[0]["stepGroups"][0]["steps"][:3] == ["Open Settings.", "Tap Display.", "Tap Navigation bar."]
    assert "http" not in response.text


def test_blank_raw_text_reference_is_treated_as_absent():
    response = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast", "siis_response": "   "})
    assert response.status_code == 200 and response.json()["contexts"]


@pytest.mark.parametrize("bad", [123, ["list"], "x" * 20001])
def test_invalid_siis_response_is_rejected_cleanly(bad):
    response = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast", "siis_response": bad})
    assert response.status_code == 422


def test_reference_grounded_plan_is_cached_without_paraphrase_keys():
    from backend.services import cache

    cache.clear()
    client.post("/v1/troubleshoot", json={"query": SPEC_QUERY, "siis_response": SPEC_TEXT})
    entry = next(e for e in cache._default._entries.values() if e.query == SPEC_QUERY)
    assert len(entry.key_ids) == 1 and entry.strict


def test_domain_plan_still_seeds_paraphrase_keys():
    from backend.services import cache

    cache.clear()
    client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    entry = next(e for e in cache._default._entries.values() if e.query == "my phone battery drains fast")
    assert len(entry.key_ids) > 1 and not entry.strict
