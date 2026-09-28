"""Stage 2: Troubleshooting Engine Service for Samsung Guided Troubleshooting Engine.

Converts enriched technical queries (and optional Samsung SIIS internal knowledge documents)
into structured, ordered troubleshooting plans conforming strictly to Samsung PRISM Theme 02 schema.
Enforces strict 50-70 word descriptions starting with 'It will', 2-3 word titles, critical action ordering (last),
and zero hallucinated deeplinks.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.schemas.troubleshooting_plan import (
    Action,
    ActionCategory,
    Goal,
    StepGroup,
    TroubleshootingPlan,
)

logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR = BASE_DIR / "data"

# Cached SIIS responses
_SIIS_CACHE: Optional[List[Dict[str, Any]]] = None


def load_structure_prompt() -> str:
    """Load the structure extraction prompt template."""
    prompt_path = PROMPTS_DIR / "structure_prompt.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


def load_siis_data() -> List[Dict[str, Any]]:
    """Load pre-cleaned Samsung internal knowledge responses."""
    global _SIIS_CACHE
    if _SIIS_CACHE is not None:
        return _SIIS_CACHE

    siis_path = DATA_DIR / "siis_responses.json"
    if siis_path.exists():
        try:
            with open(siis_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _SIIS_CACHE = data.get("responses", [])
                return _SIIS_CACHE
        except Exception as e:
            logger.warning(f"Failed to load siis_responses.json: {e}")

    _SIIS_CACHE = []
    return _SIIS_CACHE


def find_matching_siis(query: str) -> Optional[Dict[str, Any]]:
    """Find a matching SIIS response for a given query."""
    responses = load_siis_data()
    q_clean = re.sub(r"^[0-9]+[\.\)]\s*", "", query.lower()).strip().strip('"')

    # 1. Exact or substring match on original query (substring only for long queries)
    for item in responses:
        orig = re.sub(r"^[0-9]+[\.\)]\s*", "", item.get("original_query", "").lower()).strip().strip('"')
        if orig == q_clean or (len(q_clean.split()) >= SIIS_MIN_SUBSTRING_WORDS and (orig in q_clean or q_clean in orig)):
            return item.get("siis_response")

    # 2. Content-word overlap match
    q_words = _content_words(q_clean)
    best_match = None
    best_overlap = 0

    for item in responses:
        orig_words = _content_words(item.get("original_query", "").lower())
        overlap = len(q_words.intersection(orig_words))
        if overlap > best_overlap and overlap >= 4 and overlap >= SIIS_MIN_COVERAGE * len(q_words):
            best_overlap = overlap
            best_match = item.get("siis_response")

    return best_match


SIIS_MIN_SUBSTRING_WORDS = 6
SIIS_MIN_COVERAGE = 0.5
SIIS_STOPWORDS = {
    "the", "a", "an", "my", "i", "me", "is", "are", "was", "it", "its", "and", "or", "to", "of", "on", "in", "at",
    "for", "with", "when", "so", "but", "this", "that", "be", "have", "has", "had", "do", "does", "did", "can",
    "what", "how", "why", "not", "no", "am", "i'm", "im", "any", "all", "even", "just", "from", "by", "as", "if",
    "then", "than", "too", "very", "also", "again", "about", "after", "before", "while", "into", "out", "up",
}


def _content_words(text: str) -> set:
    return {w for w in re.findall(r"\w+", text) if len(w) > 2 and w not in SIIS_STOPWORDS}


def format_title(raw_title: str, domain: str) -> str:
    """Ensure title is exactly 2 to 3 words, Title/Sentence Case identifying the core issue."""
    title_words = re.findall(r"[A-Za-z0-9]+", raw_title)
    if 2 <= len(title_words) <= 3:
        return " ".join(title_words).capitalize()

    # Pre-defined standardized 2-3 word titles per domain
    fallback_titles = {
        "battery": "Battery drain issue",
        "display": "Screen display damage",
        "camera": "Camera focus failure",
        "performance": "Device performance lag",
        "connectivity": "Data transfer error",
        "audio": "Audio speaker defect",
        "storage": "Storage memory full",
        "system": "System startup failure",
    }
    return fallback_titles.get(domain, "Device troubleshooting plan")


_TRAILING_STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "at", "by",
    "from", "with", "which", "that", "will", "is", "are", "your", "you",
    "between", "into", "onto", "through", "during", "before", "after",
    "about", "over", "under", "without", "within", "across",
}


def format_action_description(raw_desc: str, action_name: str, domain: str) -> str:
    """Ensure action description starts with 'It will ' and contains 5 to 7 words."""
    text = (raw_desc or "").strip()

    # Guarantee prefix: 'It will '
    if not text.startswith("It will "):
        if text.startswith("It "):
            text = "It will " + text[3:]
        elif text.startswith("This will "):
            text = "It will " + text[10:]
        elif text:
            # lower first letter if not an acronym
            first_word = text.split()[0]
            rest = text[len(first_word):]
            text = f"It will allow you to {first_word.lower()}{rest}"
        else:
            text = f"It will check {action_name.lower()} settings."

    text = text.rstrip(".")
    words = [w.rstrip(",") for w in text.split()]

    # Trim to 7 words if the source text ran long, then drop a dangling
    # trailing preposition/conjunction/article so the phrase still reads
    # as a complete clause instead of cutting off mid-thought.
    if len(words) > 7:
        words = words[:7]
        while len(words) > 5 and words[-1].lower() in _TRAILING_STOPWORDS:
            words.pop()

    # Pad to 5 words minimum without adding new claims beyond the action itself
    filler = ["and", "verify", "current", "device", "settings"]
    pad_index = 0
    while len(words) < 5 and pad_index < len(filler):
        words.append(filler[pad_index])
        pad_index += 1

    return " ".join(words) + "."


def clean_steps(steps: List[str]) -> List[str]:
    """Clean step strings, strip external URLs, and ensure clear imperative style."""
    cleaned = []
    for step in steps:
        s = step.strip()
        # Remove markdown links [text](url) -> text
        s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
        # Remove raw URLs
        s = re.sub(r"https?://\S+", "", s)
        s = re.sub(r"bixby://\S+", "", s)
        # Strip trailing punctuation artifacts
        s = s.strip()
        if s:
            if not s.endswith("."):
                s += "."
            cleaned.append(s)
    return cleaned if cleaned else ["Navigate to device Settings and follow on-screen prompts."]


def reorder_actions_critical_last(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strictly order critical actions (Factory reset, Safe mode reboot) last."""
    standard_actions = []
    critical_actions = []

    for action in actions:
        cat = action.get("category", "auto")
        name = action.get("actionName", "").lower()
        desc = action.get("description", "").lower()

        # Identify critical actions by category or destructive keywords
        is_critical = (
            cat == ActionCategory.critical
            or cat == "critical"
            or any(kw in name for kw in ["factory reset", "wipe", "safe mode", "reset all", "firmware"])
            or any(kw in desc for kw in ["factory data reset", "reboot into safe mode", "wipe all user data"])
        )

        if is_critical:
            action["category"] = "critical"
            critical_actions.append(action)
        else:
            if cat == "manual" or cat == ActionCategory.manual:
                action["category"] = "manual"
            else:
                action["category"] = "auto"
            standard_actions.append(action)

    return standard_actions + critical_actions


