from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.schemas.troubleshooting_plan import Goal


class TroubleshootRequest(BaseModel):  # define the schema of request
    query: str = Field(..., min_length=1, max_length=settings.max_query_chars)
    siis_response: Optional[Dict] = None

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class TroubleshootResponse(BaseModel):  # define the schema of response
    contexts: List[Goal] = []
    query_variations: Optional[List[str]] = None
    fallback: Optional[str] = None
