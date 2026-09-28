import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "data" / "deeplinks.json"
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: Path = ENV_FILE) -> bool:
    return load_dotenv(path, override=False)


load_env_file()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    cache_ttl_seconds: int = _env_int("CACHE_TTL_SECONDS", 3600)
    cache_max_entries: int = _env_int("CACHE_MAX_ENTRIES", 5000)
    semantic_cache_enabled: bool = _env_bool("SEMANTIC_CACHE_ENABLED", True)
    semantic_threshold: float = _env_float("SEMANTIC_CACHE_THRESHOLD", 0.60)
    variation_threshold: float = _env_float("SEMANTIC_CACHE_VARIATION_THRESHOLD", 0.60)
    seed_variations: bool = _env_bool("SEMANTIC_CACHE_SEED_VARIATIONS", True)
    max_query_chars: int = _env_int("MAX_QUERY_CHARS", 2000)
    llm_cost_per_call_usd: float = _env_float("LLM_COST_PER_CALL_USD", 0.0004)
    relevance_llm_timeout_seconds: float = _env_float("RELEVANCE_LLM_TIMEOUT_SECONDS", 5.0)
    relevance_llm_on_cache_hit: bool = _env_bool("RELEVANCE_LLM_ON_CACHE_HIT", False)


settings = Settings()
