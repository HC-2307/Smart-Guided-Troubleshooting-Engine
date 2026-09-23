"""Catalog-backed deeplink resolution for M2."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_matcher import ActionMatcher
from .catalog_validator import load_catalog


class DeeplinkResolver:
    """Resolve model-generated actions only to trusted catalog entries."""

    def __init__(self, catalog_path: str | Path, semantic_threshold: float = 0.34):
        self.catalog = load_catalog(catalog_path)
        self.catalog_by_id = {e["id"]: e for e in self.catalog}
        self.matcher = ActionMatcher(self.catalog, semantic_threshold=semantic_threshold)

    def resolve(
        self,
        action_name: str,
        description: str = "",
        steps: list[str] | None = None,
        category: str = "auto",
        allow_dummy: bool = False,
    ) -> dict[str, Any]:
        """Resolve one action.

        Manual actions intentionally receive no actionable deeplink.
        For other categories, a link is returned only when it is catalog-backed.
        """
        if category == "manual":
            return {
                "resolved": False,
                "reason": "manual_action_no_deeplink",
                "catalogId": None,
                "actionableDeeplink": None,
                "strategy": "manual",
                "score": 1.0,
            }

        context_parts = [description] + list(steps or [])
        result = self.matcher.match(action_name, " ".join(context_parts))

        if result.entry is None:
            if allow_dummy:
                dummy = next(
                    (e for e in self.catalog if e.get("id") == "DL-DUMMY"),
                    None,
                )
                if dummy:
                    return {
                        "resolved": True,
                        "reason": "dummy_catalog_placeholder",
                        "catalogId": dummy["id"],
                        "actionableDeeplink": dummy["deeplink"],
                        "strategy": "dummy",
                        "score": 0.0,
                    }

            return {
                "resolved": False,
                "reason": "no_confident_catalog_match",
                "catalogId": None,
                "actionableDeeplink": None,
                "strategy": result.strategy,
                "score": round(result.score, 4),
                "candidates": [e.get("id") for e in result.candidates],
            }

        entry = result.entry
        if entry.get("id") == "DL-DUMMY" and not allow_dummy:
            return {
                "resolved": False,
                "reason": "dummy_catalog_disabled",
                "catalogId": None,
                "actionableDeeplink": None,
                "strategy": result.strategy,
                "score": round(result.score, 4),
            }

        return {
            "resolved": True,
            "reason": "catalog_match",
            "catalogId": entry["id"],
            "actionableDeeplink": entry["deeplink"],
            "strategy": result.strategy,
            "score": round(result.score, 4),
            "catalogEntry": entry,
        }

    def resolve_plan(self, plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Resolve every action/step group and return (plan, resolution_report)."""
        report = {"resolved": [], "unresolved": [], "manual": []}
        output = dict(plan)

        for goal in output.get("contexts", []):
            for action in goal.get("actions", []):
                category = action.get("category") or "manual"

                if category == "manual":
                    report["manual"].append(action.get("actionName"))
                    for group in action.get("stepGroups", []):
                        group["actionableDeeplink"] = None
                    continue

                for group in action.get("stepGroups", []):
                    result = self.resolve(
                        action_name=action.get("actionName", ""),
                        description=action.get("description", ""),
                        steps=group.get("steps", []),
                        category=category,
                    )
                    if result["resolved"]:
                        entry = result["catalogEntry"]
                        group["actionableDeeplink"] = {
                            "deeplink": entry["deeplink"],
                            "description": entry.get("description", ""),
                            "message": entry.get("message", ""),
                            "classes": entry.get("classes"),
                            "originalType": entry.get("originalType"),
                        }
                        report["resolved"].append({
                            "actionName": action.get("actionName"),
                            "catalogId": entry["id"],
                            "strategy": result["strategy"],
                            "score": result["score"],
                        })
                    else:
                        group["actionableDeeplink"] = None
                        report["unresolved"].append({
                            "actionName": action.get("actionName"),
                            "reason": result["reason"],
                            "strategy": result["strategy"],
                            "score": result["score"],
                            "candidates": result.get("candidates", []),
                        })

        return output, report
