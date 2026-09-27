from fastapi.testclient import TestClient

from backend.main import app
from backend.services import orchestrator

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_unavailable_when_warm_up_fails(monkeypatch):
    import backend.main as main

    monkeypatch.setattr(main._ready, "is_set", lambda: False)
    monkeypatch.setattr(main, "_get_m2_engine", lambda: (_ for _ in ()).throw(RuntimeError("catalog missing")))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_troubleshoot_returns_schema_conformant_response():
    response = client.post("/v1/troubleshoot", json={"query": "phone battery drains fast"})
    assert response.status_code == 200

    body = response.json()
    assert "contexts" in body
    for context in body["contexts"]:
        assert context["goal"].startswith("Follow these steps to perform this")
        for action in context["actions"]:
            assert action["description"].startswith("It will")


def test_troubleshoot_response_has_no_url_leakage():
    response = client.post("/v1/troubleshoot", json={"query": "screen is cracked"})
    body = response.json()

    serialized = str(body)
    assert "http://" not in serialized
    assert "https://" not in serialized
    assert "www." not in serialized


def test_trace_headers_are_attached():
    response = client.post("/v1/troubleshoot", json={"query": "wifi keeps disconnecting"})
    for header in ("X-Request-ID", "X-Cache", "X-Pipeline-Ms", "X-LLM-Calls", "X-Est-Cost-USD"):
        assert header in response.headers
    assert response.headers["X-Cache"] == "miss"
    assert response.headers["X-LLM-Calls"] == "0"


def test_caller_request_id_is_propagated():
    response = client.post("/v1/troubleshoot", json={"query": "wifi drops"}, headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_paraphrase_is_served_from_semantic_cache_over_http():
    first = client.post("/v1/troubleshoot", json={"query": "My phone battery drains really fast"})
    second = client.post("/v1/troubleshoot", json={"query": "battery draining super quick on my galaxy"})
    assert first.headers["X-Cache"] == "miss"
    assert second.headers["X-Cache"] in ("semantic", "variation")
    assert second.json() == first.json()


def test_body_contract_is_unchanged_by_telemetry():
    body = client.post("/v1/troubleshoot", json={"query": "screen flickers"}).json()
    assert set(body) == {"contexts", "query_variations", "fallback"}


def test_blank_query_is_rejected():
    assert client.post("/v1/troubleshoot", json={"query": "   "}).status_code == 422
    assert client.post("/v1/troubleshoot", json={"query": ""}).status_code == 422


def test_oversized_query_is_rejected():
    assert client.post("/v1/troubleshoot", json={"query": "a" * 2001}).status_code == 422


def test_rejected_requests_are_not_counted_in_metrics():
    client.post("/v1/troubleshoot", json={"query": ""})
    assert client.get("/v1/metrics").json()["pipeline"]["requests"] == 0


def test_unexpected_error_returns_controlled_500(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(orchestrator, "process_query", boom)
    response = client.post("/v1/troubleshoot", json={"query": "some brand new complaint about nfc"})
    assert response.status_code == 500
    assert response.json() == {"contexts": [], "fallback": "internal_error"}
    assert "X-Request-ID" in response.headers
    assert "provider exploded" not in response.text


def test_metrics_endpoint_reports_cache_and_latency():
    client.post("/v1/troubleshoot", json={"query": "Rear camera photos are blurry"})
    client.post("/v1/troubleshoot", json={"query": "back camera pictures blurry"})
    snapshot = client.get("/v1/metrics").json()

    assert snapshot["pipeline"]["requests"] == 2
    assert snapshot["pipeline"]["cache_hit_rate"] == 0.5
    assert snapshot["pipeline"]["latency_ms"]["hit"]["count"] == 1
    assert snapshot["pipeline"]["latency_ms"]["cold"]["count"] == 1
    assert snapshot["cache"]["entries"] == 1
    assert snapshot["pipeline"]["est_cost_usd"] == 0.0
