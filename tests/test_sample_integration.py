import json
from pathlib import Path

from backend.services.deeplink_resolver import DeeplinkResolver
from backend.services.sequence_engine import apply_sequence_rules


ROOT = Path(__file__).resolve().parents[1]


def test_sample_output_can_be_processed_by_m2():
    sample = json.loads((ROOT / "data" / "sample_output.json").read_text())
    plan = sample["response"]
    resolver = DeeplinkResolver(ROOT / "data" / "deeplinks.json")
    resolved, report = resolver.resolve_plan(plan)
    resolved, sequence_violations = apply_sequence_rules(resolved)

    assert sequence_violations == []
    actions = resolved["contexts"][0]["actions"]

    # Manual service action must remain manual/no deeplink.
    manual = next(a for a in actions if a["category"] == "manual")
    assert all(g["actionableDeeplink"] is None for g in manual["stepGroups"])

    # The backup action should resolve to a real catalog entry.
    backup = next(a for a in actions if a["actionName"] == "Back Up Phone Data")
    assert backup["stepGroups"][0]["actionableDeeplink"] is not None
    assert report["unresolved"] == []
