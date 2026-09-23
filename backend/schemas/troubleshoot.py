from typing import Dict, List, Optional

from pydantic import BaseModel

from backend.schemas.troubleshooting_plan import Goal


class TroubleshootRequest(BaseModel):  # define the schema of request
    query: str
    siis_response: Optional[Dict] = None


class TroubleshootResponse(BaseModel):  # define the schema of response
    contexts: List[Goal] = []
    query_variations: Optional[List[str]] = None
    fallback: Optional[str] = None
