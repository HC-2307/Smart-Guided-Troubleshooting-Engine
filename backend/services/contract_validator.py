import copy
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from backend.config import CATALOG_PATH
from backend.services.catalog_validator import load_catalog

DUMMY_DEEPLINK = "bixby://dummy_positive"
GOAL_PATTERN = re.compile(r"^Follow these steps to perform this .+ (Troubleshooting|Configuration)$")
LINK_PATTERN = re.compile(
    r"https?://\S+|www\.\S+|\[[^\]]+\]\([^)]+\)|\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE
)
MARKDOWN_PATTERN = re.compile(r"\*\*|__|`+|^#+\s*|^\s*[-*]\s+", re.MULTILINE)
ON_WORDS = re.compile(r"\b(enable|turn on|switch on|activate|allow|show)\b", re.IGNORECASE)
OFF_WORDS = re.compile(r"\b(disable|turn off|switch off|deactivate|block|hide|remove)\b", re.IGNORECASE)
VALID_CATEGORIES = {"auto", "manual", "critical"}
CATALOG_FIELDS = ("description", "message", "classes", "originalType")


@dataclass
class Violation:
    code: str
    outcome: str
    path: str
    detail: str


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)

    def add(self, code: str, outcome: str, path: str, detail: str) -> None:
        self.violations.append(Violation(code, outcome, path, detail))

    def count(self, outcome: str) -> int:
        return sum(1 for v in self.violations if v.outcome == outcome)

    def summary(self) -> dict[str, Any]:
        return {
            "repaired": self.count("repaired"),
            "quarantined": self.count("quarantined"),
            "warnings": self.count("warning"),
            "codes": sorted({v.code for v in self.violations}),
        }


@lru_cache(maxsize=1)
def catalog_by_deeplink() -> dict[str, dict]:
    return {e["deeplink"]: e for e in load_catalog(CATALOG_PATH)}


def has_link(text: Any) -> bool:
    return isinstance(text, str) and bool(LINK_PATTERN.search(text))


def polarity(text: str) -> Optional[str]:
    on, off = bool(ON_WORDS.search(text or "")), bool(OFF_WORDS.search(text or ""))
    return "on" if on and not off else "off" if off and not on else None


def entry_polarity(entry: dict) -> Optional[str]:
    kind = entry.get("originalType")
    if kind == "onURL":
        return "on"
    if kind == "offURL":
        return "off"
    return polarity(str(entry.get("message", "")))


MINOR_WORDS = {"a", "an", "the", "and", "or", "but", "for", "nor", "of", "on", "in", "to", "at", "by", "via", "with", "from", "as"}


def _title_case(name: str) -> str:
    words = name.split()
    return " ".join(
        w.lower() if i and w.lower() in MINOR_WORDS else w[:1].upper() + w[1:]
        for i, w in enumerate(words)
    )


def _strip_markdown(text: str) -> str:
    return re.sub(r"\s+", " ", MARKDOWN_PATTERN.sub("", text)).strip()


def _check_deeplink(group: dict, action: dict, path: str, report: ValidationReport, catalog: dict) -> None:
    link = group.get("actionableDeeplink")
    if link is None:
        return
    uri = link.get("deeplink") if isinstance(link, dict) else None

    if action.get("category") == "manual":
        group["actionableDeeplink"] = None
        report.add("MANUAL_HAS_DEEPLINK", "repaired", path, "manual action deeplink removed")
        return

    entry = catalog.get(uri)
    if entry is None:
        group["actionableDeeplink"] = None
        report.add("DEEPLINK_NOT_IN_CATALOG", "repaired", path, f"untrusted deeplink removed: {uri!r}")
        return

    if uri != DUMMY_DEEPLINK:
        drift = [f for f in CATALOG_FIELDS if link.get(f) != entry.get(f)]
        if drift:
            for f in CATALOG_FIELDS:
                link[f] = entry.get(f)
            report.add("DEEPLINK_METADATA_DRIFT", "repaired", path, f"restored catalog fields: {drift}")

    wanted, offered = polarity(action.get("actionName", "")), entry_polarity(entry)
    if wanted and offered and wanted != offered:
        group["actionableDeeplink"] = None
        report.add(
            "TOGGLE_POLARITY_CONFLICT", "repaired", path,
            f"action wants '{wanted}' but catalog entry '{entry.get('message')}' switches '{offered}'",
        )


