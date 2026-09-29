from backend.config import load_env_file


def test_env_file_values_are_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("M3_TEST_ENV_VALUE", raising=False)
    env = tmp_path / ".env"
    env.write_text("M3_TEST_ENV_VALUE=from-file\n", encoding="utf-8")
    assert load_env_file(env)
    import os

    assert os.environ["M3_TEST_ENV_VALUE"] == "from-file"
    monkeypatch.delenv("M3_TEST_ENV_VALUE")


def test_real_environment_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("M3_TEST_ENV_VALUE", "from-shell")
    env = tmp_path / ".env"
    env.write_text("M3_TEST_ENV_VALUE=from-file\n", encoding="utf-8")
    load_env_file(env)
    import os

    assert os.environ["M3_TEST_ENV_VALUE"] == "from-shell"


def test_missing_env_file_is_ignored(tmp_path):
    assert load_env_file(tmp_path / "missing.env") is False


def _clear_llm_env(monkeypatch):
    from backend.config import LLM_VARS

    for name in LLM_VARS + ("LLM_FREE_TIER",):
        monkeypatch.delenv(name, raising=False)


def _free_tier_file(tmp_path):
    import json

    path = tmp_path / "free_tier.json"
    path.write_text(json.dumps({"OPENAI_BASE_URL": "https://free.example/v1", "LLM_MODEL": "free-model"}), encoding="utf-8")
    return path


def test_own_openai_key_is_kept(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-judge")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "own_key"
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-judge"
    assert "OPENAI_BASE_URL" not in os.environ


def test_empty_openai_key_with_nvidia_key_uses_free_tier(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "  ")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "free_tier"
    import os

    assert os.environ["OPENAI_API_KEY"] == "nvapi-test"
    assert os.environ["OPENAI_BASE_URL"] == "https://free.example/v1"
    assert os.environ["LLM_MODEL"] == "free-model"


def test_no_keys_at_all_runs_offline(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "offline"
    import os

    assert "OPENAI_API_KEY" not in os.environ


def test_free_tier_can_be_switched_off(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("LLM_FREE_TIER", "false")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "offline"
    import os

    assert "OPENAI_API_KEY" not in os.environ


def test_missing_free_tier_file_runs_offline(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert apply_llm_provider(tmp_path / "missing.json") == "offline"


def test_shipped_free_tier_file_has_endpoint_and_model_but_no_key():
    import json

    from backend.config import FREE_TIER_PATH

    free_tier = json.loads(FREE_TIER_PATH.read_text(encoding="utf-8"))
    assert free_tier["OPENAI_BASE_URL"].startswith("https://")
    assert free_tier["LLM_MODEL"]
    assert "OPENAI_API_KEY" not in free_tier
    assert "nvapi-" not in FREE_TIER_PATH.read_text(encoding="utf-8")


def test_no_api_key_is_committed_in_tracked_files():
    import re
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.split()
    pattern = re.compile(r"nvapi-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}")
    leaks = []
    for name in tracked:
        path = root / name
        if path.suffix in {".py", ".json", ".yml", ".md", ".txt", ".example", ".sh", ".ps1", ".js", ".html"} and path.exists():
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                leaks.append(name)
    assert leaks == []
