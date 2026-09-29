import time
from concurrent.futures import ThreadPoolExecutor

from backend.services import cache, telemetry
from backend.services.orchestrator import troubleshoot

QUERIES = [
    "my phone battery drains fast",
    "battery draining super quick on my galaxy",
    "my wifi keeps disconnecting",
    "wifi connection keeps dropping on my phone",
    "my screen keeps flickering",
    "no sound from my speaker",
    "storage is full",
    "turn on bluetooth",
    "turn off bluetooth",
    "my phone time is in 24 hrs",
    "what is the capital of france",
    "tell me a joke",
]


def _run(query: str):
    telemetry.begin()
    try:
        started = time.perf_counter()
        response = troubleshoot(query)
        return query, response.model_dump(), time.perf_counter() - started
    finally:
        telemetry.end()


def test_concurrent_requests_are_consistent_and_error_free():
    expected = {q: _run(q)[1] for q in QUERIES}
    cache.clear()
    jobs = QUERIES * 25
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_run, jobs))
    assert len(results) == len(jobs)
    mismatched = [q for q, body, _ in results if body["contexts"] and body != expected[q]]
    assert mismatched == []
    for q, body, _ in results:
        assert bool(body["contexts"]) == bool(expected[q]["contexts"])
    latencies = sorted(t for _, _, t in results)
    assert latencies[int(len(latencies) * 0.95)] < 2.0


def test_cache_stays_bounded_and_consistent_under_concurrent_writes():
    unique = [f"my phone battery drains fast variant {i}" for i in range(60)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_run, unique))
    stats = cache.stats()
    assert stats["entries"] <= cache._default.max_entries
    assert stats["keys"] >= stats["entries"]


def test_identical_concurrent_requests_run_the_pipeline_once(monkeypatch):
    import threading

    from backend.services import orchestrator

    real = orchestrator.process_query
    calls = {"n": 0}
    lock = threading.Lock()

    def slow(query, siis=None):
        with lock:
            calls["n"] += 1
        time.sleep(0.3)
        return real(query, siis)

    monkeypatch.setattr(orchestrator, "process_query", slow)
    cache.clear()
    tiers = []

    def run(query):
        trace = telemetry.begin()
        try:
            body = troubleshoot(query).model_dump()
            tiers.append(trace.cache_tier)
            return body
        finally:
            telemetry.end()

    with ThreadPoolExecutor(max_workers=8) as pool:
        bodies = list(pool.map(run, ["my phone battery drains fast"] * 8))
    assert calls["n"] == 1
    assert all(b == bodies[0] for b in bodies)
    assert tiers.count("coalesced") == 7


def test_coalesced_follower_recomputes_when_the_leader_fails(monkeypatch):
    from backend.services import orchestrator

    real = orchestrator._troubleshoot
    state = {"first": True}

    def flaky(query, siis):
        if state["first"]:
            state["first"] = False
            time.sleep(0.2)
            raise RuntimeError("leader crashed")
        return real(query, siis)

    monkeypatch.setattr(orchestrator, "_troubleshoot", flaky)
    results = []

    def run(query):
        telemetry.begin()
        try:
            results.append(troubleshoot(query).model_dump())
        except RuntimeError:
            results.append("error")
        finally:
            telemetry.end()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ["my phone battery drains fast"] * 2))
    assert "error" in results
    assert any(r != "error" and r["contexts"] for r in results)
