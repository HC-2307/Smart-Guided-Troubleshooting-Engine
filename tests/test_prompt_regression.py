"""Regression test suite running against all 20 official Samsung PRISM Theme 02 benchmark queries."""
import importlib.util
from pathlib import Path
import pytest
from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import generate_troubleshooting_plan
from backend.schemas.enriched_query import EnrichedQuery
from backend.schemas.troubleshooting_plan import ActionCategory, TroubleshootingPlan

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_TXT_PATH = BASE_DIR / "data" / "input.txt"
OFFICIAL_SCHEMA_PATH = BASE_DIR / "data" / "schema.py"

# Load official schema
spec = importlib.util.spec_from_file_location("official_schema", OFFICIAL_SCHEMA_PATH)
official_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(official_schema)


def load_benchmark_queries():
    """Load benchmark queries from data/input.txt."""
    if not INPUT_TXT_PATH.exists():
        return []
    queries = []
    for line in INPUT_TXT_PATH.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            queries.append(clean)
    return queries


BENCHMARK_QUERIES = load_benchmark_queries()


class TestBenchmarkRegression:
    """Run regression against all 20 real benchmark inputs."""

    def test_benchmark_queries_loaded(self):
        assert len(BENCHMARK_QUERIES) >= 15, f"Expected at least 15 queries in input.txt, found {len(BENCHMARK_QUERIES)}"

    @pytest.mark.parametrize("query", BENCHMARK_QUERIES)
    def test_end_to_end_query_processing(self, query: str):
        # 1. Run Stage 1 Enrichment
        enriched = enrich_query(query)
        eq = EnrichedQuery(**enriched)
        assert eq.domain in [
            "battery", "display", "camera", "performance", "connectivity", "audio", "storage", "system"
        ]
        assert len(eq.query_variations) >= 8

        # 2. Run Stage 2 Troubleshooting Structure
        plan = generate_troubleshooting_plan(enriched)
        tp = TroubleshootingPlan(**plan)
        assert len(tp.contexts) > 0

        # Validate against official Samsung schema.py
        official_resp = official_schema.ContextDeeplinkResponse(**plan)
        assert len(official_resp.contexts) > 0

        goal = tp.contexts[0]

        # 3. Validate Title length (2 to 3 words)
        title_words = goal.title.strip().split()
        assert 2 <= len(title_words) <= 3, f"Title '{goal.title}' has {len(title_words)} words"

        # 4. Validate Actions
        assert len(goal.actions) > 0
        has_seen_critical = False

        for idx, action in enumerate(goal.actions):
            desc = action.description.strip()
            words = desc.split()

            # Word count: 50-70 words
            assert 50 <= len(words) <= 70, (
                f"Action '{action.actionName}' in query '{query[:40]}' has {len(words)} words; required 50-70: '{desc}'"
            )

            # Prefix: 'It will '
            assert desc.startswith("It will "), f"Action description must start with 'It will ': '{desc[:30]}'"

            # Ordering: critical actions last
            if action.category == ActionCategory.critical or action.category == "critical":
                has_seen_critical = True
            elif has_seen_critical:
                pytest.fail(f"Non-critical action '{action.actionName}' appeared after critical action at index {idx}")

            # Steps: No URLs
            for sg in action.stepGroups:
                for step in sg.steps:
                    assert "http" not in step.lower()
                    assert "bixby://" not in step.lower()
