import json
import logging
import re
import threading

from backend.schemas.troubleshoot import TroubleshootResponse
from backend.config import BASE_DIR, settings
from backend.services import cache, telemetry
from backend.services.contract_validator import validate_and_repair
from backend.services.query_processor import process_query
from backend.services.relevance import check_relevance, offline_relevance
from backend.services.validator import check_no_url_leakage

logger = logging.getLogger("m3")


def _cache_lookup(query: str, trace: telemetry.RequestTrace):
    try:
        with telemetry.stage("cache_lookup"):
            return cache.lookup(query)
    except Exception as exc:
        trace.errors.append(f"cache_lookup: {exc!r}")
        logger.warning("request %s cache lookup failed: %r", trace.request_id, exc)
        return None


def _cache_store(query: str, response: TroubleshootResponse, trace: telemetry.RequestTrace) -> None:
    try:
        with telemetry.stage("cache_store"):
            cache.store(query, response.model_dump(), response.query_variations)
    except Exception as exc:
        trace.errors.append(f"cache_store: {exc!r}")
        logger.warning("request %s cache store failed: %r", trace.request_id, exc)


class _Flight:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.response: TroubleshootResponse | None = None
        self.trace: telemetry.RequestTrace | None = None


_flights: dict[str, _Flight] = {}
_flights_lock = threading.Lock()


def troubleshoot(query: str, siis_response: dict | None = None) -> TroubleshootResponse:
    if siis_response is not None:
        return _troubleshoot(query, siis_response)
    key = " ".join(query.lower().split())
    with _flights_lock:
        flight = _flights.get(key)
        leader = flight is None
        if leader:
            flight = _flights[key] = _Flight()
    if not leader:
        if flight.done.wait(settings.coalesce_wait_seconds) and flight.response is not None:
            trace = telemetry.current()
            for field in ("relevance", "planner", "fallback", "validation"):
                setattr(trace, field, getattr(flight.trace, field))
            trace.cache_tier = "coalesced"
            return flight.response.model_copy(deep=True)
        return _troubleshoot(query, None)
    try:
        flight.response = _troubleshoot(query, None)
        flight.trace = telemetry.current()
        return flight.response
    finally:
        flight.done.set()
        with _flights_lock:
            _flights.pop(key, None)


def _troubleshoot(query: str, siis_response: dict | None) -> TroubleshootResponse:
    trace = telemetry.current()

    hit = _cache_lookup(query, trace) if siis_response is None else None
    hit = hit if hit is not None and hit.response is not None else None
    if siis_response is None:
        fast_accept = False
        if hit is not None and not settings.relevance_llm_on_cache_hit:
            fast_accept, source = offline_relevance(query)
            if fast_accept:
                trace.relevance = source
        if not fast_accept and not check_relevance(query):
            trace.fallback = "no_match"
            return TroubleshootResponse(contexts=[], fallback="no_match")

    if hit is not None:
        trace.cache_tier, trace.cache_score = hit.tier, hit.score
        return TroubleshootResponse(**hit.response)

    with telemetry.stage("pipeline"):
        plan = process_query(query, siis_response)

    with telemetry.stage("contract_validation"):
        repaired, report = validate_and_repair(plan)
    trace.validation = report.summary()
    response = TroubleshootResponse(**repaired)

    if check_no_url_leakage(response):
        response = TroubleshootResponse(contexts=[], fallback="validation_failed")

    trace.fallback = response.fallback
    if response.contexts and response.fallback is None:
        _cache_store(query, response, trace)
    return response


SIIS_PATH = BASE_DIR / "data" / "siis_responses.json"
_NUMBERING = re.compile(r"^\s*\d+[.)]\s*")


def _reference_queries() -> list[tuple[str, dict]]:
    payload = json.loads(SIIS_PATH.read_text(encoding="utf-8"))
    return [
        (_NUMBERING.sub("", item["original_query"]).strip(), item["siis_response"])
        for item in payload.get("responses", [])
        if item.get("original_query") and item.get("siis_response")
    ]


def prewarm() -> dict:
    report = {"built": 0, "skipped": 0, "failed": 0}
    try:
        references = _reference_queries()
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("cache pre-warm skipped, reference file unreadable: %r", exc)
        return report
    for query, siis in references:
        if cache.contains(query):
            report["skipped"] += 1
            continue
        telemetry.begin()
        try:
            repaired, _ = validate_and_repair(process_query(query, siis))
            response = TroubleshootResponse(**repaired)
            if not response.contexts or check_no_url_leakage(response):
                report["failed"] += 1
                continue
            cache.store(query, response.model_dump(), response.query_variations, pinned=True)
            report["built"] += 1
        except Exception as exc:
            report["failed"] += 1
            logger.warning("cache pre-warm failed for %r: %r", query[:60], exc)
        finally:
            telemetry.end()
    return report
