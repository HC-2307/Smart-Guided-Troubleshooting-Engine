import pytest

from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import (
    _build_domain_plan,
    _plan_key,
    format_action_description,
    generate_troubleshooting_plan,
)

ALL_KEYS = ("battery", "display", "camera", "performance", "connectivity", "audio", "storage", "system")


def _plan(query):
    return generate_troubleshooting_plan(enrich_query(query))["contexts"][0]


@pytest.mark.parametrize("query, title", [
    ("Wi-Fi keeps disconnecting", "Network connection issue"),
    ("No sound coming from my speaker", "Speaker sound issue"),
    ("My phone storage is full", "Storage space full"),
    ("my phone is stuck in a boot loop after an update", "System startup failure"),
])
def test_non_display_domains_no_longer_get_the_screen_plan(query, title):
    plan = _plan(query)
    assert plan["title"] == title
    assert "Screen" not in plan["goal"]


def test_smart_switch_blank_screen_reports_never_get_the_network_plan():
    query = "My Galaxy tablet screen stays completely blank when I try to use Smart Switch to scan the QR code"
    assert _plan_key("connectivity", query) == "display"
    plan = _plan(query)
    assert plan["title"] != "Network connection issue"
    assert "Transfer" in plan["goal"] or plan["title"] == "Screen display damage"


@pytest.mark.parametrize("query, kept, dropped", [
    ("wifi keeps dropping", "View WiFi Settings", "View Bluetooth"),
    ("bluetooth won't connect to my earbuds", "View Bluetooth", "View WiFi Settings"),
    ("mobile data keeps disconnecting", "View Mobile Networks", "View WiFi Settings"),
])
def test_network_plan_focuses_on_the_named_radio(query, kept, dropped):
    names = [a["actionName"] for a in _plan(query)["actions"]]
    assert kept in names
    assert dropped not in names


def test_unknown_domain_falls_back_to_display_plan():
    assert _plan_key("unknown", "") == "display"


@pytest.mark.parametrize("domain", ALL_KEYS)
def test_every_plan_description_is_already_a_complete_5_to_7_word_sentence(domain):
    for action in _build_domain_plan(domain, "", "", "wifi bluetooth mobile data")["contexts"][0]["actions"]:
        raw = action["description"]
        assert raw.startswith("It will ") and raw.endswith(".")
        assert 5 <= len(raw.rstrip(".").split()) <= 7, raw
        assert format_action_description(raw, action["actionName"], domain) == raw


@pytest.mark.parametrize("domain", ALL_KEYS)
def test_every_plan_puts_critical_actions_last(domain):
    categories = [a["category"] for a in _build_domain_plan(domain, "", "", "wifi")["contexts"][0]["actions"]]
    assert "critical" not in categories or all(c == "critical" for c in categories[categories.index("critical"):])
