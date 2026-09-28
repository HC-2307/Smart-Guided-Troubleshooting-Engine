"""Stage 1: Query Enrichment and Normalization Service for Samsung Guided Troubleshooting Engine.

Converts colloquial, emotional, or ambiguous user complaints into normalized technical queries,
extracts domain, issue, and context entities, and generates 8-10 diverse register paraphrases.
Includes both live LLM calling capabilities and a 100% offline deterministic fallback engine.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.schemas.enriched_query import EnrichedQuery

logger = logging.getLogger(__name__)

# Base directory for prompt files
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"


def load_enrichment_prompt() -> str:
    """Load the enrichment prompt template."""
    prompt_path = PROMPTS_DIR / "enrichment_prompt.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


# Comprehensive domain keyword dictionary for deterministic classification
DOMAIN_KEYWORDS = {
    "battery": [
        "battery", "drain", "draining", "dies", "dying", "charge", "charging",
        "power", "overheat", "overheating", "hot", "warm", "percentage",
        "charger", "discharges", "drops quickly"
    ],
    "display": [
        "screen", "display", "blank", "black", "flicker", "flickering", "crack",
        "cracked", "touch", "touchscreen", "amoled", "pixels", "dark", "glass",
        "flashes", "flashing", "white screen", "green line", "distorted",
        "fold", "unresponsive touch", "laggy touch", "aspect ratio"
    ],
    "camera": [
        "camera", "photo", "picture", "lens", "blur", "blurry", "focus",
        "autofocus", "shutter", "zoom", "flash", "rear camera", "front camera"
    ],
    "performance": [
        "slow", "lag", "lagging", "laggy", "freeze", "freezing", "froze",
        "crash", "crashing", "stutter", "hang", "hanging", "app pair",
        "multi window", "unresponsive", "memory", "ram"
    ],
    "connectivity": [
        "wifi", "wi-fi", "bluetooth", "network", "cellular", "data", "sim",
        "signal", "internet", "smart switch", "qr code", "transfer", "airplay",
        "casting", "smart view", "mirroring"
    ],
    "audio": [
        "sound", "speaker", "audio", "mic", "microphone", "volume", "quiet",
        "distorted sound", "earpiece", "muffled"
    ],
    "storage": [
        "storage", "space", "full storage", "internal storage", "sd card",
        "micro sd", "clean storage"
    ],
    "system": [
        "update", "pin", "password", "safe mode", "boot", "reboot", "restart",
        "lock screen", "fingerprint", "security", "kids home"
    ],
}


def _classify_domain(query: str) -> str:
    """Classify the target device domain based on keyword frequency."""
    q_lower = query.lower()
    scores = {d: 0 for d in DOMAIN_KEYWORDS}
    for domain, kws in DOMAIN_KEYWORDS.items():
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", q_lower):
                scores[domain] += 2
            elif re.search(r"\b" + re.escape(kw), q_lower):
                scores[domain] += 1

    best_domain = max(scores, key=scores.get)
    return best_domain if scores[best_domain] > 0 else "system"


def _extract_context(query: str) -> List[str]:
    """Extract situational context modifiers from the query."""
    q_lower = query.lower()
    contexts = []
    context_patterns = {
        "device overheating": ["hot", "warm", "overheat", "overheating", "heats up"],
        "while charging": ["charger", "charging", "plugged in", "plug in"],
        "intermittent display flickering": ["flashes", "flashing", "flicker", "flickering"],
        "physical damage": ["crack", "cracked", "broken", "dropped", "damage"],
        "startup failure": ["won't turn on", "fails to start", "doesn't boot", "black screen"],
        "during data transfer": ["smart switch", "transfer data", "qr code"],
        "touch responsiveness delay": ["laggy", "delayed", "input delay", "slow touch"],
        "unresponsive screen": ["no image", "completely blank", "completely dark", "dark screen"],
        "app crash": ["crashes", "stops working", "force close"],
    }
    for ctx, kws in context_patterns.items():
        if any(kw in q_lower for kw in kws):
            contexts.append(ctx)
    return contexts[:3]


CONNECTIVITY_SUBTOPICS = [
    ("transfer", ["smart switch", "qr code", "transfer", "migration", "migrate"]),
    ("bluetooth", ["bluetooth", "earbuds", "headphones", "pairing", "pair"]),
    ("wifi", ["wifi", "wi-fi", "wi fi", "router", "hotspot"]),
    ("mobiledata", ["mobile data", "cellular", "sim", "signal", "4g", "5g", "lte", "no service"]),
]


def _topic_key(query: str, domain: str) -> str:
    """Refine the connectivity domain into the subtopic the user actually named."""
    if domain != "connectivity":
        return domain
    q_lower = query.lower()
    for topic, kws in CONNECTIVITY_SUBTOPICS:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", q_lower) for kw in kws):
            return topic
    return "network"


def _generate_deterministic_variations(query: str, domain: str, issue: str) -> List[str]:
    """Generate exactly 8 to 10 varied register paraphrases deterministically."""
    clean_q = re.sub(r'^[0-9]+[\.\)]\s*', '', query).strip().strip('"')

    variations_catalog = {
        "battery": [
            "My Galaxy phone battery drains unusually fast throughout the day.",
            "Why is my Samsung battery dying so quickly without heavy usage?",
            "Phone loses charge rapidly and the back panel becomes noticeably warm.",
            "Severe battery consumption problem causing premature shutdown.",
            "Battery percentage drops drastically within just a couple hours.",
            "Galaxy device experiencing rapid battery discharge and high thermal output.",
            "My battery won't stay charged and drains even when the phone is idle.",
            "Battery draining super fast, device feels hot to the touch.",
            "Extreme power depletion issue on Samsung Galaxy phone."
        ],
        "display": [
            "My Samsung phone display goes completely dark and does not respond.",
            "Screen flashes intermittently and then turns black without warning.",
            "The display panel is unresponsive and flickers when opening applications.",
            "Phone screen stays blank or black even though the device powers on.",
            "Encountering display flickering and intermittent blackout on Galaxy screen.",
            "Why does my phone screen keep turning dark and failing to show content?",
            "Touchscreen display malfunction with sudden blank screen behavior.",
            "Galaxy screen goes dark and shows no visual output upon waking up.",
            "Display panel intermittently blinks and stays completely black."
        ],
        "camera": [
            "The rear camera takes blurry pictures and cannot lock focus.",
            "Galaxy camera autofocus mechanism fails when taking close-up shots.",
            "Why are my smartphone photos constantly out of focus and hazy?",
            "Primary camera lens produces unfocused and blurry pictures.",
            "Camera app fails to adjust focal length resulting in blurred photos.",
            "Back camera blurry focus issue when attempting photography.",
            "Main camera focus problem causing all pictures to turn out fuzzy.",
            "Cannot get Samsung camera to focus properly on nearby objects.",
            "Camera optical focus error resulting in degraded image sharpness."
        ],
        "performance": [
            "Phone performance is noticeably laggy and applications respond slowly.",
            "Device experiences frequent frame drops and system interface stuttering.",
            "Why does my Galaxy phone freeze and take forever to open apps?",
            "System touch responsiveness is delayed causing significant interface lag.",
            "Smartphone interface lags and apps crash unexpectedly during navigation.",
            "Delayed touch input and slow app launching on Samsung device.",
            "Severe UI lag and system responsiveness latency across all applications.",
            "Phone hangs constantly and touch interactions take seconds to register.",
            "Device operating with heavy input delay and sluggish performance."
        ],
        "transfer": [
            "Device fails to establish stable wireless data transfer between phones.",
            "Smart Switch transfer cannot connect or scan the synchronization code.",
            "Why is my Galaxy tablet unable to transfer data wirelessly?",
            "Data transfer stalls and screen displays blank during synchronization.",
            "Wireless connection drops while attempting Smart Switch file migration.",
            "Unable to proceed with device data transfer over Wi-Fi connection.",
            "Connection between Samsung devices fails during initial data migration.",
            "Data transfer process encounters connection failure and blank screen.",
            "Interrupted wireless pairing preventing Smart Switch file transfer."
        ],
        "wifi": [
            "My Galaxy phone keeps disconnecting from Wi-Fi.",
            "Why does my Samsung phone drop the Wi-Fi connection so often?",
            "Wi-Fi connection is unstable and keeps cutting out.",
            "Phone connects to the wireless network but has no internet.",
            "Intermittent Wi-Fi connectivity loss on Samsung Galaxy device.",
            "Wi-Fi randomly turns off or fails to reconnect automatically.",
            "Can't stay connected to my home Wi-Fi network.",
            "Wireless LAN connection drops repeatedly during normal use.",
            "Wi-Fi signal keeps going in and out on my phone."
        ],
        "bluetooth": [
            "My phone won't connect to my Bluetooth earbuds.",
            "Why won't my Galaxy phone pair with Bluetooth devices?",
            "Bluetooth pairing fails with my headphones and speaker.",
            "Samsung device cannot discover nearby Bluetooth accessories.",
            "Bluetooth pairing request never completes on my phone.",
            "Unable to pair a Bluetooth device with my Galaxy phone.",
            "My Bluetooth accessory does not show up in the device list.",
            "Phone fails to establish a Bluetooth connection with new accessories.",
            "Bluetooth pairing error on Samsung Galaxy device."
        ],
        "mobiledata": [
            "Mobile data is not working on my Galaxy phone.",
            "Why does my Samsung phone show no signal or no service?",
            "Cellular data keeps dropping even with full signal bars.",
            "Phone cannot connect to the internet over mobile data.",
            "SIM card network connection is lost intermittently.",
            "Mobile network signal is weak and calls keep dropping.",
            "4G or 5G data connection is unavailable on my phone.",
            "Cellular connectivity failure on Samsung Galaxy device.",
            "My phone keeps losing mobile data connection."
        ],
        "network": [
            "My Galaxy phone keeps losing its network connection.",
            "Why can't my Samsung phone connect to the internet?",
            "Internet connection on my phone is unstable and drops out.",
            "Phone shows connected but pages and apps will not load.",
            "Intermittent network connectivity loss on Samsung Galaxy device.",
            "Unable to get online from my phone at all.",
            "Network connection keeps cutting out during normal use.",
            "Samsung device fails to maintain a stable internet connection.",
            "My phone has no internet access even though it is connected."
        ],
        "audio": [
            "My Galaxy phone speaker sounds distorted and crackly.",
            "Why is the sound on my Samsung phone so quiet?",
            "Audio output is muffled even at full volume.",
            "Phone speaker produces no sound during calls or media.",
            "Low and distorted audio output on Samsung Galaxy device.",
            "Volume is too low and the earpiece sounds unclear.",
            "Speaker crackles when playing music or videos.",
            "Microphone or speaker audio quality is noticeably poor.",
            "Sound keeps cutting out on my phone."
        ],
        "storage": [
            "My Galaxy phone says storage is almost full.",
            "Why is my Samsung phone running out of space?",
            "Internal storage is full and apps will not install.",
            "Not enough storage space to download updates or photos.",
            "Insufficient internal storage capacity on Samsung Galaxy device.",
            "Phone storage fills up quickly even after deleting files.",
            "Cannot save new photos because storage is full.",
            "Device memory is full and the phone is slowing down.",
            "How do I free up storage space on my phone?"
        ],
        "system": [
            "System software encounters unexpected error and fails to boot normally.",
            "Galaxy phone displays startup screen error and does not load the home interface.",
            "Device lock screen authentication issues preventing normal access.",
            "System settings application becomes unresponsive during configuration.",
            "Smartphone operating system reboots unexpectedly or enters boot loop.",
            "Unable to unlock Samsung device after system security restart.",
            "System interface stops responding and navigation buttons fail.",
            "Galaxy device system malfunction requiring troubleshooting reset.",
            "Device encounters critical system error during normal operation."
        ]
    }

    base_list = variations_catalog.get(_topic_key(query, domain), variations_catalog["system"])
    # Return 9 distinct paraphrases ensuring diversity
    return base_list[:9]


def _deterministic_enrichment(query: str) -> Dict[str, Any]:
    """Deterministic enrichment fallback when live LLM is unavailable."""
    domain = _classify_domain(query)
    contexts = _extract_context(query)

    issue_map = {
        "battery": "rapid battery drain and overheating",
        "display": "display blackout and intermittent flickering",
        "camera": "camera autofocus malfunction and blurry capture",
        "performance": "touch input latency and system sluggishness",
        "transfer": "data transfer synchronization failure",
        "wifi": "intermittent Wi-Fi connection loss",
        "bluetooth": "Bluetooth pairing and connection failure",
        "mobiledata": "mobile data and cellular signal loss",
        "network": "intermittent network connectivity loss",
        "audio": "speaker distortion and low audio output",
        "storage": "insufficient internal storage capacity",
        "system": "device startup malfunction and screen unresponsiveness",
    }
    topic = _topic_key(query, domain)
    issue = issue_map.get(topic, "device operation malfunction")

    technical_query_map = {
        "battery": "rapid battery drain accompanied by elevated thermal temperature",
        "display": "display panel intermittent blackout and visual output failure",
        "camera": "rear camera autofocus failure resulting in blurry imagery",
        "performance": "digitizer input delay and application performance latency",
        "transfer": "wireless data synchronization and device transfer failure",
        "wifi": "Wi-Fi connection instability and intermittent disconnection",
        "bluetooth": "Bluetooth pairing failure and unstable accessory connection",
        "mobiledata": "cellular data connection failure and mobile signal loss",
        "network": "network connectivity loss and internet access failure",
        "audio": "audio subsystem distortion and hardware speaker malfunction",
        "storage": "internal storage partition full causing app failure",
        "system": "system boot malfunction and OS unresponsive state",
    }
    technical_query = technical_query_map.get(topic, f"{domain} hardware and software malfunction")

    variations = _generate_deterministic_variations(query, domain, issue)

    return {
        "original_query": query,
        "technical_query": technical_query,
        "domain": domain,
        "issue": issue,
        "context": contexts,
        "query_variations": variations,
        "confidence": 0.95,
    }


def _call_llm_for_enrichment(query: str) -> Optional[Dict[str, Any]]:
    """Attempt calling an external LLM (OpenAI / Gemini / Ollama) if configured."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        prompt_template = load_enrichment_prompt()
        prompt = prompt_template.replace("{user_query}", query) if prompt_template else f"Normalize query: {query}"

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a Samsung Diagnostic AI. Return ONLY a valid JSON object."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=10
        )
        content = response.choices[0].message.content
        if content:
            import json_repair
            data = json_repair.loads(content)
            if isinstance(data, dict) and "domain" in data:
                return data
    except Exception as e:
        logger.warning(f"Live LLM enrichment call failed, using deterministic engine: {e}")

    return None


