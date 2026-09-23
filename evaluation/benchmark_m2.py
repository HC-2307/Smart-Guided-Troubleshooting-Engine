"""Run M2 resolution on source-grounded scenarios.

This benchmark measures candidate resolution only. It does not invent ground truth.
Populate data/scenarios.json::expected_catalog_ids after manual review before
calculating deeplink accuracy.
"""
from __future__ import annotations

import json
from pathlib import Path
from backend.services.deeplink_resolver import DeeplinkResolver


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "deeplinks.json"
SCENARIOS = ROOT / "data" / "scenarios.json"


def main() -> None:
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    resolver = DeeplinkResolver(CATALOG)
    results = []

    for scenario in scenarios:
        result = resolver.resolve(
            action_name=scenario["source_title"] or "",
            description=scenario["query"],
            category="auto",
        )
        results.append({
            "id": scenario["id"],
            "query": scenario["query"],
            "strategy": result["strategy"],
            "score": result["score"],
            "catalogId": result.get("catalogId"),
            "resolved": result["resolved"],
        })

    print(json.dumps({
        "scenario_count": len(results),
        "resolved_count": sum(r["resolved"] for r in results),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
