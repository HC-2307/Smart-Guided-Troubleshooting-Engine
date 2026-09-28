import re
from typing import Optional

from backend.services.contract_validator import LINK_PATTERN, MINOR_WORDS, disruption_rank

MAX_ACTIONS = 5
MAX_STEPS = 6
MAX_ACTION_WORDS = 6

HEADING = re.compile(r"^#{2,}\s*(?:step\s*)?(?:\d+\s*[:.)-]?\s*)?(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
IMPERATIVE = re.compile(
    r"^(tap|touch|open|go to|navigate|swipe|select|choose|press|hold|turn|toggle|enable|disable|clear|restart|"
    r"reboot|scroll|remove|add|enter|check|find|launch|update|install|uninstall|delete|move|connect|disconnect|"
    r"pair|unpair|set|adjust|drag|slide|insert|charge|plug|unplug|wait|release|back up|reset|close|force|"
    r"switch|make sure|ensure|use|try|clean|wipe|inspect|contact|visit|sign in|log in|verify|review|attempt|create|perform|test|mirror)\b",
    re.IGNORECASE,
)
SPLIT = re.compile(
    r",?\s*(?:and then|then|and)\s+(?=(?:tap|touch|select|choose|press|open|go to|swipe|turn|enable|disable)\b)"
    r"|,\s+(?=(?:tap|touch|select|choose|press|open|swipe|turn|enable|disable)\b)",
    re.IGNORECASE,
)
DROP = re.compile(r"\b(link|links|click here|website|visit our|see the|for more information)\b", re.IGNORECASE)
CRITICAL = re.compile(r"\b(factory|reset|wipe|erase|safe mode)\b", re.IGNORECASE)
MANUAL = re.compile(
    r"\b(pc|computer|service cent(?:er|re)|contact|technician|inspect|clean|cable|charger|port|replace|physical|"
    r"damage|liquid|restart\w*|reboot\w*|power|button|buttons)\b",
    re.IGNORECASE,
)
LEADING = re.compile(r"^(?:first|next|then|finally|alternatively|also|now)\s*,?\s*", re.IGNORECASE)
GLUED = re.compile(r"\S{25,}")
FILLER = {"your", "the", "a", "an", "my", "their", "its", "troubleshooting"}
DANGLING = {"to", "for", "the", "a", "an", "enter", "select", "tap", "open", "of", "on", "in", "and", "or", "search"}
TOPIC_STOP = {
    "on", "a", "an", "the", "your", "my", "samsung", "galaxy", "phone", "tablet", "how", "to", "and", "of", "in",
    "for", "with", "not", "some", "things", "check", "first", "what", "use", "using", "or", "is", "does", "do",
    "when", "if", "s", "issue", "issues", "problem", "problems", "access", "data", "fix", "troubleshooting",
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -*\t") for p in parts if p.strip(" -*\t")]


def _steps(section: str) -> list[str]:
    steps: list[str] = []
    for sentence in _sentences(section):
        sentence = LEADING.sub("", sentence)
        if LINK_PATTERN.search(sentence) or DROP.search(sentence) or GLUED.search(sentence):
            continue
        if not IMPERATIVE.match(sentence):
            continue
        for piece in SPLIT.split(sentence):
            piece = piece.strip(" ,.;:")
            if len(piece.split()) < 2 or piece.split()[-1].lower() in DANGLING:
                continue
            step = piece[:1].upper() + piece[1:] + "."
            if step not in steps:
                steps.append(step)
    return steps[:MAX_STEPS]


def _title_case(words: list[str]) -> str:
    return " ".join(
        w.lower() if i and w.lower() in MINOR_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words)
    )


def _words(heading: str) -> list[str]:
    return [w for w in re.sub(r"[^\w\s'-]", " ", heading).split() if w.lower() not in FILLER]


def _action_name(heading: str) -> str:
    words = _words(heading)[:MAX_ACTION_WORDS]
    while words and words[-1].lower() in MINOR_WORDS:
        words.pop()
    return _title_case(words)


def _lower(word: str) -> str:
    return word if word.isupper() and len(word) > 1 else word.lower()


def _description(heading: str) -> str:
    words = [_lower(w) for w in _words(heading)]
    if not words:
        return "It will help resolve this issue"
    if not IMPERATIVE.match(words[0]):
        words = ["fix", *words]
    body = words[:5]
    while body and body[-1] in MINOR_WORDS:
        body.pop()
    if len(body) < 3:
        return "It will help resolve this issue"
    return "It will " + " ".join(body)


def _topic(title: str) -> list[str]:
    head = re.split(r"\s+on\s+", title, maxsplit=1)[0]
    head = re.sub(r"\b\w+\s+or\s+", "", head, flags=re.IGNORECASE)
    return [w for w in re.findall(r"[A-Za-z0-9-]+", head) if w.lower() not in TOPIC_STOP][:2]


def _category(heading: str) -> str:
    if CRITICAL.search(heading):
        return "critical"
    return "manual" if MANUAL.search(heading) else "auto"


def parse_reference(siis: Optional[dict], fallback_topic: str = "Device") -> Optional[dict]:
    if not siis:
        return None
    content = str(siis.get("content") or "")
    matches = list(HEADING.finditer(content))
    sections = [
        (m.group(1), content[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(content)])
        for i, m in enumerate(matches)
    ]
    if not sections and content.strip():
        sections = [("Follow the Reference Steps", content)]
    actions = []
    for heading, body in sections:
        steps = _steps(body)
        name = _action_name(heading)
        if not steps or not name:
            continue
        actions.append({
            "actionName": name,
            "description": _description(heading),
            "stepGroups": [{"steps": steps, "actionableDeeplink": None, "validationDeeplink": None}],
            "category": _category(heading),
        })
        if len(actions) == MAX_ACTIONS:
            break
    if not actions:
        return None
    actions.sort(key=disruption_rank)
    topic = _topic(str(siis.get("title") or "")) or [fallback_topic]
    title_words = topic + ["issue"] if len(topic) < 3 else topic
    title = " ".join(title_words[:3])
    return {
        "contexts": [{
            "goal": f"Follow these steps to perform this {_title_case(topic)} Troubleshooting",
            "title": title[:1].upper() + title[1:].lower(),
            "score": 0.9,
            "actions": actions,
        }],
    }
