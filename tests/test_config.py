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
