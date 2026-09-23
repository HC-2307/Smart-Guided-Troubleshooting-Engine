import time

from backend.services import cache


def test_set_then_get_returns_same_response():
    cache.set("battery drains fast", {"contexts": []})
    assert cache.get("battery drains fast") == {"contexts": []}


def test_get_misses_on_unseen_query():
    assert cache.get("never cached query xyz") is None


def test_normalization_hits_across_case_and_whitespace_variants():
    cache.set("Screen  Is Cracked", {"contexts": [{"title": "cracked"}]})
    assert cache.get("screen is cracked") == {"contexts": [{"title": "cracked"}]}
    assert cache.get("   screen   is   cracked   ") == {"contexts": [{"title": "cracked"}]}


def test_expired_entry_is_evicted():
    cache._store["expired key"] = (time.time() - 1, {"contexts": []})
    assert cache.get("expired key") is None
    assert "expired key" not in cache._store
