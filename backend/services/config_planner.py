import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from backend.config import CATALOG_PATH, settings
from backend.services.catalog_index import dense_index
from backend.services.catalog_validator import load_catalog
from backend.services.contract_validator import MINOR_WORDS, entry_polarity, polarity

MIN_COVERAGE = 0.6
MIN_EVIDENCE = 4.0
MIN_MARGIN = 0.15
FIELD_WEIGHTS = {"key": 3.0, "message": 2.0, "description": 1.5, "qna": 1.0}

SYNONYMS = {
    "hrs": "hour", "hr": "hour", "hours": "hour", "clock": "time", "wi": "wifi", "fi": "wifi",
    "text": "font", "letters": "font", "rotate": "rotation", "rotating": "rotation", "rotates": "rotation",
    "percent": "percentage", "tone": "ringtone", "ringer": "ringtone", "lockscreen": "lock",
    "automatically": "automatic", "auto": "automatic", "nightmode": "dark", "night": "dark",
}

STOPWORDS = {
    "a", "an", "the", "my", "i", "me", "is", "are", "was", "it", "its", "and", "or", "to", "of", "on", "in",
    "at", "for", "with", "how", "do", "does", "can", "could", "please", "want", "wanna", "need", "would",
    "like", "phone", "device", "galaxy", "samsung", "mobile", "tablet", "setting", "settings", "page",
    "open", "opens", "view", "via", "enable", "enables", "disable", "disables", "turn", "switch", "change",
    "set", "sets", "make", "get", "show", "shows", "use", "uses", "off", "this", "that", "be", "so", "what",
    "where", "which", "there", "you", "your", "from", "by", "up", "into", "when", "specified", "value",
    "update", "updates", "adjust", "adjusts", "configure", "configures", "option", "options", "help", "find",
    "who", "whom", "whose", "why", "increase", "decrease", "bigger", "larger", "smaller", "higher", "lower",
    "longer", "shorter", "more", "less", "should", "will", "just", "now", "currently", "always",
}

MALFUNCTION = re.compile(
    r"\b(crash\w*|freez\w*|frozen|drain\w*|dies|dying|dead|broken|break\w*|crack\w*|blank|flicker\w*|stuck|"
    r"lag\w*|slow\w*|hot|heat\w*|overheat\w*|error\w*|fail\w*|won'?t|can'?t|cannot|doesn'?t|isn'?t|not working|"
    r"stopped|keeps|disconnect\w*|glitch\w*|bug\w*|blurr?y|no sound|problem\w*|issue\w*|restart\w*|reboot\w*|"
    r"damage\w*|water|wet|swollen|noise|distort\w*|unresponsive|(?<!do )not)\b"
)

REQUEST = re.compile(
    r"\b(turn|switch|change|set|make|show|hide|use|enable|disable|activate|deactivate|increase|decrease|"
    r"adjust|put|pick|choose|select|allow|stop|start|keep|silence|mute|unmute|want|wanna|how do i|how to|"
    r"how can i|where is|where do i|let me|can i|i'd like|i would like)\b"
)

VERB_PREFIXES = {"switch", "view", "enable", "disable", "adjust", "check", "increase", "decrease", "set", "use",
                 "show", "turn", "open"}
TRAILING_WORDS = MINOR_WORDS | {"your", "their", "its", "between", "about", "when", "while", "so", "that"}


def _stem(word: str) -> str:
    for suffix in ("ing", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower().replace("wi-fi", "wifi"))
    return [_stem(SYNONYMS.get(w, w)) for w in words if w not in STOPWORDS and SYNONYMS.get(w, w) not in STOPWORDS]


@dataclass(frozen=True)
class Match:
    entry: dict
    score: float
    evidence: float
    margin: float
    source: str = "keyword"


def _usable(entry: dict) -> bool:
    message = (entry.get("message") or "").strip()
    if "device settings" not in (entry.get("description") or "").lower():
        return False
    if message.lower() in {"onurl", "offurl"} or entry.get("originalType") not in {"onURL", "offURL", "onClickURL", "updateURL"}:
        return False
    named, actual = polarity(message), entry_polarity(entry)
    return not (named and actual and named != actual)


def _key(entry: dict) -> str:
    return ((entry.get("validation") or {}).get("key") or "").strip()


