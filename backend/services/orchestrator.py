from backend.services.query_processor import process_query


def troubleshoot(query: str):
    result = process_query(query)

    return result