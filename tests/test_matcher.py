from pathlib import Path
from backend.services.deeplink_resolver import DeeplinkResolver


ROOT = Path(__file__).resolve().parents[1]


def resolver():
    return DeeplinkResolver(ROOT / "data" / "deeplinks.json")


def test_exact_match_uses_catalog_value():
    r = resolver().resolve("Switch Time Format")
    assert r["resolved"] is True
    assert r["catalogId"] == "DL-0001"
    assert r["strategy"] == "exact"
    assert r["actionableDeeplink"].startswith("bixby://")


def test_manual_action_never_gets_a_deeplink():
    r = resolver().resolve(
        "Schedule Screen Repair Service",
        "Visit an authorized service center.",
        category="manual",
    )
    assert r["resolved"] is False
    assert r["actionableDeeplink"] is None


def test_context_can_disambiguate_duplicate_messages():
    r = resolver().resolve(
        "Check Battery Performance",
        "Open the battery protection settings page and limit charge to 85%.",
        category="auto",
    )
    assert r["resolved"] is True
    assert r["catalogId"] == "DL-0517"


def test_unknown_action_is_not_fabricated():
    r = resolver().resolve(
        "Open Quantum Flux Repair Console",
        "This setting does not exist in the supplied catalog.",
        category="auto",
    )
    assert r["resolved"] is False
    assert r["actionableDeeplink"] is None
