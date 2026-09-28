import json

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.services import cache, orchestrator
from backend.services.cache import SemanticCache

RESPONSE = {"contexts": [{"goal": "g", "title": "t", "score": 0.9, "actions": []}], "query_variations": [], "fallback": None}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_saved_cache_is_restored_after_restart(tmp_path):
    path = tmp_path / "cache.json"
    first = SemanticCache()
    first.store("my phone battery drains fast", RESPONSE, ["battery dies too quickly on my galaxy"])
    assert first.save(str(path)) == 1

    second = SemanticCache()
    assert second.load(str(path)) == 1
    assert second.lookup("my phone battery drains fast").tier == "exact"
    assert second.lookup("battery dies too quickly on my galaxy").response == RESPONSE


def test_expired_entries_are_not_restored_but_pinned_ones_are(tmp_path):
    clock = Clock()
    path = tmp_path / "cache.json"
    first = SemanticCache(ttl_seconds=10, clock=clock)
    first.store("screen keeps flickering", RESPONSE)
    first.store("wifi keeps disconnecting", RESPONSE, pinned=True)
    first.save(str(path))

    clock.now += 60
    second = SemanticCache(ttl_seconds=10, clock=clock)
    assert second.load(str(path)) == 1
    assert second.contains("wifi keeps disconnecting")
    assert not second.contains("screen keeps flickering")


def test_pinned_entries_never_expire_or_get_evicted():
    clock = Clock()
    small = SemanticCache(ttl_seconds=10, max_entries=2, clock=clock)
    small.store("official query one", RESPONSE, pinned=True)
    small.store("query two", RESPONSE)
    small.store("query three", RESPONSE)
    small.store("query four", RESPONSE)
    clock.now += 3600
    assert small.contains("official query one")
    assert small.stats()["pinned"] == 1


def test_corrupt_cache_file_starts_empty_without_crashing(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")
    fresh = SemanticCache()
    assert fresh.load(str(path)) == 0
    assert len(fresh) == 0


def test_bad_records_are_skipped_and_good_ones_kept(tmp_path):
    path = tmp_path / "cache.json"
    good = {"query": "turn on bluetooth", "response": RESPONSE, "variations": [], "pinned": True, "expires_at": 0}
    path.write_text(json.dumps({"version": 1, "entries": [{"query": "missing fields"}, good]}), encoding="utf-8")
    fresh = SemanticCache()
    assert fresh.load(str(path)) == 1
    assert fresh.contains("turn on bluetooth")


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "nested" / "cache.json"
    store = SemanticCache()
    store.store("change my ringtone", RESPONSE)
    store.save(str(path))
    assert path.exists()
    assert not (tmp_path / "nested" / "cache.json.tmp").exists()
    assert not store.dirty


def test_missing_cache_file_loads_nothing(tmp_path):
    assert SemanticCache().load(str(tmp_path / "absent.json")) == 0


def test_prewarm_pins_every_official_reference_query():
    report = orchestrator.prewarm()
    references = orchestrator._reference_queries()
    assert report["built"] == len(references) == 20
    assert report["failed"] == 0
    assert cache.stats()["pinned"] == 20
    assert all(cache.contains(query) for query, _ in references)


def test_prewarmed_query_is_served_without_running_the_pipeline(monkeypatch):
    orchestrator.prewarm()
    query, _ = orchestrator._reference_queries()[0]
    monkeypatch.setattr(orchestrator, "process_query", lambda *a, **k: pytest.fail("pipeline should not run"))
    response = TestClient(main.app).post("/v1/troubleshoot", json={"query": query})
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "exact"
    assert response.json()["contexts"]


def test_prewarm_skips_queries_already_loaded():
    orchestrator.prewarm()
    assert orchestrator.prewarm() == {"built": 0, "skipped": 20, "failed": 0}


def test_prewarm_keeps_going_when_one_query_fails(monkeypatch):
    real = orchestrator.process_query
    calls = {"n": 0}

    def flaky(query, siis=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider exploded")
        return real(query, siis)

    monkeypatch.setattr(orchestrator, "process_query", flaky)
    report = orchestrator.prewarm()
    assert report["failed"] == 1 and report["built"] == 19


def test_prewarm_survives_unreadable_reference_file(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "SIIS_PATH", tmp_path / "missing.json")
    assert orchestrator.prewarm() == {"built": 0, "skipped": 0, "failed": 0}


def test_persist_cache_writes_only_when_dirty(monkeypatch, tmp_path):
    from dataclasses import replace

    path = tmp_path / "cache.json"
    monkeypatch.setattr(main, "settings", replace(main.settings, cache_persist_path=str(path)))
    monkeypatch.setattr(cache, "settings", replace(cache.settings, cache_persist_path=str(path)))
    main.persist_cache()
    assert not path.exists()
    cache.store("turn on bluetooth", RESPONSE)
    main.persist_cache()
    assert path.exists()
    assert not cache.is_dirty()


def test_restart_round_trip_through_the_app_lifespan(monkeypatch, tmp_path):
    from dataclasses import replace

    path = tmp_path / "cache.json"
    patched = replace(main.settings, cache_persist_path=str(path), cache_prewarm=False)
    monkeypatch.setattr(main, "settings", patched)
    monkeypatch.setattr(cache, "settings", patched)
    monkeypatch.setattr(main._ready, "is_set", lambda: False)

    with TestClient(main.app) as client:
        client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    assert path.exists()

    cache.clear()
    with TestClient(main.app) as client:
        response = client.post("/v1/troubleshoot", json={"query": "my phone battery drains fast"})
    assert response.headers["X-Cache"] == "exact"
