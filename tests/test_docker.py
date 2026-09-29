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
    assert env["OPENAI_BASE_URL"] == "${OPENAI_BASE_URL:-}"
    assert env["LLM_FREE_TIER"] == "${LLM_FREE_TIER:-true}"
    assert env["NVIDIA_API_KEY"] == "${NVIDIA_API_KEY:-}"


def test_start_scripts_ask_for_key_and_fall_back_to_free_tier():
    for name in ("start.sh", "start.ps1"):
        script = (ROOT / name).read_text(encoding="utf-8")
        assert "OpenAI API key (leave empty to use the free NVIDIA tier or offline mode)" in script
        assert "NVIDIA API key (free at build.nvidia.com; leave empty to run offline without an LLM)" in script
        assert "docker compose up --build" in script
        assert "LLM_FREE_TIER" in script


def test_dockerfile_ships_free_tier_config_without_a_key():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY backend/ backend/" in dockerfile
    assert (ROOT / "backend" / "free_tier.json").exists()


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
