import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.troubleshoot import router
from backend.services import cache, telemetry
from backend.services.contract_validator import catalog_by_deeplink
from backend.services.query_processor import _get_m2_engine
from backend.services.text_similarity import catalog_idf

logger = logging.getLogger("m3")
_ready = threading.Event()


def warm_up() -> None:
    if _ready.is_set():
        return
    _get_m2_engine()
    catalog_by_deeplink()
    catalog_idf()
    _ready.set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    warm_up()
    yield


app = FastAPI(title="Smart Guided Troubleshooting Engine", lifespan=lifespan)
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
    return {"pipeline": telemetry.metrics.snapshot(), "cache": cache.stats()}
