import pytest

from backend.services.contract_validator import disruption_rank, validate_and_repair


def _action(name, category="auto"):
    return {
        "actionName": name,
        "description": "It will help fix the issue",
        "stepGroups": [{"steps": ["Open Settings."], "actionableDeeplink": None, "validationDeeplink": None}],
        "category": category,
    }


def _plan(*actions):
    return {"contexts": [{"goal": "Follow these steps to perform this Battery Troubleshooting", "title": "Battery drain issue",
                          "score": 0.9, "actions": list(actions)}], "query_variations": None, "fallback": None}


@pytest.mark.parametrize("name,category,rank", [
    ("Enable Power Saving Mode", "auto", 0),
    ("View WiFi Settings", "auto", 0),
    ("Clear App Cache", "auto", 1),
    ("Optimize Device Storage and Memory", "auto", 1),
    ("Check Software Updates", "auto", 1),
    ("Clean Camera Lens Surface", "manual", 1),
    ("Force Restart Device", "manual", 2),
    ("Schedule Screen Repair Service", "manual", 3),
    ("Reset Network Settings", "critical", 4),
])
def test_disruption_rank(name, category, rank):
    assert disruption_rank({"actionName": name, "category": category}) == rank


def test_plan_is_reordered_toggles_then_optimizations_then_reboots():
    plan = _plan(
        _action("Force Restart Device", "manual"),
        _action("Clear App Cache"),
        _action("Reset All Settings", "critical"),
        _action("Enable Power Saving Mode"),
    )
    repaired, report = validate_and_repair(plan)
    names = [a["actionName"] for a in repaired["contexts"][0]["actions"]]
    assert names == ["Enable Power Saving Mode", "Clear App Cache", "Force Restart Device", "Reset All Settings"]
    assert "DISRUPTION_ORDER" in report.summary()["codes"]


def test_order_within_the_same_rank_is_kept():
    plan = _plan(_action("View WiFi Settings"), _action("Disable Airplane Mode"))
    repaired, report = validate_and_repair(plan)
    assert [a["actionName"] for a in repaired["contexts"][0]["actions"]] == ["View WiFi Settings", "Disable Airplane Mode"]
    assert report.summary()["repaired"] == 0


def test_already_ordered_plan_needs_no_repair():
    plan = _plan(_action("Enable Power Saving Mode"), _action("Clear App Cache"), _action("Reboot into Safe Mode", "critical"))
    assert validate_and_repair(plan)[1].summary()["repaired"] == 0