def _validate_action(action: dict, path: str, report: ValidationReport, catalog: dict) -> bool:
    name = action.get("actionName") or ""
    description = action.get("description") or ""

    if not name.strip() or has_link(name):
        report.add("ACTION_NAME_INVALID", "quarantined", path, repr(name))
        return False
    if _title_case(name) != name:
        action["actionName"] = _title_case(name)
        report.add("ACTION_NAME_CASE", "repaired", path, f"{name!r} -> {action['actionName']!r}")

    words = description.strip().rstrip(".").split()
    if not description.startswith("It will ") or not 5 <= len(words) <= 7 or has_link(description):
        report.add("DESCRIPTION_CONTRACT", "quarantined", path, f"needs 5-7 words starting 'It will': {description!r}")
        return False

    if action.get("category") not in VALID_CATEGORIES:
        report.add("CATEGORY_INVALID", "quarantined", path, repr(action.get("category")))
        return False

    groups = action.get("stepGroups") or []
    if not groups:
        report.add("NO_STEP_GROUPS", "quarantined", path, "action has no step groups")
        return False

    for g_index, group in enumerate(groups):
        g_path = f"{path}.stepGroups[{g_index}]"
        steps = group.get("steps") or []
        if not steps:
            report.add("EMPTY_STEPS", "quarantined", g_path, "step group has no steps")
            return False
        for s_index, step in enumerate(steps):
            if has_link(step):
                report.add("URL_LEAK", "quarantined", f"{g_path}.steps[{s_index}]", repr(step))
                return False
            cleaned = _strip_markdown(step)
            if cleaned != step:
                steps[s_index] = cleaned
                report.add("MARKDOWN_IN_STEP", "repaired", f"{g_path}.steps[{s_index}]", repr(step))
        _check_deeplink(group, action, g_path, report, catalog)

    return True


def _validate_goal(goal: dict, path: str, report: ValidationReport, catalog: dict) -> bool:
    text, title = goal.get("goal") or "", goal.get("title") or ""
    if not GOAL_PATTERN.match(text) or has_link(text):
        report.add("GOAL_PHRASING", "quarantined", path, repr(text))
        return False
    if not 2 <= len(title.split()) <= 3 or has_link(title):
        report.add("TITLE_CONTRACT", "quarantined", path, f"title must be 2-3 words: {title!r}")
        return False
    if title[:1].islower():
        goal["title"] = title[:1].upper() + title[1:]
        report.add("TITLE_CASE", "repaired", path, f"{title!r} -> {goal['title']!r}")

    raw_score = goal.get("score")
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 0.0
    if not 0.0 <= score <= 1.0 or score != raw_score:
        goal["score"] = min(max(score, 0.0), 1.0)
        report.add("SCORE_RANGE", "repaired", path, f"{raw_score!r} -> {goal['score']}")

    kept, seen = [], set()
    for a_index, action in enumerate(goal.get("actions") or []):
        a_path = f"{path}.actions[{a_index}]"
        if not _validate_action(action, a_path, report, catalog):
            continue
        if action["actionName"].lower() in seen:
            report.add("DUPLICATE_ACTION", "repaired", a_path, action["actionName"])
            continue
        seen.add(action["actionName"].lower())
        kept.append(action)

    ordered = [a for a in kept if a["category"] != "critical"] + [a for a in kept if a["category"] == "critical"]
    if ordered != kept:
        report.add("CRITICAL_NOT_LAST", "repaired", path, "critical actions moved to the end")
    goal["actions"] = ordered

    if not ordered:
        report.add("GOAL_EMPTY", "quarantined", path, "no valid actions left")
        return False
    return True


def _validate_variations(response: dict, report: ValidationReport) -> None:
    variations = response.get("query_variations")
    if variations is None:
        return
    cleaned, seen = [], set()
    for v in variations:
        key = " ".join(str(v).lower().split())
        if key and key not in seen and not has_link(v):
            seen.add(key)
            cleaned.append(v)
    if len(cleaned) != len(variations):
        report.add("VARIATIONS_CLEANED", "repaired", "query_variations", "duplicates/links removed")
    if len(cleaned) > 10:
        cleaned = cleaned[:10]
        report.add("VARIATIONS_TRIMMED", "repaired", "query_variations", "trimmed to 10")
    if len(cleaned) < 8:
        report.add("VARIATIONS_TOO_FEW", "warning", "query_variations", f"{len(cleaned)} < 8")
    response["query_variations"] = cleaned


def validate_and_repair(response: dict, catalog: Optional[dict] = None) -> tuple[dict, ValidationReport]:
    catalog = catalog if catalog is not None else catalog_by_deeplink()
    output = copy.deepcopy(response)
    report = ValidationReport()

    had_contexts = bool(output.get("contexts"))
    output["contexts"] = [
        goal for g_index, goal in enumerate(output.get("contexts") or [])
        if _validate_goal(goal, f"contexts[{g_index}]", report, catalog)
    ]
    _validate_variations(output, report)

    if had_contexts and not output["contexts"]:
        output["fallback"] = "validation_failed"
    elif not output["contexts"]:
        output["fallback"] = output.get("fallback") or "no_match"
    return output, report