def enrich_query(query: str) -> Dict[str, Any]:
    """Main entrypoint for Stage 1 Query Enrichment.

    Args:
        query: Raw colloquial complaint from the user.

    Returns:
        Dictionary conforming to EnrichedQuery schema.
    """
    if not query or not query.strip():
        query = "Device malfunction"

    # 1. Attempt live LLM if API keys are configured
    llm_result = _call_llm_for_enrichment(query)
    if llm_result:
        try:
            # Ensure query variations count is between 8 and 10
            variations = llm_result.get("query_variations", [])
            if len(variations) < 8:
                fallback_vars = _generate_deterministic_variations(
                    query, llm_result.get("domain", "system"), llm_result.get("issue", "")
                )
                for var in fallback_vars:
                    if var not in variations:
                        variations.append(var)
                    if len(variations) >= 9:
                        break
                llm_result["query_variations"] = variations[:9]

            # Validate against Pydantic model
            validated = EnrichedQuery(**llm_result)
            return validated.model_dump()
        except Exception as e:
            logger.warning(f"LLM enrichment output validation failed: {e}. Falling back to deterministic engine.")

    # 2. High-precision deterministic fallback
    enriched = _deterministic_enrichment(query)
    validated = EnrichedQuery(**enriched)
    return validated.model_dump()
