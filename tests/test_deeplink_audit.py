import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _audit_module():
    spec = importlib.util.spec_from_file_location("deeplink_audit", ROOT / "evaluation" / "deeplink_audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_finds_only_catalog_deeplinks_and_no_problems():
    report = _audit_module().audit(["my phone battery drains fast", "turn off bluetooth", "my wifi keeps disconnecting"])
    linked, total = report["deeplinks_in_catalog"].split("/")
    assert int(total) > 0 and linked == total
    assert report["manual_actions_with_deeplink"] == 0
    assert report["problems"] == []


def test_audit_query_groups_cover_official_and_settings_sets():
    groups = _audit_module().queries()
    assert len(groups["official"]) == 20
    assert len(groups["settings_requests"]) == 40
    assert groups["domain_seeds"]
