import json
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

FREE_TIER_PATH = BASE_DIR / "backend" / "free_tier.json"
LLM_VARS = ("OPENAI_API_KEY", "GEMINI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL", "LLM_EXTRA_BODY", "LLM_REASONING_EFFORT")


def apply_llm_provider(path: Path = FREE_TIER_PATH) -> str:
    for name in LLM_VARS:
        if name in os.environ and not os.environ[name].strip():
            del os.environ[name]
    if os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "own_key"
    if os.getenv("LLM_FREE_TIER", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return "offline"
    try:
        free_tier = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "offline"
    if not free_tier.get("OPENAI_API_KEY"):
        return "offline"
    os.environ.update({name: str(value) for name, value in free_tier.items() if value})
    os.environ.setdefault("LLM_COST_PER_CALL_USD", "0")
    return "free_tier"


LLM_PROVIDER = apply_llm_provider()


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
    reference_match_threshold: float = _env_float("SEMANTIC_CACHE_REFERENCE_THRESHOLD", 0.75)
    seed_variations: bool = _env_bool("SEMANTIC_CACHE_SEED_VARIATIONS", True)
    max_query_chars: int = _env_int("MAX_QUERY_CHARS", 2000)
    llm_cost_per_call_usd: float = _env_float("LLM_COST_PER_CALL_USD", 0.0004)
    relevance_llm_timeout_seconds: float = _env_float("RELEVANCE_LLM_TIMEOUT_SECONDS", 5.0)
    relevance_llm_on_cache_hit: bool = _env_bool("RELEVANCE_LLM_ON_CACHE_HIT", False)
    embeddings_enabled: bool = _env_bool("EMBEDDINGS_ENABLED", True)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    embedding_cache_dir: Path = Path(os.getenv("EMBEDDING_CACHE_DIR", str(BASE_DIR / ".cache" / "embeddings")))
    dense_min_score: float = _env_float("DENSE_MIN_SCORE", 0.74)
    dense_min_gap: float = _env_float("DENSE_MIN_GAP", 0.0)
    semantic_relevance_enabled: bool = _env_bool("SEMANTIC_RELEVANCE_ENABLED", True)
    semantic_relevance_margin: float = _env_float("SEMANTIC_RELEVANCE_MARGIN", 0.0)
    cache_persist_path: str = os.getenv("CACHE_PERSIST_PATH", str(BASE_DIR / ".cache" / "semantic_cache.json"))
    cache_persist_interval_seconds: float = _env_float("CACHE_PERSIST_INTERVAL_SECONDS", 5.0)
    cache_prewarm: bool = _env_bool("CACHE_PREWARM", True)
    llm_call_timeout_seconds: float = _env_float("LLM_CALL_TIMEOUT_SECONDS", 6.0)
    llm_request_budget_seconds: float = _env_float("LLM_REQUEST_BUDGET_SECONDS", 5.5)
    llm_min_call_seconds: float = _env_float("LLM_MIN_CALL_SECONDS", 1.0)
    llm_breaker_failures: int = _env_int("LLM_BREAKER_FAILURES", 2)
    llm_breaker_cooldown_seconds: float = _env_float("LLM_BREAKER_COOLDOWN_SECONDS", 60.0)
    coalesce_wait_seconds: float = _env_float("COALESCE_WAIT_SECONDS", 15.0)
    embedding_threads: int = _env_int("EMBEDDING_THREADS", 1)


settings = Settings()
