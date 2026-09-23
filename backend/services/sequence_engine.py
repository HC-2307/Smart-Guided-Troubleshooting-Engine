"""M2 action sequencing and category-rule validation."""
from __future__ import annotations
from typing import Any


CRITICAL = "critical"
MANUAL = "manual"


def validate_action_sequence(actions: list[dict[str, Any]]) -> list[str]:
    """Return ordering/category violations without mutating the input."""
    violations: list[str] = []
    seen_critical = False

    for index, action in enumerate(actions):
        category = action.get("category") or MANUAL

        if category == CRITICAL:
            seen_critical = True
        elif seen_critical:
            violations.append(
                f"non-critical action '{action.get('actionName', '')}' appears "
                f"after critical action at index {index}"
            )

        if category == MANUAL:
            for group in action.get("stepGroups", []):
                if group.get("actionableDeeplink") is not None:
                    violations.append(
                        f"manual action '{action.get('actionName', '')}' has an actionable deeplink"
                    )

    return violations


def order_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Move critical actions to the end while preserving relative order otherwise."""
    noncritical = [a for a in actions if (a.get("category") or MANUAL) != CRITICAL]
    critical = [a for a in actions if (a.get("category") or MANUAL) == CRITICAL]
    return noncritical + critical


def apply_sequence_rules(plan: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a copied plan with critical actions last and validation errors."""
    output = dict(plan)
    all_violations: list[str] = []

    for goal in output.get("contexts", []):
        actions = goal.get("actions", [])
        goal["actions"] = order_actions(actions)
        all_violations.extend(validate_action_sequence(goal["actions"]))

    return output, all_violations
