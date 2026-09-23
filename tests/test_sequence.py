from backend.services.sequence_engine import apply_sequence_rules, validate_action_sequence


def test_critical_actions_are_last():
    plan = {"contexts": [{"actions": [
        {"actionName": "Factory reset", "category": "critical", "stepGroups": [{"steps": []}]},
        {"actionName": "Check display", "category": "auto", "stepGroups": [{"steps": []}]},
    ]}]}
    result, violations = apply_sequence_rules(plan)
    names = [a["actionName"] for a in result["contexts"][0]["actions"]]
    assert names == ["Check display", "Factory reset"]
    assert violations == []


def test_manual_action_cannot_have_deeplink():
    actions = [{
        "actionName": "Visit service center",
        "category": "manual",
        "stepGroups": [{
            "steps": ["Visit a service center."],
            "actionableDeeplink": {"deeplink": "bixby://bad"}
        }]
    }]
    assert validate_action_sequence(actions)
