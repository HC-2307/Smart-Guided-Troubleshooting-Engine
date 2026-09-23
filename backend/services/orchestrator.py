from backend.schemas.troubleshoot import TroubleshootResponse
from backend.services import cache
from backend.services.query_processor import process_query
from backend.services.validator import check_no_url_leakage


def troubleshoot(query: str, siis_response: dict | None = None) -> TroubleshootResponse:
    cached = cache.get(query)
    if cached is not None:
        return TroubleshootResponse(**cached)

    plan = process_query(query, siis_response)
    response = TroubleshootResponse(**plan)

    # Final safety gate: never let a leaked URL reach the client, even if
    # something upstream (LLM plan or catalog match) slipped one in.
    if check_no_url_leakage(response):
        response = TroubleshootResponse(contexts=[], fallback="validation_failed")

    cache.set(query, response.model_dump())
    return response
