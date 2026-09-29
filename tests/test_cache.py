import threading

import pytest

from backend.services import cache
from backend.services.cache import SemanticCache, domain_evidence, domains_compatible

BATTERY = {"contexts": [{"title": "battery"}]}
CAMERA = {"contexts": [{"title": "rear camera"}]}
DISPLAY = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen display damage"}]}
NETWORK = {"contexts": [{"goal": "Follow these steps to perform this Network Troubleshooting", "title": "Mobile data failure"}]}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def sc():
    return SemanticCache(threshold=0.6, variation_threshold=0.65, max_entries=100)


def test_store_then_exact_lookup_returns_same_response(sc):
    sc.store("battery drains fast", BATTERY)
    hit = sc.lookup("battery drains fast")
    assert hit.response == BATTERY
    assert hit.tier == "exact"


def test_exact_lookup_normalizes_case_and_whitespace(sc):
    sc.store("Screen  Is Cracked", CAMERA)
    assert sc.lookup("   screen   is   cracked   ").tier == "exact"


def test_miss_on_unseen_query(sc):
    assert sc.lookup("never cached query xyz").response is None
    assert sc.stats()["misses"] == 1


def test_paraphrase_is_served_by_semantic_tier(sc):
    sc.store("My phone battery drains really fast", BATTERY)
    hit = sc.lookup("battery draining super quick on my galaxy")
    assert hit.response == BATTERY
    assert hit.tier == "semantic"
    assert hit.score >= 0.6


def test_typo_paraphrase_still_hits(sc):
    sc.store("Wi-Fi keeps disconnecting on my Galaxy", BATTERY)
    assert sc.lookup("wify keeps disconecting").response == BATTERY


def test_different_domain_does_not_hit(sc):
    sc.store("My phone battery drains really fast", BATTERY)
    assert sc.lookup("rear camera photos are blurry").response is None


def test_front_camera_query_does_not_reuse_rear_camera_answer(sc):
    sc.store("Rear camera photos are blurry", CAMERA)
    assert sc.lookup("Front camera photos are blurry").response is None


def test_mobile_data_query_does_not_reuse_wifi_answer(sc):
    sc.store("Wi-Fi keeps disconnecting", BATTERY)
    assert sc.lookup("mobile data keeps disconnecting").response is None


def test_turn_on_query_does_not_reuse_remove_answer(sc):
    sc.store("How do I remove the floating circle button", BATTERY)
    assert sc.lookup("How do I turn on the floating circle button").response is None


def test_unguarded_cache_would_serve_the_conflicting_answer():
    unguarded = SemanticCache(threshold=0.6, variation_threshold=0.65, facet_guard=False, domain_guard=False)
    unguarded.store("Rear camera photos are blurry", CAMERA)
    assert unguarded.lookup("Front camera photos are blurry").response == CAMERA


def test_guard_rejections_are_counted(sc):
    sc.store("Rear camera photos are blurry", CAMERA)
    sc.lookup("Front camera photos are blurry")
    assert sc.stats()["guard_rejections"]["facet"] == 1


def test_seeded_variation_serves_matching_query(sc):
    sc.store("screen issue", DISPLAY, variations=["display keeps flickering on and off"])
    hit = sc.lookup("my display keeps flickering")
    assert hit.response == DISPLAY
    assert hit.tier == "variation"


def test_seeding_disabled_stores_only_the_original_key():
    sc = SemanticCache(seed_variations=False)
    sc.store("screen issue", CAMERA, variations=["display keeps flickering on and off"])
    assert sc.stats()["keys"] == 1


def test_duplicate_variations_are_not_stored_twice(sc):
    sc.store("battery drain", BATTERY, variations=["Battery drain", "battery   drain", "phone dies fast"])
    assert sc.stats()["keys"] == 2


def test_semantic_disabled_behaves_as_exact_cache():
    sc = SemanticCache(semantic_enabled=False)
    sc.store("My phone battery drains really fast", BATTERY)
    assert sc.lookup("battery draining super quick").response is None
    assert sc.lookup("my phone battery drains really fast").response == BATTERY


def test_expired_entry_is_evicted_with_all_its_keys():
    clock = FakeClock()
    sc = SemanticCache(ttl_seconds=10, clock=clock)
    sc.store("battery drains fast", BATTERY, variations=["phone dies quickly"])
    clock.now += 11
    assert sc.lookup("battery drains fast").response is None
    assert sc.stats()["entries"] == 0
    assert sc.stats()["keys"] == 0


def test_lru_eviction_keeps_recently_used_entries():
    sc = SemanticCache(max_entries=2, semantic_enabled=False)
    sc.store("q1", {"n": 1})
    sc.store("q2", {"n": 2})
    sc.lookup("q1")
    sc.store("q3", {"n": 3})
    assert sc.lookup("q2").response is None
    assert sc.lookup("q1").response == {"n": 1}
    assert sc.stats()["evicted"] == 1


