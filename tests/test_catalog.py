from pathlib import Path
from backend.services.catalog_validator import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_expected_shape_and_unique_ids():
    entries = load_catalog(ROOT / "data" / "deeplinks.json")
    assert len(entries) == 578
    assert len({e["id"] for e in entries}) == 578
    assert len({e["deeplink"] for e in entries}) == 578
