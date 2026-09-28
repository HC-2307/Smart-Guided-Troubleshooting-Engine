import logging

from backend.schemas.troubleshoot import TroubleshootResponse
from backend.config import settings
from backend.services import cache, telemetry
from backend.services.contract_validator import validate_and_repair
from backend.services.query_processor import process_query
from backend.services.relevance import check_relevance, keyword_relevant
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


def troubleshoot(query: str, siis_response: dict | None = None) -> TroubleshootResponse:
    trace = telemetry.current()

    hit = _cache_lookup(query, trace) if siis_response is None else None
    hit = hit if hit is not None and hit.response is not None else None
    if siis_response is None:
        fast_accept = hit is not None and not settings.relevance_llm_on_cache_hit and keyword_relevant(query)
        if fast_accept:
            trace.relevance = "keywords"
        elif not check_relevance(query):
            trace.fallback = "no_match"
            return TroubleshootResponse(contexts=[], fallback="no_match")

    if hit is not None:
        trace.cache_tier, trace.cache_score = hit.tier, hit.score
        return TroubleshootResponse(**hit.response)

    with telemetry.stage("pipeline"):
        plan = process_query(query, siis_response)
    if telemetry.llm_provider_configured() and trace.planner == "m1":
        trace.llm_calls += 2

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
