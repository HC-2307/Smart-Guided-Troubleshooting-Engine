import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.troubleshoot import router
from backend.config import LLM_PROVIDER, settings
from backend.services import cache, llm_guard, telemetry
from backend.services.catalog_index import dense_index
from backend.services.config_planner import ensure_dense_index
from backend.services.contract_validator import catalog_by_deeplink
from backend.services.orchestrator import prewarm
from backend.services.query_processor import _get_m2_engine
from backend.services.relevance import semantic_relevant
from backend.services.text_similarity import catalog_idf

logger = logging.getLogger("m3")
_ready = threading.Event()
_warm_lock = threading.Lock()
startup_report: dict = {}


def warm_up() -> None:
    with _warm_lock:
        if _ready.is_set():
            return
        _get_m2_engine()
        catalog_by_deeplink()
        catalog_idf()
        ensure_dense_index()
        semantic_relevant("warm up")
        if settings.cache_persist_path:
            startup_report["cache_loaded"] = cache.load()
        if settings.cache_prewarm:
            startup_report["prewarm"] = prewarm()
        _ready.set()


def persist_cache() -> None:
    if not settings.cache_persist_path or not cache.is_dirty():
        return
    try:
        cache.save()
    except OSError as exc:
        logger.warning("cache save failed: %r", exc)


def _persist_loop(stop: threading.Event) -> None:
    while not stop.wait(settings.cache_persist_interval_seconds):
        persist_cache()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("uvicorn.error").info("LLM provider: %s (%s)", LLM_PROVIDER, os.getenv("LLM_MODEL", "gpt-4o-mini") if LLM_PROVIDER != "offline" else "no LLM")
    warm_up()
    stop = threading.Event()
    writer = threading.Thread(target=_persist_loop, args=(stop,), daemon=True)
    writer.start()
    yield
    stop.set()
    writer.join(timeout=5)
    persist_cache()


app = FastAPI(title="Smart Guided Troubleshooting Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Cache", "X-Pipeline-Ms", "X-LLM-Calls", "X-Est-Cost-USD", "X-Relevance", "X-Planner"],
)
app.include_router(router, prefix="/v1")


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    trace = telemetry.begin(request.headers.get("X-Request-ID"))
    try:
        response = await call_next(request)
    except Exception as exc:
        trace.errors.append(repr(exc))
        trace.fallback = "internal_error"
        logger.exception("request %s failed", trace.request_id)
        response = JSONResponse(status_code=500, content={"contexts": [], "fallback": "internal_error"})
    if request.url.path.startswith("/v1/troubleshoot") and response.status_code != 422:
        telemetry.metrics.record(trace)
    response.headers.update(trace.headers())
    telemetry.end()
    return response


@app.get("/health")
def health():
    try:
        warm_up()
    except Exception as exc:
        logger.exception("warm-up failed: %r", exc)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


@app.get("/v1/metrics")
def metrics():
    return {
        "pipeline": telemetry.metrics.snapshot(),
        "cache": cache.stats(),
        "dense_index": dense_index.status,
        "llm_guard": llm_guard.guard.state(),
        "startup": startup_report,
        "llm": {"provider": LLM_PROVIDER, "model": os.getenv("LLM_MODEL", "gpt-4o-mini") if LLM_PROVIDER != "offline" else None},
    }