@lru_cache(maxsize=1)
def _index() -> tuple[list[dict], list[dict[str, float]], dict[str, float], list[set[str]]]:
    entries = [e for e in load_catalog(CATALOG_PATH) if _usable(e)]
    labels = [set(tokens(_key(e)) or tokens(e.get("message"))) for e in entries]
    fields = []
    for e in entries:
        weights: dict[str, float] = {}
        for name, text in (("key", _key(e)), ("message", e.get("message")), ("description", e.get("description")),
                           ("qna", e.get("qna_description"))):
            for t in tokens(text):
                weights[t] = max(weights.get(t, 0.0), FIELD_WEIGHTS[name])
        fields.append(weights)
    df = Counter(t for w in fields for t in w)
    idf = {t: math.log((1 + len(entries)) / (1 + n)) + 1 for t, n in df.items()}
    return entries, fields, idf, labels


def entry_text(entry: dict) -> str:
    return f"{_key(entry)}. {entry.get('message') or ''}. {entry.get('description') or ''} {entry.get('qna_description') or ''}"


def ensure_dense_index() -> bool:
    if dense_index.status == "not_loaded":
        entries = _index()[0]
        dense_index.build(entries, [entry_text(e) for e in entries])
    return dense_index.ready


def _dense_match(query: str) -> Optional[Match]:
    if not REQUEST.search((query or "").lower()) or not ensure_dense_index():
        return None
    results = dense_index.search(query, k=20)
    if not results:
        return None
    best_score, best = results[0]
    feature = _feature(best)
    runner_up = next((sc for sc, e in results if _feature(e) != feature), 0.0)
    margin = best_score - runner_up
    if best_score < settings.dense_min_score or margin < settings.dense_min_gap:
        return None
    candidates = [e for e in _index()[0] if _feature(e) == feature]
    chosen = _pick_by_polarity(candidates, polarity(query))
    if chosen is None:
        return None
    return Match(chosen, round(best_score, 4), 0.0, round(margin, 4), "dense")


def _feature(entry: dict) -> str:
    return _key(entry).lower() or entry["message"].lower()


def _pick_by_polarity(candidates: list[dict], wanted: Optional[str]) -> Optional[dict]:
    same = [e for e in candidates if wanted and entry_polarity(e) == wanted]
    neutral = [e for e in candidates if entry_polarity(e) is None]
    return (same or neutral or [None])[0]


def match(query: str, dense: bool = True) -> Optional[Match]:
    if MALFUNCTION.search((query or "").lower()):
        return None
    found = _keyword_match(query)
    if found is None and dense:
        found = _dense_match(query)
    return found


def _keyword_match(query: str) -> Optional[Match]:
    q_tokens = list(dict.fromkeys(tokens(query)))
    if not q_tokens:
        return None
    entries, fields, idf, labels = _index()
    unseen = max(idf.values())
    total = sum(idf.get(t, unseen) for t in q_tokens) * max(FIELD_WEIGHTS.values())
    scored = []
    for entry, weights, label in zip(entries, fields, labels):
        hits = [t for t in q_tokens if t in weights]
        if not label & set(hits):
            continue
        evidence = sum(idf[t] * weights[t] for t in hits)
        precision = len(label & set(hits)) / len(label)
        scored.append((evidence / total * (0.5 + 0.5 * precision), evidence, entry))
    if not scored:
        return None
    scored.sort(key=lambda s: -s[0])
    best_score, best_ev, best = scored[0]
    feature = _feature(best)
    same_feature = [e for sc, _, e in scored if sc >= best_score - 1e-9 and _feature(e) == feature]
    runner_up = next((sc for sc, _, e in scored if _feature(e) != feature), 0.0)
    margin = best_score - runner_up
    if best_score < MIN_COVERAGE or best_ev < MIN_EVIDENCE or margin < MIN_MARGIN:
        return None
    chosen = _pick_by_polarity(same_feature, polarity(query))
    if chosen is None:
        return None
    return Match(chosen, round(best_score, 4), round(best_ev, 4), round(margin, 4))


def _base_verb(word: str) -> str:
    lower = word.lower()
    if lower.endswith("ies") and len(lower) > 4:
        return lower[:-3] + "y"
    if lower.endswith(("ches", "shes", "sses", "xes", "zes")):
        return lower[:-2]
    if lower.endswith("s") and not lower.endswith("ss"):
        return lower[:-1]
    return lower


