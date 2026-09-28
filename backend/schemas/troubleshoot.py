from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.schemas.troubleshooting_plan import Goal

MAX_SIIS_CHARS = 20000


class TroubleshootRequest(BaseModel):  # define the schema of request
    query: str = Field(..., min_length=1, max_length=settings.max_query_chars)
    siis_response: Optional[Union[str, Dict]] = None

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value

    @field_validator("siis_response")
    @classmethod
    def siis_as_document(cls, value: Optional[Union[str, Dict]]) -> Optional[Dict]:
        if isinstance(value, str):
            if len(value) > MAX_SIIS_CHARS:
                raise ValueError(f"siis_response must be at most {MAX_SIIS_CHARS} characters")
            return {"title": "", "content": value.strip()} if value.strip() else None
        return value or None


class TroubleshootResponse(BaseModel):  # define the schema of response
    contexts: List[Goal] = []
    query_variations: Optional[List[str]] = None
    fallback: Optional[str] = None