NETWORK_WORDS = ("wifi", "wi-fi", "bluetooth", "internet", "signal", "mobile data", "cellular", "network", "hotspot", "disconnect")
PLAN_KEYS = ("battery", "display", "camera", "performance", "audio", "storage", "system")


def _plan_key(domain: str, original_query: str) -> str:
    if domain == "connectivity":
        query = (original_query or "").lower()
        return "network" if any(word in query for word in NETWORK_WORDS) else "display"
    return domain if domain in PLAN_KEYS else "display"


RADIO_ACTIONS = {
    "wifi": ("View WiFi Settings", ("wifi", "wi-fi", "internet", "hotspot")),
    "bluetooth": ("View Bluetooth", ("bluetooth", "earbuds", "buds", "headphones", "speaker")),
    "mobile": ("View Mobile Networks", ("mobile data", "cellular", "signal", "sim", "4g", "5g", "lte")),
}


def _focus_network_actions(actions: List[Dict[str, Any]], original_query: str) -> List[Dict[str, Any]]:
    query = (original_query or "").lower()
    named = {radio for radio, (_, words) in RADIO_ACTIONS.items() if any(w in query for w in words)}
    if not named:
        return actions
    dropped = {RADIO_ACTIONS[radio][0] for radio in RADIO_ACTIONS if radio not in named}
    return [a for a in actions if a["actionName"] not in dropped]


