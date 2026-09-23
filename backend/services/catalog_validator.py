"""Catalog loading and integrity checks for M2."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ("id", "deeplink", "description")


class CatalogError(ValueError):
    """Raised when the trusted deeplink catalog is malformed."""


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("deeplinks") if isinstance(payload, dict) else payload

    if not isinstance(entries, list):
        raise CatalogError("deeplinks.json must contain a 'deeplinks' list")

    ids: set[str] = set()
    deeplinks: set[str] = set()

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CatalogError(f"Entry {i} is not an object")

        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            raise CatalogError(f"Entry {i} missing required fields: {missing}")

        if entry["id"] in ids:
            raise CatalogError(f"Duplicate catalog id: {entry['id']}")
        if entry["deeplink"] in deeplinks:
            raise CatalogError(f"Duplicate deeplink: {entry['deeplink']}")

        ids.add(entry["id"])
        deeplinks.add(entry["deeplink"])

    return entries


def validate_resolved_entry(
    entry: dict[str, Any],
    catalog_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return violations for a resolved catalog entry."""
    violations: list[str] = []
    catalog_id = entry.get("catalogId")

    if not catalog_id:
        violations.append("missing catalogId")
        return violations

    trusted = catalog_by_id.get(catalog_id)
    if trusted is None:
        violations.append(f"catalogId not found: {catalog_id}")
        return violations

    if entry.get("actionableDeeplink") != trusted.get("deeplink"):
        violations.append(f"deeplink does not equal trusted catalog value for {catalog_id}")

    return violations
