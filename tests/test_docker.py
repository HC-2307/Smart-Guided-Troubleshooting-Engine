from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_runs_api_and_frontend():
    services = COMPOSE["services"]
    assert "8000:8000" in services["api"]["ports"]
    assert "5500:80" in services["frontend"]["ports"]
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_compose_passes_llm_keys_without_hardcoding():
    env = COMPOSE["services"]["api"]["environment"]
    assert env["OPENAI_API_KEY"] == "${OPENAI_API_KEY:-}"
    assert env["GEMINI_API_KEY"] == "${GEMINI_API_KEY:-}"


def test_compose_frontend_serves_repo_frontend_folder():
    volumes = COMPOSE["services"]["frontend"]["volumes"]
    assert "./frontend:/usr/share/nginx/html:ro" in volumes
    assert (ROOT / "frontend" / "index.html").exists()


def test_dockerfile_copies_runtime_dirs():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for folder in ("backend/", "data/", "prompts/"):
        assert f"COPY {folder}" in dockerfile
        assert (ROOT / folder).is_dir()


def test_dockerignore_excludes_secrets():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in ignored
    assert ".git" in ignored
