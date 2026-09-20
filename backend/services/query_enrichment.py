def enrich_query(query):
    return {
        "technical_query": query,
        "domain": "unknown",
        "issue": query,
        "context": []
    }