from backend.services import cache, orchestrator, query_processor, telemetry
from backend.services.contract_validator import catalog_by_deeplink, entry_polarity, polarity
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
    first = troubleshoot(query)
    cached_entry = cache.get(query)

    assert cached_entry is not None
    assert cached_entry == first.model_dump()


def test_paraphrase_hits_cache_without_rerunning_pipeline(monkeypatch):
    troubleshoot("My phone battery drains really fast")
    monkeypatch.setattr(orchestrator, "process_query", lambda *_: (_ for _ in ()).throw(AssertionError("cold path")))
    telemetry.begin()
    response = troubleshoot("Why does my Samsung battery die so quickly?")
    assert response.contexts
    assert telemetry.current().cache_tier in ("semantic", "variation")
    telemetry.end()


def test_critical_actions_are_ordered_last_after_m2_resolution():
    response = troubleshoot("need to factory reset my phone")
    goal = response.contexts[0]

    categories = [action.category for action in goal.actions]
    if "critical" in categories:
        first_critical = categories.index("critical")
        assert all(c == "critical" for c in categories[first_critical:])


def test_manual_actions_never_carry_actionable_deeplink():
    response = troubleshoot("camera lens is blurry")
    for goal in response.contexts:
        for action in goal.actions:
            if action.category == "manual":
                for group in action.stepGroups:
                    assert group.actionableDeeplink is None


def test_every_delivered_deeplink_is_verbatim_from_catalog_with_matching_polarity():
    catalog = catalog_by_deeplink()
    for query in ("phone battery drains fast", "screen flickers", "wifi keeps disconnecting", "camera is blurry"):
        for goal in troubleshoot(query).contexts:
            for action in goal.actions:
                for group in action.stepGroups:
                    link = group.actionableDeeplink
                    if link is None:
                        continue
                    entry = catalog[link.deeplink]
                    assert link.description == entry["description"]
                    wanted, offered = polarity(action.actionName), entry_polarity(entry)
                    assert not (wanted and offered and wanted != offered)


def test_enable_power_saving_gets_the_enable_deeplink_without_m3_repair():
    telemetry.begin()
    response = troubleshoot("phone battery drains fast")
    trace = telemetry.current()
    telemetry.end()
    action = next(a for a in response.contexts[0].actions if a.actionName == "Enable Power Saving Mode")
    assert action.stepGroups[0].actionableDeeplink.originalType == "onURL"
    assert "TOGGLE_POLARITY_CONFLICT" not in trace.validation["codes"]


def test_official_and_domain_queries_need_no_contract_repairs():
    queries = [q.strip() for q in open("data/input.txt", encoding="utf-8") if q.strip()]
    queries += ["Wi-Fi keeps disconnecting", "No sound from my speaker", "My storage is full", "stuck in a boot loop"]
    for query in queries:
        cache.clear()
        telemetry.begin()
        response = troubleshoot(query)
        trace = telemetry.current()
        telemetry.end()
        assert response.contexts, query
        assert trace.validation["repaired"] == 0 and trace.validation["quarantined"] == 0, (query, trace.validation)


def test_cache_failure_does_not_break_the_request(monkeypatch):
    def broken(*_args, **_kwargs):
        raise ConnectionError("cache down")

    monkeypatch.setattr(cache, "lookup", broken)
    monkeypatch.setattr(cache, "store", broken)
    telemetry.begin()
    response = troubleshoot("screen keeps flickering")
    trace = telemetry.current()
    telemetry.end()
    assert response.contexts
    assert any("cache_lookup" in e for e in trace.errors)
    assert any("cache_store" in e for e in trace.errors)


def test_siis_context_bypasses_cache():
    troubleshoot("phone battery drains fast")
    telemetry.begin()
    troubleshoot("phone battery drains fast", {"title": "Battery", "content": "Check battery usage."})
    assert telemetry.current().cache_tier == "miss"
    telemetry.end()


def test_failed_responses_are_not_cached(monkeypatch):
    monkeypatch.setattr(orchestrator, "process_query", lambda *_: {"contexts": [], "fallback": "no_match"})
    response = troubleshoot("totally unknown request about quantum flux")
    assert response.fallback == "no_match"
    assert cache.stats()["entries"] == 0


def test_resolution_memo_returns_equal_but_independent_copies():
    plan = {"contexts": [{"goal": "g", "title": "t", "score": 1.0, "actions": [{
        "actionName": "Check Battery Usage", "description": "It will show battery usage.",
        "category": "auto", "stepGroups": [{"steps": ["Open Settings."]}],
    }]}]}
    first = query_processor.resolve_plan(plan)
    second = query_processor.resolve_plan(plan)
    assert first == second
    first["contexts"][0]["title"] = "mutated"
    assert query_processor.resolve_plan(plan)["contexts"][0]["title"] == "t"
    assert plan["contexts"][0]["actions"][0]["stepGroups"][0].get("actionableDeeplink") is None


def _answer(client, query):
    response = client.post("/v1/troubleshoot", json={"query": query})
    body = response.json()
    return (body["contexts"][0]["title"] if body["contexts"] else body["fallback"]), response.headers["X-Cache"]


def test_misspelt_query_does_not_poison_the_cache_for_the_correct_spelling():
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    for typo, clean in [
        ("mobil data not wrking", "mobile data not working"),
        ("my phone storge is ful", "my phone storage is full"),
        ("blutooth wont pair with my car", "bluetooth won't pair with my car"),
        ("speker not wroking on calls", "speaker not working on calls"),
    ]:
        cache.clear()
        client.post("/v1/troubleshoot", json={"query": typo})
        after_typo, tier = _answer(client, clean)
        cache.clear()
        alone, _ = _answer(client, clean)
        assert after_typo == alone, (typo, clean, after_typo, tier)


def test_confident_plan_is_still_cached_and_reused():
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    cache.clear()
    first, tier = _answer(client, "my phone battery drains so fast")
    assert tier == "miss"
    second, tier = _answer(client, "my phone batery drainz so fast")
    assert second == first and tier in {"semantic", "variation"}
