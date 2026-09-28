import difflib
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from backend.config import BASE_DIR, settings
from backend.services import telemetry
from backend.services.text_similarity import _base_normalize

logger = logging.getLogger("m3")
PROMPT_PATH = BASE_DIR / "prompts" / "relevance_prompt.txt"

TYPO_CUTOFF = 0.85
MODEL_NAME = re.compile(r"\b(?:[asmzf]\d{1,2}|note\s?\d{1,2}|tab\s?[as]\d*)\b")

DEVICE_TERMS = {
    "battery", "batt", "charger", "charging", "recharge", "screen", "display", "touchscreen",
    "amoled", "brightness", "camera", "selfie", "lens", "autofocus", "shutter", "wifi", "bluetooth",
    "hotspot", "nfc", "sim", "esim", "cellular", "earbuds", "buds", "speaker", "speakers",
    "microphone", "mic", "earpiece", "headphones", "headset", "ringtone", "vibration", "vibrate",
    "notification", "notifications", "storage", "sd card", "micro sd", "safe mode", "reboot",
    "lock screen", "fingerprint", "face unlock", "firmware", "software update", "smart switch",
    "smart view", "qr code", "kids home", "dark mode", "always on display", "wallpaper", "keyboard",
    "overheat", "overheats", "overheating", "touchscreen", "airplane mode", "mobile data",
    "power saving", "battery saver", "home screen", "app", "apps", "settings", "gps", "location",
    "font", "volume", "usb", "charge", "flashlight", "torch", "widget", "widgets", "bixby",
    "one ui", "android", "ram", "hdr", "pixels", "cover screen", "signal", "network", "internet",
    "application", "applications", "touch", "tap", "floating", "shortcut", "assistant menu",
    "no sound", "whatsapp", "instagram", "aps", "wify", "loudspeaker", "boot loop", "bootloop",
}

CONTEXT_TERMS = {
    "phone", "device", "galaxy", "samsung", "tablet", "smartphone", "mobile", "handset", "watch",
    "fold", "flip", "cellphone", "texting", "browsing", "calls", "caller", "callers", "button",
    "buttons",
}

SYMPTOM_TERMS = {
    "drain", "drains", "draining", "dies", "dying", "hot", "warm", "blank", "black", "dark",
    "flicker", "flickers", "flickering", "flash", "flashes", "flashing", "crack", "cracked",
    "slow", "lag", "lags", "laggy", "lagging", "freeze", "freezes", "freezing", "frozen", "froze",
    "hang", "hangs", "crash", "crashes", "crashing", "stutter", "stuck", "unresponsive", "blurry",
    "blur", "quiet", "muffled", "distorted", "disconnect", "disconnects", "disconnecting",
    "restart", "restarts", "restarting", "boot", "update", "reset", "full", "broken",
    "not working", "stopped working", "won't", "wont", "can't", "cant", "doesn't", "doesnt",
    "keeps", "error", "fails", "failed", "issue", "problem", "glitch", "bug", "sound", "audio",
    "internet", "data", "connect", "connection", "pair", "pairing", "photo", "photos", "picture",
    "pictures", "video", "zoom", "focus", "memory", "space", "password", "pin", "security",
    "transfer", "power", "turn on", "turn off", "enable", "disable", "heat", "heats", "heating",
    "latency", "delay", "closing", "terminate", "terminates", "unexpectedly", "respond", "responds",
}


@lru_cache(maxsize=1)
def _patterns() -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    def build(terms: set[str]) -> re.Pattern:
        alternatives = sorted((re.escape(t) for t in terms), key=len, reverse=True)
        return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b")
    return build(DEVICE_TERMS), build(CONTEXT_TERMS), build(SYMPTOM_TERMS)


@lru_cache(maxsize=1)
def _vocabulary() -> tuple[str, ...]:
    return tuple(sorted(t for t in DEVICE_TERMS | CONTEXT_TERMS | SYMPTOM_TERMS if " " not in t and len(t) > 3))


@lru_cache(maxsize=4096)
def _correct(word: str) -> str:
    if len(word) < 5:
        return word
    match = difflib.get_close_matches(word, _vocabulary(), n=1, cutoff=TYPO_CUTOFF)
    return match[0] if match else word


def _normalize(query: str) -> str:
    text = (query or "").lower().replace("’", "'")
    words = _base_normalize(text).split()
    return " ".join([text.replace("wi-fi", "wifi")] + [_correct(w) for w in words])


def is_device_query(query: str) -> bool:
    device, context, symptom = _patterns()
    text = _normalize(query)
    if device.search(text):
        return True
    symptoms = {m.group(0) for m in symptom.finditer(text)}
    return bool((context.search(text) or MODEL_NAME.search(text)) and symptoms)



def keyword_relevant(query: str) -> bool:
    from backend.services.config_planner import match

    return is_device_query(query) or match(query) is not None

@lru_cache(maxsize=1)
def _prompt() -> str:
    return Path(PROMPT_PATH).read_text(encoding="utf-8")


def _ask_llm(query: str) -> str:
    from backend.services.llm_guard import chat_json

    return chat_json(
        [{"role": "user", "content": _prompt().replace("{user_query}", query)}],
        temperature=0,
        max_tokens=20,
        cap=settings.relevance_llm_timeout_seconds,
    )


def _parse_verdict(content: str) -> bool:
    import json_repair

    data = json_repair.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get("relevant"), bool):
        raise ValueError(f"unexpected relevance verdict: {content!r}")
    return data["relevant"]


@lru_cache(maxsize=2048)
def _llm_verdict(normalized_query: str) -> bool:
    return _parse_verdict(_ask_llm(normalized_query))


def check_relevance(query: str) -> bool:
    trace = telemetry.current()
    if telemetry.llm_provider_configured():
        try:
            verdict = _llm_verdict(" ".join(query.split()))
            trace.relevance = "llm"
            return verdict
        except Exception as exc:
            trace.errors.append(f"relevance_llm: {exc!r}")
            logger.warning("request %s relevance llm failed, using keywords: %r", trace.request_id, exc)
    trace.relevance = "keywords"
    return keyword_relevant(query)