def _build_domain_plan(domain: str, issue: str, technical_query: str, original_query: str = "") -> Dict[str, Any]:
    """Generate grounded, pre-validated troubleshooting actions based on domain."""
    domain_plans = {
        "battery": {
            "goal": "Follow these steps to perform this Battery Troubleshooting",
            "title": "Battery drain issue",
            "actions": [
                {
                    "actionName": "Check Battery Usage",
                    "description": "It will show which apps drain battery.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to and open Settings.",
                                "Tap on Battery and device care.",
                                "Select Battery to view detailed app power consumption."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Enable Power Saving Mode",
                    "description": "It will reduce background power consumption.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to and open Settings.",
                                "Tap on Battery and device care.",
                                "Toggle Power saving to On."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Restart Device in Safe Mode",
                    "description": "It will reboot with third-party apps disabled.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Press and hold the Power button and Volume down button.",
                                "Touch and hold the Power off icon on screen.",
                                "Tap Safe mode to initiate the diagnostic reboot."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "critical"
                }
            ]
        },
        "display": {
            "goal": "Follow these steps to perform this Screen Damage Troubleshooting",
            "title": "Screen display damage",
            "actions": [
                {
                    "actionName": "Back Up Phone Data",
                    "description": "It will back up your personal data.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to and open Settings.",
                                "Tap on Accounts and backup.",
                                "Select Back up data to secure your personal files."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Inspect Hardware and Liquid Indicator",
                    "description": "It will check for liquid damage signs.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Power off device and remove any protective case.",
                                "Insert ejector tool into SIM tray to inspect Liquid Damage Indicator.",
                                "Verify indicator is solid white and free of pink discoloration."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "manual"
                },
                {
                    "actionName": "Schedule Screen Repair Service",
                    "description": "It will arrange a professional screen repair.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Contact Samsung Support or visit an authorized Samsung Service Center.",
                                "Provide device details regarding the damaged display panel to initiate service."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "manual"
                }
            ]
        },
        "camera": {
            "goal": "Follow these steps to perform this Camera Troubleshooting",
            "title": "Camera focus failure",
            "actions": [
                {
                    "actionName": "Clear Camera App Cache",
                    "description": "It will clear corrupted camera cache files.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to Settings and select Apps.",
                                "Scroll down and select Camera.",
                                "Tap Storage and tap Clear cache."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Clean Camera Lens Surface",
                    "description": "It will remove smudges blocking the lens.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Inspect camera module glass under direct lighting.",
                                "Gently wipe lens glass with a clean microfiber cloth."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "manual"
                },
                {
                    "actionName": "Reset Camera Settings",
                    "description": "It will restore default camera settings.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Open the Camera application.",
                                "Tap the Settings gear icon in the upper left corner.",
                                "Scroll to the bottom and select Reset settings."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "critical"
                }
            ]
        },
        "performance": {
            "goal": "Follow these steps to perform this Performance Troubleshooting",
            "title": "Device performance lag",
            "actions": [
                {
                    "actionName": "Optimize Device Storage and Memory",
                    "description": "It will free up memory and storage.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to and open Settings.",
                                "Tap Battery and device care.",
                                "Tap Optimize now to close background apps and free RAM."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Check Software Updates",
                    "description": "It will install the latest system software.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Navigate to Settings.",
                                "Scroll down and tap Software update.",
                                "Select Download and install."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "auto"
                },
                {
                    "actionName": "Reboot into Safe Mode",
                    "description": "It will reboot with third-party apps disabled.",
                    "stepGroups": [
                        {
                            "steps": [
                                "Hold Power and Volume down keys simultaneously.",
                                "Long-press the Power off prompt on display.",
                                "Tap Safe mode to reboot into diagnostic state."
                            ],
                            "actionableDeeplink": None,
                            "validationDeeplink": None
                        }
                    ],
                    "category": "critical"
                }
            ]
        },
        "network": {
            "goal": "Follow these steps to perform this Network Troubleshooting",
            "title": "Network connection issue",
            "actions": [
                {
                    "actionName": "View WiFi Settings",
                    "description": "It will reconnect your phone to Wi-Fi.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Connections.",
                        "Tap Wi-Fi.",
                        "Tap the Wi-Fi switch to turn it off.",
                        "Tap the Wi-Fi switch again to turn it on.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "View Bluetooth",
                    "description": "It will reconnect your paired Bluetooth devices.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Connections.",
                        "Tap Bluetooth.",
                        "Tap the paired device name to reconnect it.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Disable Airplane Mode",
                    "description": "It will restore all wireless connections.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Connections.",
                        "Toggle Airplane mode to Off.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "View Mobile Networks",
                    "description": "It will review your mobile data settings.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Connections.",
                        "Tap Mobile networks.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Reset Network Settings",
                    "description": "It will restore default network connection settings.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap General management.",
                        "Tap Reset.",
                        "Tap Reset network settings.",
                        "Tap Reset settings to confirm.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "critical",
                },
            ]
        },
        "audio": {
            "goal": "Follow these steps to perform this Audio Troubleshooting",
            "title": "Speaker sound issue",
            "actions": [
                {
                    "actionName": "View Volume Settings",
                    "description": "It will confirm media and ringtone volume.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Sounds and vibration.",
                        "Tap Volume.",
                        "Drag the Media slider to the right.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "View Sound Settings",
                    "description": "It will switch off silent or vibrate.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Sounds and vibration.",
                        "Select Sound as the sound mode.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Clean Speaker Grille",
                    "description": "It will clear debris blocking the speaker.",
                    "stepGroups": [{"steps": [
                        "Power off the device.",
                        "Gently brush the speaker grille with a soft dry brush.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "manual",
                },
                {
                    "actionName": "Schedule Speaker Repair Service",
                    "description": "It will arrange a professional speaker inspection.",
                    "stepGroups": [{"steps": [
                        "Contact Samsung Support or visit an authorized Samsung Service Center.",
                        "Describe the missing or distorted sound to initiate service.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "manual",
                },
            ]
        },
        "storage": {
            "goal": "Follow these steps to perform this Storage Troubleshooting",
            "title": "Storage space full",
            "actions": [
                {
                    "actionName": "Check Storage Usage",
                    "description": "It will show what uses storage space.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Battery and device care.",
                        "Tap Storage.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Clear App Cache",
                    "description": "It will remove temporary app cache files.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap Apps.",
                        "Select the app using the most space.",
                        "Tap Storage.",
                        "Tap Clear cache.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Back Up Phone Data",
                    "description": "It will back up your personal data.",
                    "stepGroups": [{"steps": [
                        "Navigate to and open Settings.",
                        "Tap on Accounts and backup.",
                        "Select Back up data to secure your personal files.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
            ]
        },
        "system": {
            "goal": "Follow these steps to perform this System Troubleshooting",
            "title": "System startup failure",
            "actions": [
                {
                    "actionName": "Check Software Updates",
                    "description": "It will install the latest system software.",
                    "stepGroups": [{"steps": [
                        "Navigate to Settings.",
                        "Scroll down and tap Software update.",
                        "Select Download and install.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "auto",
                },
                {
                    "actionName": "Force Restart Device",
                    "description": "It will force the device to reboot.",
                    "stepGroups": [{"steps": [
                        "Press and hold the Side key and Volume down key together.",
                        "Release both keys when the Samsung logo appears.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "manual",
                },
                {
                    "actionName": "Reboot into Safe Mode",
                    "description": "It will reboot with third-party apps disabled.",
                    "stepGroups": [{"steps": [
                        "Hold Power and Volume down keys simultaneously.",
                        "Long-press the Power off prompt on display.",
                        "Tap Safe mode to reboot into diagnostic state.",
                    ], "actionableDeeplink": None, "validationDeeplink": None}],
                    "category": "critical",
                },
            ]
        },
    }

    key = _plan_key(domain, original_query)
    base = domain_plans[key]
    if key == "network":
        base = dict(base, actions=_focus_network_actions(base["actions"], original_query))
    return {
        "contexts": [
            {
                "goal": base["goal"],
                "title": format_title(base["title"], domain),
                "score": 0.95,
                "actions": base["actions"]
            }
        ]
    }


def _call_llm_for_structure(
    technical_query: str, domain: str, issue: str, context: List[str], siis_content: str
) -> Optional[Dict[str, Any]]:
    """Call external LLM to synthesize structure if API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        prompt_template = load_structure_prompt()
        prompt = (
            prompt_template
            .replace("{technical_query}", technical_query)
            .replace("{domain}", domain)
            .replace("{issue}", issue)
            .replace("{context}", ", ".join(context))
            .replace("{siis_content}", siis_content[:2000] if siis_content else "None available")
        )

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a Samsung Diagnostic Engine. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=15
        )
        content = response.choices[0].message.content
        if content:
            import json_repair
            data = json_repair.loads(content)
            if isinstance(data, dict) and "contexts" in data:
                return data
    except Exception as e:
        logger.warning(f"LLM structure extraction call failed: {e}")

    return None


def generate_troubleshooting_plan(
    enriched_query: Dict[str, Any], siis_response: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate structured troubleshooting plan conforming to Samsung PRISM Theme 02 schema.

    Args:
        enriched_query: Stage 1 output dictionary containing technical_query, domain, issue, context.
        siis_response: Optional SIIS knowledge store payload. If None, matching is attempted from data.

    Returns:
        Dictionary conforming to TroubleshootingPlan / ContextDeeplinkResponse schema.
    """
    orig_query = enriched_query.get("original_query", "")
    technical_query = enriched_query.get("technical_query", orig_query)
    domain = enriched_query.get("domain", "system")
    issue = enriched_query.get("issue", "")
    context = enriched_query.get("context", [])
    query_variations = enriched_query.get("query_variations", [])

    # 1. Match SIIS response from data if not explicitly provided
    if not siis_response:
        siis_response = find_matching_siis(orig_query)

    siis_content = ""
    if siis_response:
        siis_content = f"{siis_response.get('title', '')}\n{siis_response.get('content', '')}"

    # 2. Attempt LLM structure generation if provider is active
    raw_plan = _call_llm_for_structure(technical_query, domain, issue, context, siis_content)

    # 3. Fallback to domain-specific grounded plan
    if not raw_plan:
        raw_plan = _build_domain_plan(domain, issue, technical_query, orig_query)

    # 4. Post-processing Sanitization & Strict Constraint Enforcement
    contexts = raw_plan.get("contexts", [])
    if not contexts:
        contexts = _build_domain_plan(domain, issue, technical_query, orig_query)["contexts"]

    sanitized_contexts = []
    for ctx in contexts:
        raw_title = ctx.get("title", f"{domain.capitalize()} issue")
        title = format_title(raw_title, domain)
        goal = ctx.get("goal") or f"Follow these steps to perform this {domain.capitalize()} Troubleshooting"
        score = float(ctx.get("score", 0.95))

        actions = ctx.get("actions", [])
        sanitized_actions = []

        for action in actions:
            action_name = action.get("actionName", "Diagnostic Step")
            desc = action.get("description", "")
            formatted_desc = format_action_description(desc, action_name, domain)
            cat = action.get("category", "auto")

            step_groups = action.get("stepGroups", [])
            sanitized_groups = []
            for sg in step_groups:
                steps = clean_steps(sg.get("steps", []))
                sanitized_groups.append({
                    "steps": steps,
                    "actionableDeeplink": None,
                    "validationDeeplink": None
                })

            if not sanitized_groups:
                sanitized_groups = [{
                    "steps": ["Navigate to Settings and select configuration options."],
                    "actionableDeeplink": None,
                    "validationDeeplink": None
                }]

            sanitized_actions.append({
                "actionName": action_name,
                "description": formatted_desc,
                "stepGroups": sanitized_groups,
                "category": cat
            })

        # Apply Critical Actions Reordering Rule: Critical actions MUST be ordered last
        ordered_actions = reorder_actions_critical_last(sanitized_actions)

        # Enforce manual action rule: manual actions cannot have actionableDeeplink
        for a in ordered_actions:
            if a["category"] == "manual":
                for sg in a["stepGroups"]:
                    sg["actionableDeeplink"] = None

        sanitized_contexts.append({
            "goal": goal,
            "title": title,
            "score": score,
            "actions": ordered_actions
        })

    result = {
        "contexts": sanitized_contexts,
        "query_variations": query_variations
    }

    # Validate against Pydantic model
    validated = TroubleshootingPlan(**result)
    return validated.model_dump()
