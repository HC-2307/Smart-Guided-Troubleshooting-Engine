"""Pydantic data models for Stage 1 Query Enrichment."""
from typing import List
from pydantic import BaseModel, Field


class EnrichedQuery(BaseModel):
    """Enriched representation of the user complaint after Stage 1 normalisation."""

    original_query: str = Field(..., description="Raw user input complaint string")
    technical_query: str = Field(
        ..., description="Normalized technical query representing the underlying defect"
    )
    domain: str = Field(
        ...,
        description="Target hardware/software domain: battery, display, camera, performance, connectivity, audio, storage, system",
    )
    issue: str = Field(..., description="Concise statement of the core issue")
    context: List[str] = Field(
        default_factory=list,
        description="Extracted situational modifiers (e.g., overheating, charging, startup)",
    )
    query_variations: List[str] = Field(
        default_factory=list,
        description="8 to 10 diverse register paraphrases (slang, formal, panic, brief, verbose)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score between 0.0 and 1.0",
    )
