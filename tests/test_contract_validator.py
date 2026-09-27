import copy

import pytest

from backend.services.contract_validator import (
    DUMMY_DEEPLINK,
    catalog_by_deeplink,
    entry_polarity,
    has_link,
    polarity,
    validate_and_repair,
)


def _entry(original_type=None, message_prefix=None):
    for entry in catalog_by_deeplink().values():
        if original_type and entry.get("originalType") != original_type:
            continue
        if message_prefix and not entry["message"].startswith(message_prefix):
            continue
        return entry
    raise LookupError


def _link(entry):
    return {k: entry.get(k) for k in ("deeplink", "description", "message", "classes", "originalType")}


def _action(name="Check Battery Usage", category="auto", link=None, steps=None, description=None):
    return {
        "actionName": name,
        "description": description or "It will show battery usage details.",
        "category": category,
        "stepGroups": [{
            "steps": steps or ["Open Settings.", "Tap Battery and device care."],
            "actionableDeeplink": link,
            "validationDeeplink": None,
        }],
    }


def _response(*actions, variations=None):
    return {
        "contexts": [{
            "goal": "Follow these steps to perform this Battery Troubleshooting",
            "title": "Battery drain issue",
            "score": 0.9,
            "actions": list(actions),
        }],
        "query_variations": variations if variations is not None else [f"variation {i}" for i in range(9)],
        "fallback": None,
    }


def codes(report):
    return {v.code for v in report.violations}


def test_clean_response_passes_untouched():
    link = _link(_entry("onClickURL"))
    original = _response(_action(link=link))
    output, report = validate_and_repair(original)
    assert report.violations == []
    assert output == original


def test_input_is_not_mutated():
    original = _response(_action(name="check battery usage"))
    snapshot = copy.deepcopy(original)
    validate_and_repair(original)
    assert original == snapshot


def test_deeplink_not_in_catalog_is_removed():
    output, report = validate_and_repair(_response(_action(link={"deeplink": "bixby://invented/xyz", "description": "x"})))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"] is None
    assert "DEEPLINK_NOT_IN_CATALOG" in codes(report)


def test_deeplink_metadata_drift_is_restored_from_catalog():
    entry = _entry("onClickURL")
    link = dict(_link(entry), description="tampered description")
    output, report = validate_and_repair(_response(_action(link=link)))
    restored = output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"]
    assert restored["description"] == entry["description"]
    assert "DEEPLINK_METADATA_DRIFT" in codes(report)


def test_dummy_placeholder_keeps_generated_metadata():
    link = {"deeplink": DUMMY_DEEPLINK, "description": "Opens the lock screen settings", "message": "Lock screen"}
    output, report = validate_and_repair(_response(_action(link=link)))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"]["message"] == "Lock screen"
    assert "DEEPLINK_METADATA_DRIFT" not in codes(report)


def test_manual_action_deeplink_is_removed():
    link = _link(_entry("onClickURL"))
    output, report = validate_and_repair(_response(_action(name="Visit Service Center", category="manual", link=link)))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"] is None
    assert "MANUAL_HAS_DEEPLINK" in codes(report)


def test_enable_action_with_disable_deeplink_is_rejected():
    link = _link(_entry("offURL", "Disable"))
    output, report = validate_and_repair(_response(_action(name="Enable Power Saving Mode", link=link)))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"] is None
    assert "TOGGLE_POLARITY_CONFLICT" in codes(report)


def test_matching_polarity_is_kept():
    link = _link(_entry("onURL", "Enable"))
    output, report = validate_and_repair(_response(_action(name="Enable Power Saving Mode", link=link)))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["actionableDeeplink"] is not None
    assert "TOGGLE_POLARITY_CONFLICT" not in codes(report)


def test_critical_actions_are_moved_last():
    output, report = validate_and_repair(_response(
        _action(name="Factory Reset Device", category="critical", description="It will erase all device data."),
        _action(name="Check Battery Usage"),
    ))
    assert [a["category"] for a in output["contexts"][0]["actions"]] == ["auto", "critical"]
    assert "CRITICAL_NOT_LAST" in codes(report)


