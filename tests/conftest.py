import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def deterministic_pipeline(monkeypatch):
    if os.getenv("M3_TESTS_ALLOW_LLM") != "1":
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from backend.services import cache, telemetry
    cache.clear()
    telemetry.metrics.reset()
    yield
    cache.clear()
