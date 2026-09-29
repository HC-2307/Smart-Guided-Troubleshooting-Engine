import copy
import difflib
import json
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from backend.services import telemetry
from backend.services.config_planner import build_plan
from backend.services.query_enrichment import DOMAIN_KEYWORDS, enrich_query
from backend.services.text_similarity import CONCEPT_PHRASES, CONCEPT_WORDS, _base_normalize, _known_words
from backend.services.troubleshooting_engine import find_matching_siis, generate_troubleshooting_plan
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


_TOPIC_WORDS = [k for ks in DOMAIN_KEYWORDS.values() for k in ks] + ["app", "application"]
_TOPIC_WORDS += [w for c, ws in CONCEPT_WORDS.items() if c != "fail" for w in ws]
_TOPIC_WORDS += [p for c, ps in CONCEPT_PHRASES.items() if c not in {"turnon", "turnoff"} for p in ps]
_TOPIC_VOCAB = sorted({w for w in _TOPIC_WORDS if " " not in w and len(w) > 3})
TOPIC_TYPO_CUTOFF = 0.8
_DOMAIN_PATTERN = re.compile(
    r"\b(?:" + "|".join(sorted(map(re.escape, _TOPIC_WORDS), key=len, reverse=True)) + r")(?:s|es|ed|ing|er|y)?\b"
)
TOPIC_TYPO_MIN_LENGTH = 5


def _strict_correct(word: str) -> str:
    if len(word) < TOPIC_TYPO_MIN_LENGTH or word in _known_words():
        return word
    match = difflib.get_close_matches(word, _TOPIC_VOCAB, n=1, cutoff=TOPIC_TYPO_CUTOFF)
    return match[0] if match else word


def has_topic_evidence(query: str) -> bool:
    lowered = (query or "").lower().replace("wi-fi", "wifi")
    corrected = " ".join(_strict_correct(w) for w in _base_normalize(lowered).split())
    return bool(_DOMAIN_PATTERN.search(lowered) or _DOMAIN_PATTERN.search(corrected))


def no_context_response() -> dict:
    return {"contexts": [], "query_variations": None, "fallback": "no_siis_context"}


def process_query(query: str, siis_response: Optional[dict] = None) -> dict:
    trace = telemetry.current()
    reference = siis_response
    if siis_response is None:
        with telemetry.stage("config_plan"):
            config_plan = build_plan(query)
        if config_plan is not None:
            trace.planner, trace.grounding = "catalog", "catalog"
            return config_plan
        reference = find_matching_siis(query)
        if reference is None and not has_topic_evidence(query):
            trace.planner = "none"
            return no_context_response()
    trace.planner = "m1"
    trace.grounding = "reference" if reference else "domain"

    with telemetry.stage("enrich"):
        enriched_query = enrich_query(query)

    with telemetry.stage("plan"):
        troubleshooting_plan = generate_troubleshooting_plan(enriched_query, siis_response)

    with telemetry.stage("resolve"):
        resolved_plan = resolve_plan(troubleshooting_plan)

    resolved_plan["fallback"] = None if resolved_plan.get("contexts") else "no_match"
    return resolved_plan
