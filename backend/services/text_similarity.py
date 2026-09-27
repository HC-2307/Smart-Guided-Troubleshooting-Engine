import difflib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.config import CATALOG_PATH

CONCEPT_PHRASES = {
    "drain": [
        "loses charge", "losing charge", "lose charge", "runs out", "running out",
        "dies fast", "dies quickly", "dying fast", "dying quickly", "power depletion",
        "battery life is short", "battery life short", "drops quickly", "drops fast",
    ],
    "chargefail": [
        "won't charge", "wont charge", "not charging", "doesn't charge", "doesnt charge",
        "does not charge", "stopped charging", "stops charging", "will not charge",
        "isn't charging", "isnt charging", "no charging", "can't charge", "cant charge",
    ],
    "blurry": ["out of focus", "not focusing", "won't focus", "wont focus", "can't focus", "no focus"],
    "nosound": ["no sound", "no audio", "can't hear", "cant hear", "not hearing"],
    "turnon": ["turn on", "switch on", "enable"],
    "turnoff": ["turn off", "switch off", "get rid of", "disable", "remove"],
    "mobiledata": ["mobile data", "cellular data", "cellular network"],
    "reset": ["factory reset", "wipe everything", "erase everything", "hard reset"],
    "blank": ["no image", "nothing on screen", "nothing shows", "shows nothing", "no display"],
    "storagefull": [
        "storage is full", "storage full", "storage almost full", "storage is almost full",
        "out of storage", "out of space", "no space", "running out of space", "free up storage",
    ],
}

CONCEPT_WORDS = {
    "drain": ["drain", "drains", "draining", "drained", "discharge", "discharges", "discharging", "depletes", "dying", "dies"],
    "hot": ["hot", "heat", "heats", "heating", "overheat", "overheats", "overheating", "warm", "burning"],
    "blank": ["blank", "black", "dark", "blackout"],
    "flicker": ["flicker", "flickers", "flickering", "flash", "flashes", "flashing", "blink", "blinks", "blinking", "strobe"],
    "screen": ["screen", "display", "touchscreen", "panel"],
    "lag": ["lag", "lags", "laggy", "lagging", "slow", "sluggish", "stutter", "stutters", "stuttering",
            "freeze", "freezes", "freezing", "frozen", "hang", "hangs", "hanging", "delay", "delayed"],
    "crash": ["crash", "crashes", "crashing"],
    "wifi": ["wifi", "wi-fi", "wlan"],
    "bluetooth": ["bluetooth", "earbuds", "buds"],
    "disconnect": ["disconnect", "disconnects", "disconnecting", "drops", "dropping", "unstable", "cuts"],
    "camera": ["camera", "cam", "lens"],
    "blurry": ["blurry", "blur", "blurred", "fuzzy", "hazy", "unfocused"],
    "photo": ["photo", "photos", "picture", "pictures", "pics", "shots", "images"],
    "sound": ["sound", "audio", "speaker", "speakers", "volume"],
    "crack": ["crack", "cracked", "shattered", "smashed"],
    "storage": ["storage", "space"],
    "charge": ["charge", "charging", "charger", "charged"],
    "battery": ["battery", "batt"],
    "update": ["update", "updates", "updating", "firmware"],
    "unresponsive": ["unresponsive"],
    "touch": ["touch", "tap", "taps", "tapping"],
    "connect": ["connect", "connects", "connecting", "connection", "pair", "pairs", "pairing", "paired"],
    "floating": ["floating", "float", "hovering", "hovers"],
    "fail": ["won't", "wont", "can't", "cant", "doesn't", "doesnt", "not", "never", "fail", "fails",
             "failed", "unable", "stopped", "isn't", "isnt"],
}

FACET_GROUPS = {
    "camera_side": {"front": ["front", "selfie"], "rear": ["rear", "back camera", "main camera"]},
    "fold_screen": {"inner": ["inner", "internal screen"], "outer": ["outer", "cover screen", "cover display"]},
    "radio": {"wifi": ["wifi", "wi-fi"], "bluetooth": ["bluetooth"], "mobiledata": ["mobile data", "cellular"], "nfc": ["nfc"]},
    "power_issue": {"drain": ["drain"], "chargefail": ["chargefail"]},
    "polarity": {"on": ["turnon"], "off": ["turnoff"]},
}

STOPWORDS = {
    "a", "an", "the", "my", "i", "me", "is", "are", "was", "it", "its", "it's", "and", "or", "to", "of",
    "on", "in", "at", "for", "with", "when", "whenever", "so", "but", "this", "that", "be", "been", "has",
    "have", "had", "do", "does", "did", "just", "really", "very", "super", "keeps", "keep", "always",
    "again", "also", "any", "some", "all", "every", "what", "why", "how", "can", "could", "please", "help",
    "phone", "device", "samsung", "galaxy", "mobile", "smartphone", "tablet", "ultra", "plus", "pro",
    "fold", "flip", "z", "gets", "get", "getting", "got", "too", "much", "after", "while", "since", "from",
    "up", "out", "like", "then", "than", "there", "here", "which", "who", "am", "im", "i'm", "you", "your",
    "issue", "problem", "problems", "quickly", "fast", "rapidly", "suddenly", "completely", "totally",
    "want", "need", "trying", "try", "even", "though", "although", "still", "way", "lot", "one", "no",
    "time", "times", "during", "use", "using", "used", "normal", "anything", "nothing", "all",
}

