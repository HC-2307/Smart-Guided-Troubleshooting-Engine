import re
from backend.schemas.troubleshoot import TroubleshootResponse

# Matches http(s) links, bare "www." links, and markdown-style [text](url) links.
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+|\[[^\]]+\]\([^)]+\)", re.IGNORECASE)


def check_no_url_leakage(response: TroubleshootResponse) -> list[str]:
    """Scan every user-facing text field for URLs. Returns violation messages (empty = clean)."""
    violations: list[str] = []

    for goal in response.contexts:
        _scan_field(goal.goal, "goal", violations)
        _scan_field(goal.title, "title", violations)

        for action in goal.actions:
            _scan_field(action.actionName, f"{action.actionName}.actionName", violations)
            _scan_field(action.description, f"{action.actionName}.description", violations)

            for group in action.stepGroups:
                for step in group.steps:
                    _scan_field(step, f"{action.actionName}.step", violations)

    return violations


def _scan_field(text: str, field_label: str, violations: list[str]) -> None:
    # One field at a time, so every hit can point back to exactly where it came from.
    if URL_PATTERN.search(text):
        violations.append(f"URL found in {field_label}: {text!r}")
