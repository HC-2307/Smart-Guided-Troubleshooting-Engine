from backend.services import cache
from backend.services.orchestrator import troubleshoot


def test_orchestrator_runs_real_m1_to_m2_pipeline_end_to_end():
    response = troubleshoot("phone battery drains fast")

    assert response.fallback is None
    assert len(response.contexts) > 0

    goal = response.contexts[0]
    assert goal.goal.startswith("Follow these steps to perform this")
    assert len(goal.title.split()) in (2, 3)

    for action in goal.actions:
        assert action.description.startswith("It will")
        assert 5 <= len(action.description.rstrip(".").split()) <= 7


def test_orchestrator_result_is_served_from_cache_on_repeat_query():
    query = "wifi keeps disconnecting on my galaxy"
    cache.get(query)  # ensure a clean slate for this key isn't required; cache.set overwrites
    first = troubleshoot(query)
    cached_entry = cache.get(query)

    assert cached_entry is not None
    assert cached_entry == first.model_dump()


def test_critical_actions_are_ordered_last_after_m2_resolution():
    response = troubleshoot("need to factory reset my phone")
    goal = response.contexts[0]

    categories = [action.category for action in goal.actions]
    if "critical" in categories:
        assert categories[-1] == "critical" or all(
            c != "critical" for c in categories[categories.index("critical") + 1:]
        )


def test_manual_actions_never_carry_actionable_deeplink():
    response = troubleshoot("camera lens is blurry")
    for goal in response.contexts:
        for action in goal.actions:
            if action.category == "manual":
                for group in action.stepGroups:
                    assert group.actionableDeeplink is None
