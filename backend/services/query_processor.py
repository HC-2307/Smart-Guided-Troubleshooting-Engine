from pathlib import Path
from typing import Optional

from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import generate_troubleshooting_plan
from backend.services.m2_engine import M2Engine

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = BASE_DIR / "data" / "deeplinks.json"

_m2_engine: Optional[M2Engine] = None


def _get_m2_engine() -> M2Engine:
    global _m2_engine
    if _m2_engine is None:
        _m2_engine = M2Engine(CATALOG_PATH)
    return _m2_engine


def process_query(query: str, siis_response: Optional[dict] = None) -> dict:
    enriched_query = enrich_query(query)

    troubleshooting_plan = generate_troubleshooting_plan(
        enriched_query, siis_response
    )

    resolved_plan, _report = _get_m2_engine().process_plan(troubleshooting_plan)

    resolved_plan["fallback"] = None if resolved_plan.get("contexts") else "no_match"
    return resolved_plan