def test_restoring_same_query_replaces_entry(sc):
    sc.store("battery drains fast", {"v": 1})
    sc.store("battery drains fast", {"v": 2})
    assert sc.lookup("battery drains fast").response == {"v": 2}
    assert sc.stats()["entries"] == 1


def test_hit_rate_in_stats(sc):
    sc.store("battery drains fast", BATTERY)
    sc.lookup("battery drains fast")
    sc.lookup("unrelated xyz")
    assert sc.stats()["hit_rate"] == 0.5


def test_concurrent_store_and_lookup_is_safe():
    sc = SemanticCache(max_entries=50)
    errors = []

    def worker(n):
        try:
            for i in range(30):
                sc.store(f"battery drains fast {n} {i}", {"n": n})
                sc.lookup(f"battery drain {i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(sc) <= 50


def test_domain_evidence_and_compatibility():
    assert "battery" in domain_evidence("battery drains fast")
    assert domain_evidence("remove the thing") == frozenset()
    assert domains_compatible(frozenset(), "display")
    assert not domains_compatible(frozenset({"camera"}), "battery")


def test_module_level_api_round_trip():
    cache.clear()
    cache.store("screen is cracked", CAMERA)
    assert cache.get("Screen is cracked") == CAMERA
    assert cache.lookup("screen is cracked").tier == "exact"
    assert cache.stats()["entries"] == 1
    cache.clear()


def test_variation_that_contradicts_its_original_query_is_not_seeded(sc):
    sc.store("Front camera selfies are blurry", CAMERA, variations=["The rear camera takes blurry pictures"])
    assert sc.stats()["keys"] == 1
    assert sc.stats()["variations_filtered"] == 1
    assert sc.lookup("Rear camera photos are blurry").response is None


def test_query_must_agree_with_entry_origin_not_only_matched_key():
    sc = SemanticCache(threshold=0.6, variation_threshold=0.65)
    sc.store("Front camera selfies are blurry", CAMERA, variations=["camera photos come out blurry"])
    assert sc.lookup("rear camera photos come out blurry").response is None
    assert sc.lookup("camera photos come out blurry").response == CAMERA


def test_query_answered_by_similarity_keeps_the_same_answer_after_new_entries():
    from backend.services.cache import SemanticCache

    store = SemanticCache()
    first = {"contexts": [{"title": "first"}]}
    second = {"contexts": [{"title": "second"}]}
    store.store("my phone battery drains fast", first)
    hit = store.lookup("my phone battery is draining fast")
    assert hit.response == first and hit.tier == "semantic"
    store.confirm("my phone battery is draining fast", hit)
    store.store("phone battery draining fast", second)
    again = store.lookup("my phone battery is draining fast")
    assert again.response == first and again.tier == "exact"


def test_alias_is_removed_with_its_entry():
    from backend.services.cache import SemanticCache

    store = SemanticCache(max_entries=1)
    store.store("my phone battery drains fast", {"contexts": [{"title": "first"}]})
    store.confirm("my phone battery is draining fast", store.lookup("my phone battery is draining fast"))
    store.store("my screen keeps flickering", {"contexts": [{"title": "screen"}]})
    assert store.lookup("my phone battery is draining fast").response is None


def test_lookup_alone_does_not_pin_an_alias():
    from backend.services.cache import SemanticCache

    store = SemanticCache()
    store.store("my phone battery drains fast", {"contexts": [{"title": "first"}]})
    assert store.lookup("my phone battery is draining fast").tier == "semantic"
    assert store.lookup("my phone battery is draining fast").tier == "semantic"


def test_plan_topics_come_from_goal_and_title():
    assert cache.plan_topics(DISPLAY) == {"display"}
    assert cache.plan_topics(NETWORK) == {"connectivity"}
    assert cache.plan_topics({"contexts": []}) == frozenset()


def test_plan_topics_ignore_action_names():
    plan = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen display damage",
                          "actions": [{"actionName": "Back Up Phone Data"}]}]}
    assert cache.plan_topics(plan) == {"display"}


def test_unconfident_plan_is_not_cached(sc):
    assert sc.store("my phone storge is ful", DISPLAY, require_topic_match=True) is False
    assert sc.lookup("my phone storge is ful").response is None
    assert sc.stats()["unconfident_not_cached"] == 1


def test_confident_plan_is_cached(sc):
    assert sc.store("my screen keeps flickering", DISPLAY, require_topic_match=True) is True
    assert sc.lookup("my screen keeps flickering").tier == "exact"
