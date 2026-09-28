import json
import logging
import re

from backend.schemas.troubleshoot import TroubleshootResponse
from backend.config import BASE_DIR, settings
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
