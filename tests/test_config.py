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


def _free_tier_file(tmp_path, key="nvapi-test"):
    import json

    path = tmp_path / "free_tier.json"
    path.write_text(json.dumps({"OPENAI_API_KEY": key, "OPENAI_BASE_URL": "https://free.example/v1", "LLM_MODEL": "free-model"}), encoding="utf-8")
    return path


def test_own_openai_key_is_kept(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-judge")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "own_key"
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-judge"
    assert "OPENAI_BASE_URL" not in os.environ


def test_empty_key_uses_free_tier(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "  ")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "free_tier"
    import os

    assert os.environ["OPENAI_API_KEY"] == "nvapi-test"
    assert os.environ["OPENAI_BASE_URL"] == "https://free.example/v1"
    assert os.environ["LLM_MODEL"] == "free-model"


def test_free_tier_can_be_switched_off(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_FREE_TIER", "false")
    assert apply_llm_provider(_free_tier_file(tmp_path)) == "offline"
    import os

    assert "OPENAI_API_KEY" not in os.environ


def test_missing_or_empty_free_tier_file_runs_offline(tmp_path, monkeypatch):
    from backend.config import apply_llm_provider

    _clear_llm_env(monkeypatch)
    assert apply_llm_provider(tmp_path / "missing.json") == "offline"
    assert apply_llm_provider(_free_tier_file(tmp_path, key="")) == "offline"


def test_shipped_free_tier_file_is_complete():
    import json

    from backend.config import FREE_TIER_PATH

    free_tier = json.loads(FREE_TIER_PATH.read_text(encoding="utf-8"))
    assert free_tier["OPENAI_API_KEY"]
    assert free_tier["OPENAI_BASE_URL"].startswith("https://")
    assert free_tier["LLM_MODEL"]
