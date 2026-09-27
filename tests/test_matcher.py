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


def test_enable_action_resolves_to_enable_toggle():
    r = resolver().resolve("Enable Power Saving Mode", category="auto")
    assert r["catalogEntry"]["originalType"] == "onURL"


def test_turn_off_action_resolves_to_off_toggle():
    r = resolver().resolve("Turn Off Bluetooth", category="auto")
    assert r["catalogEntry"]["originalType"] == "offURL"


def test_neutral_action_never_resolves_to_a_disable_toggle():
    r = resolver().resolve("Back Up Phone Data", "It will back up your personal data.", category="auto")
    assert r["resolved"] is True
    assert r["catalogEntry"]["originalType"] != "offURL"


def test_critical_action_rejects_weak_semantic_match():
    r = resolver().resolve(
        "Reset Network Settings",
        "It will restore default network connection settings.",
        steps=["Navigate to and open Settings.", "Tap General management.", "Tap Reset.",
               "Tap Reset network settings.", "Tap Reset settings to confirm."],
        category="critical",
    )
    assert r["resolved"] is False
    assert r["reason"] == "critical_requires_confident_match"
    assert r["actionableDeeplink"] is None


def test_polarity_helpers():
    from backend.services.action_matcher import action_polarity, entry_polarity
    assert action_polarity("Enable Wi-Fi") == "on"
    assert action_polarity("Remove floating button") == "off"
    assert action_polarity("Check Battery Usage") is None
    assert entry_polarity({"originalType": "offURL"}) == "off"
