from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
