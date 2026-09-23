"""Unit tests for Stage 1 Query Enrichment Service."""
import pytest
from backend.services.query_enrichment import enrich_query
from backend.schemas.enriched_query import EnrichedQuery


class TestQueryEnrichment:
    """Test suite for query enrichment, classification, and variations."""

    def test_battery_domain_enrichment(self):
        query = "My battery is draining really fast and phone gets hot"
        res = enrich_query(query)
        validated = EnrichedQuery(**res)
        assert validated.domain == "battery"
        assert "battery" in validated.technical_query.lower()
        assert len(validated.query_variations) >= 8
        assert len(validated.query_variations) <= 12

    def test_display_domain_enrichment(self):
        query = "Screen flickers green and goes completely blank when tapping apps"
        res = enrich_query(query)
        validated = EnrichedQuery(**res)
        assert validated.domain == "display"
        assert any(w in validated.technical_query.lower() for w in ["display", "screen", "blackout"])
        assert len(validated.query_variations) >= 8

    def test_camera_domain_enrichment(self):
        query = "Rear camera won't focus and all my close-up photos come out blurry"
        res = enrich_query(query)
        validated = EnrichedQuery(**res)
        assert validated.domain == "camera"
        assert "camera" in validated.technical_query.lower()
        assert len(validated.query_variations) >= 8

    def test_performance_domain_enrichment(self):
        query = "My Galaxy phone is lagging badly and touch response has a huge delay"
        res = enrich_query(query)
        validated = EnrichedQuery(**res)
        assert validated.domain == "performance"
        assert any(w in validated.technical_query.lower() for w in ["latency", "performance", "input delay"])
        assert len(validated.query_variations) >= 8

    def test_symptom_preservation(self):
        """Ensure no unmentioned symptoms (like water damage or cracks) are hallucinated."""
        query = "Battery discharges in 2 hours without playing any games"
        res = enrich_query(query)
        t_query = res["technical_query"].lower()
        assert "crack" not in t_query
        assert "liquid" not in t_query
        assert "water" not in t_query
        assert "screen" not in t_query

    def test_query_variations_diversity(self):
        query = "My phone died suddenly and won't turn back on"
        res = enrich_query(query)
        variations = res["query_variations"]
        assert len(variations) >= 8
        # Ensure all variations are distinct non-empty strings
        assert len(set(variations)) == len(variations)
        for var in variations:
            assert len(var.strip()) > 10

    def test_edge_case_empty_query(self):
        res = enrich_query("")
        validated = EnrichedQuery(**res)
        assert validated.domain in ["system", "performance", "battery"]
        assert len(validated.query_variations) >= 8
