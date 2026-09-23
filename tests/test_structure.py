"""Unit tests for Stage 2 Troubleshooting Engine and Strict Constraint Validation."""
import importlib.util
from pathlib import Path
import pytest
from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import generate_troubleshooting_plan
from backend.schemas.troubleshooting_plan import ActionCategory, TroubleshootingPlan

# Load official schema
OFFICIAL_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema.py"
spec = importlib.util.spec_from_file_location("official_schema", OFFICIAL_SCHEMA_PATH)
official_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(official_schema)


class TestTroubleshootingStructure:
    """Test suite for strict Theme 02 schema constraints and ordering rules."""

    @pytest.mark.parametrize(
        "query",
        [
            "My phone battery drains in 3 hours and gets hot",
            "Screen flashes intermittently and goes black",
            "Camera autofocus is blurry and out of focus",
            "Apps keep crashing and system response is very laggy",
            "Galaxy phone won't turn on after update",
        ],
    )
    def test_schema_constraints(self, query: str):
        """Verify 2-3 word title, 50-70 word description, and prefix on multiple scenarios."""
        enriched = enrich_query(query)
        plan = generate_troubleshooting_plan(enriched)

        # 1. Pydantic validation on local schema
        tp = TroubleshootingPlan(**plan)
        assert len(tp.contexts) > 0

        # 2. Pydantic validation on official Samsung schema.py
        official_resp = official_schema.ContextDeeplinkResponse(**plan)
        assert len(official_resp.contexts) > 0

        goal = tp.contexts[0]

        # 3. Title Constraint: exactly 2 to 3 words
        title_words = goal.title.strip().split()
        assert 2 <= len(title_words) <= 3, f"Title '{goal.title}' must be 2-3 words (got {len(title_words)})"

        # 4. Action constraints
        assert len(goal.actions) > 0
        found_critical = False
        critical_indices = []

        for idx, action in enumerate(goal.actions):
            desc = action.description.strip()
            words = desc.split()

            # Rule: Must start with 'It will '
            assert desc.startswith("It will "), f"Action description must start with 'It will ': {desc[:30]}"

            # Rule: Must contain between 50 and 70 words
            assert 50 <= len(words) <= 70, (
                f"Action '{action.actionName}' description has {len(words)} words; must be 50-70 words: '{desc}'"
            )

            # Rule: No URLs in steps
            for sg in action.stepGroups:
                for step in sg.steps:
                    assert "http" not in step.lower(), f"URL found in step: {step}"
                    assert "bixby://" not in step.lower(), f"Deeplink found in step: {step}"

            # Track category indices
            if action.category == ActionCategory.critical or action.category == "critical":
                found_critical = True
                critical_indices.append(idx)
            else:
                # If a critical action was already found earlier, this is an ordering violation!
                assert not found_critical, (
                    f"Non-critical action '{action.actionName}' found at index {idx} after critical action!"
                )

            # Rule: Manual action cannot have actionableDeeplink
            if action.category == ActionCategory.manual or action.category == "manual":
                for sg in action.stepGroups:
                    assert sg.actionableDeeplink is None, f"Manual action has non-null deeplink: {sg}"

    def test_critical_actions_ordering(self):
        """Explicitly verify that critical actions are sorted to the end."""
        enriched = enrich_query("My phone is lagging and I might need to factory reset or safe mode")
        plan = generate_troubleshooting_plan(enriched)
        actions = plan["contexts"][0]["actions"]

        # Ensure that any critical action comes after standard/auto actions
        has_seen_critical = False
        for action in actions:
            cat = action.get("category")
            if cat == "critical":
                has_seen_critical = True
            elif has_seen_critical:
                pytest.fail(f"Standard action '{action.get('actionName')}' appeared after critical action!")
