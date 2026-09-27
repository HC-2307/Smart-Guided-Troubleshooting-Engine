import copy
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from backend.services import telemetry
from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import generate_troubleshooting_plan
from backend.services.m2_engine import M2Engine

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = BASE_DIR / "data" / "deeplinks.json"
_RESOLUTION_MEMO_SIZE = 512

_m2_engine: Optional[M2Engine] = None
_resolution_memo: "OrderedDict[str, dict]" = OrderedDict()
_memo_lock = threading.Lock()


def _get_m2_engine() -> M2Engine:
    global _m2_engine
    if _m2_engine is None:
        _m2_engine = M2Engine(CATALOG_PATH)
    return _m2_engine


def resolve_plan(plan: dict) -> dict:
    key = json.dumps(plan, sort_keys=True, default=str)
    with _memo_lock:
        if key in _resolution_memo:
            _resolution_memo.move_to_end(key)
            return copy.deepcopy(_resolution_memo[key])

    resolved, _report = _get_m2_engine().process_plan(copy.deepcopy(plan))

    with _memo_lock:
        _resolution_memo[key] = copy.deepcopy(resolved)
        while len(_resolution_memo) > _RESOLUTION_MEMO_SIZE:
            _resolution_memo.popitem(last=False)
    return resolved


def process_query(query: str, siis_response: Optional[dict] = None) -> dict:
    with telemetry.stage("enrich"):
        enriched_query = enrich_query(query)

    with telemetry.stage("plan"):
        troubleshooting_plan = generate_troubleshooting_plan(enriched_query, siis_response)

    with telemetry.stage("resolve"):
        resolved_plan = resolve_plan(troubleshooting_plan)

    resolved_plan["fallback"] = None if resolved_plan.get("contexts") else "no_match"
    return resolved_plan