_NUMBERING = re.compile(r"^\s*\d+[\.\)]\s*")
_MODEL_TOKEN = re.compile(r"\b[a-z]?\d+[a-z]?\b")
_NON_WORD = re.compile(r"[^a-z0-9'\s]")
_SUFFIXES = ("ing", "ed", "es", "s", "ly")


@lru_cache(maxsize=1)
def _intent_vocabulary() -> tuple[str, ...]:
    words = set(_WORD_TO_CONCEPT)
    for phrases in CONCEPT_PHRASES.values():
        for phrase in phrases:
            words.update(phrase.split())
    for values in FACET_GROUPS.values():
        for cues in values.values():
            for cue in cues:
                words.update(cue.split())
    return tuple(sorted(w for w in words if len(w) > 2))


@lru_cache(maxsize=1)
def _known_words() -> frozenset[str]:
    words = set(_intent_vocabulary()) | STOPWORDS
    for text in _catalog_texts():
        words.update(_base_normalize(text).split())
    return frozenset(words)


@lru_cache(maxsize=4096)
def _correct(word: str) -> str:
    if len(word) < 4 or word.isdigit() or word in _known_words():
        return word
    match = difflib.get_close_matches(word, _intent_vocabulary(), n=1, cutoff=0.75)
    return match[0] if match else word


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _base_normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().replace("’", "'")
    text = _NUMBERING.sub("", text).strip().strip('"')
    text = text.replace("wi-fi", "wifi").replace("-", " ")
    return re.sub(r"\s+", " ", _NON_WORD.sub(" ", text)).strip()


_WORD_TO_CONCEPT = {w: c for c, words in CONCEPT_WORDS.items() for w in words}
_PHRASE_PATTERNS = sorted(
    ((p, c) for c, phrases in CONCEPT_PHRASES.items() for p in phrases),
    key=lambda pc: -len(pc[0]),
)


def canonical_tokens(text: str) -> list[str]:
    normalized = " ".join(_correct(w) for w in _base_normalize(text).split())
    for phrase, concept in _PHRASE_PATTERNS:
        normalized = re.sub(r"\b" + re.escape(phrase) + r"\b", f" _{concept} ", normalized)
    normalized = _MODEL_TOKEN.sub(" ", normalized)
    out: list[str] = []
    for word in normalized.split():
        if word.startswith("_"):
            out.append(word[1:])
        elif word in _WORD_TO_CONCEPT:
            out.append(_WORD_TO_CONCEPT[word])
        elif word not in STOPWORDS and len(word) > 1:
            out.append(_stem(word))
    return out


def facets(text: str) -> dict[str, set[str]]:
    normalized = " ".join(_correct(w) for w in _base_normalize(text).split())
    concepts = set(canonical_tokens(text))
    found: dict[str, set[str]] = {}
    for group, values in FACET_GROUPS.items():
        for value, cues in values.items():
            if any(cue in concepts or re.search(r"\b" + re.escape(cue) + r"\b", normalized) for cue in cues):
                found.setdefault(group, set()).add(value)
    return found


def facets_conflict(a: dict[str, set[str]], b: dict[str, set[str]]) -> bool:
    return any(group in b and a[group].isdisjoint(b[group]) for group in a)


def _char_trigrams(tokens: list[str]) -> set[str]:
    joined = f" {' '.join(tokens)} "
    return {joined[i:i + 3] for i in range(len(joined) - 2)}


@lru_cache(maxsize=1)
def _catalog_texts() -> tuple[str, ...]:
    try:
        payload = json.loads(Path(CATALOG_PATH).read_text(encoding="utf-8"))
        entries = payload.get("deeplinks", []) if isinstance(payload, dict) else payload
    except (OSError, ValueError):
        entries = []
    return tuple(" ".join(str(e.get(k) or "") for k in ("message", "description", "qna_description")) for e in entries)


@lru_cache(maxsize=1)
def catalog_idf() -> dict[str, float]:
    docs = [set(canonical_tokens(text)) for text in _catalog_texts()]
    n = max(len(docs), 1)
    df = Counter(t for doc in docs for t in doc)
    return {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}


_CONCEPTS = (set(CONCEPT_WORDS) | set(CONCEPT_PHRASES)) - {"fail"}
CONCEPT_WEIGHT = 3.0
MAX_TERM_WEIGHT = 2.0
UNSEEN_TERM_WEIGHT = 1.0


def _idf(token: str, table: dict[str, float]) -> float:
    if token in _CONCEPTS:
        return CONCEPT_WEIGHT
    return min(table.get(token, UNSEEN_TERM_WEIGHT), MAX_TERM_WEIGHT)


@dataclass(frozen=True)
class QueryFingerprint:
    text: str
    vector: dict[str, float]
    norm: float
    trigrams: frozenset[str]
    facets: dict[str, set[str]]


def fingerprint(text: str) -> QueryFingerprint:
    tokens = canonical_tokens(text)
    table = catalog_idf()
    vector = {t: c * _idf(t, table) for t, c in Counter(tokens).items()}
    norm = math.sqrt(sum(v * v for v in vector.values()))
    return QueryFingerprint(text, vector, norm, frozenset(_char_trigrams(tokens)), facets(text))


def similarity(a: QueryFingerprint, b: QueryFingerprint) -> float:
    if not a.norm or not b.norm:
        return 0.0
    cosine = sum(v * b.vector.get(k, 0.0) for k, v in a.vector.items()) / (a.norm * b.norm)
    union = a.trigrams | b.trigrams
    jaccard = len(a.trigrams & b.trigrams) / len(union) if union else 0.0
    return 0.75 * cosine + 0.25 * jaccard