@pytest.mark.parametrize("description", [
    "It will help.",
    "This will show battery usage details.",
    "It will show every single battery usage detail right now.",
])
def test_description_contract_violation_quarantines_action(description):
    output, report = validate_and_repair(_response(
        _action(name="Bad Action", description=description), _action(name="Check Battery Usage")))
    assert [a["actionName"] for a in output["contexts"][0]["actions"]] == ["Check Battery Usage"]
    assert "DESCRIPTION_CONTRACT" in codes(report)
    assert report.count("quarantined") == 1


@pytest.mark.parametrize("step", [
    "Visit https://samsung.com for help.",
    "Go to www.samsung.com",
    "See [support](https://x.y)",
    "Open bixby://masked/act/aa73a35e8d directly",
])
def test_link_in_step_quarantines_action(step):
    output, report = validate_and_repair(_response(_action(name="Leaky Action", steps=[step]), _action()))
    names = [a["actionName"] for a in output["contexts"][0]["actions"]]
    assert "Leaky Action" not in names
    assert "URL_LEAK" in codes(report)


def test_all_actions_invalid_returns_validation_failed():
    output, report = validate_and_repair(_response(_action(description="nope")))
    assert output["contexts"] == []
    assert output["fallback"] == "validation_failed"
    assert "GOAL_EMPTY" in codes(report)


def test_empty_plan_returns_no_match():
    output, _ = validate_and_repair({"contexts": [], "query_variations": []})
    assert output["fallback"] == "no_match"


def test_bad_goal_phrasing_quarantines_goal():
    response = _response(_action())
    response["contexts"][0]["goal"] = "Try these battery tips"
    output, report = validate_and_repair(response)
    assert output["contexts"] == []
    assert "GOAL_PHRASING" in codes(report)


def test_title_word_count_is_enforced():
    response = _response(_action())
    response["contexts"][0]["title"] = "Battery"
    _, report = validate_and_repair(response)
    assert "TITLE_CONTRACT" in codes(report)


def test_title_case_score_and_action_name_are_repaired():
    response = _response(_action(name="check battery usage in settings"))
    response["contexts"][0]["title"] = "battery drain issue"
    response["contexts"][0]["score"] = 1.7
    output, report = validate_and_repair(response)
    goal = output["contexts"][0]
    assert goal["title"] == "Battery drain issue"
    assert goal["score"] == 1.0
    assert goal["actions"][0]["actionName"] == "Check Battery Usage in Settings"
    assert {"TITLE_CASE", "SCORE_RANGE", "ACTION_NAME_CASE"} <= codes(report)


def test_markdown_is_stripped_from_steps():
    output, report = validate_and_repair(_response(_action(steps=["Tap **Battery** and `device care`."])))
    assert output["contexts"][0]["actions"][0]["stepGroups"][0]["steps"][0] == "Tap Battery and device care."
    assert "MARKDOWN_IN_STEP" in codes(report)


def test_duplicate_actions_are_dropped():
    output, report = validate_and_repair(_response(_action(), _action()))
    assert len(output["contexts"][0]["actions"]) == 1
    assert "DUPLICATE_ACTION" in codes(report)


def test_invalid_category_quarantines_action():
    output, report = validate_and_repair(_response(_action(category="standard"), _action(name="Other Action")))
    assert [a["actionName"] for a in output["contexts"][0]["actions"]] == ["Other Action"]
    assert "CATEGORY_INVALID" in codes(report)


def test_query_variations_are_deduplicated_trimmed_and_warned():
    dup, _ = validate_and_repair(_response(_action(), variations=["a b", "A  b"] + [f"v{i}" for i in range(12)]))
    assert len(dup["query_variations"]) == 10
    few, report = validate_and_repair(_response(_action(), variations=["only one"]))
    assert "VARIATIONS_TOO_FEW" in codes(report)
    assert report.count("warning") == 1
    assert few["contexts"]


def test_summary_counts_outcomes():
    _, report = validate_and_repair(_response(_action(name="check battery usage"), _action(name="X", description="bad")))
    summary = report.summary()
    assert summary["repaired"] == 1
    assert summary["quarantined"] == 1
    assert "ACTION_NAME_CASE" in summary["codes"]


def test_helpers():
    assert has_link("see http://x.y") and not has_link("Open Settings.")
    assert polarity("Enable Wi-Fi") == "on"
    assert polarity("Turn off Bluetooth") == "off"
    assert polarity("Check Battery Usage") is None
    assert entry_polarity({"originalType": "offURL", "message": "x"}) == "off"
