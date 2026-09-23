"""High-level M2 Knowledge/Deeplink Engine."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .deeplink_resolver import DeeplinkResolver
from .sequence_engine import apply_sequence_rules


class M2Engine:
    def __init__(self, catalog_path: str | Path):
        self.resolver = DeeplinkResolver(catalog_path)

    def process_plan(self, plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        resolved, report = self.resolver.resolve_plan(plan)
        ordered, sequence_violations = apply_sequence_rules(resolved)
        report["sequence_violations"] = sequence_violations
        report["ready_for_m3"] = not sequence_violations and not report["unresolved"]
        return ordered, report