def _describe(entry: dict) -> Optional[str]:
    for source in (entry.get("qna_description"), entry.get("description")):
        words = re.sub(r"\s+", " ", (source or "").strip().rstrip(".")).split()
        if not words:
            continue
        index = 1 if words[0].lower().endswith("ly") and len(words) > 1 else 0
        words[index] = _base_verb(words[index])
        words[0] = words[0].lower()
        body = words[:5]
        while body and body[-1].lower().strip(",") in TRAILING_WORDS:
            body.pop()
        body = [w.strip(",") for w in body]
        if len(body) >= 3:
            return "It will " + " ".join(body)
    return None


def _label_words(entry: dict) -> list[str]:
    words = (_key(entry) or entry.get("message") or "").split()
    while len(words) > 1 and words[0].lower() in VERB_PREFIXES:
        words.pop(0)
    return words


def _title_case(words: list[str]) -> str:
    return " ".join(w.lower() if i and w.lower() in MINOR_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


def _sentence_case(words: list[str]) -> str:
    text = " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in words)
    return text[:1].upper() + text[1:]


def _title(words: list[str]) -> str:
    chosen = words[:2] + ["settings"] if len(words) <= 2 else words[:3]
    while len(chosen) > 2 and chosen[-1].lower() in MINOR_WORDS:
        chosen.pop()
    if len(chosen) < 2:
        chosen = chosen + ["settings"]
    return _sentence_case(chosen)


def _action_name(entry: dict) -> str:
    message, key = entry.get("message") or "", _key(entry)
    if not key or set(tokens(message)) & set(tokens(key)):
        return _title_case(message.split())
    prefix = {"on": ["Turn", "On"], "off": ["Turn", "Off"]}.get(entry_polarity(entry) or "", ["Open"])
    return _title_case(prefix + _label_words(entry))


def _steps(entry: dict) -> list[str]:
    key, kind = _key(entry), entry.get("originalType")
    page = re.match(r"opens the (.+?) page in device settings", (entry.get("description") or "").lower())
    if kind == "onURL":
        return [f"Turn on {key}."]
    if kind == "offURL":
        return [f"Turn off {key}."]
    if kind == "updateURL":
        return [f"Open {key}.", f"Set {key} to the value you want."]
    steps = [f"Open the {page.group(1)} page."] if page else [f"Open {key}."]
    if key and page and key.lower() not in page.group(1):
        steps.append(f"Tap {key}.")
    return steps


def _variations(topic: str, wanted: Optional[str]) -> list[str]:
    action = {"on": "turn on", "off": "turn off"}.get(wanted or "", "change")
    return [
        f"How do I {action} {topic} on my Galaxy?",
        f"{topic} settings",
        f"Where is the {topic} setting on my phone?",
        f"I want to {action} {topic}",
        f"open {topic} settings",
        f"Can you help me {action} {topic} on Samsung?",
        f"Galaxy {topic} option",
        f"need to {action} {topic} on my phone",
        f"{action} {topic} please",
    ]


def build_plan(query: str) -> Optional[dict]:
    found = match(query)
    if found is None:
        return None
    entry = found.entry
    description = _describe(entry)
    words = _label_words(entry)
    if description is None or not words:
        return None
    while len(words) > 1 and words[-1].lower() == "settings":
        words = words[:-1]
    topic = " ".join(words)
    link = {f: entry.get(f) for f in ("deeplink", "description", "message", "originalType")}
    critical = bool(re.search(r"\breset\b|\berase\b", (entry.get("message") or "").lower()))
    return {
        "contexts": [{
            "goal": f"Follow these steps to perform this {_title_case(words[:4])} Configuration",
            "title": _title(words),
            "score": round(min(found.score, 1.0), 2),
            "actions": [{
                "actionName": _action_name(entry),
                "description": description,
                "stepGroups": [{
                    "steps": _steps(entry),
                    "actionableDeeplink": link,
                    "validationDeeplink": entry.get("validation"),
                }],
                "category": "critical" if critical else "auto",
            }],
        }],
        "query_variations": _variations(topic.lower(), polarity(query)),
        "fallback": None,
    }
