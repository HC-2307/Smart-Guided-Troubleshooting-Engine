from backend.services.query_enrichment import enrich_query
from backend.services.troubleshooting_engine import generate_troubleshooting_plan


def process_query(query: str):
    enriched_query = enrich_query(query)

    troubleshooting_plan = generate_troubleshooting_plan(
        enriched_query
    )

    return troubleshooting_plan