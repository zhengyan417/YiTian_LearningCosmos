"""Request and response schemas for the deep research API."""

import re

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.schemas.base import BaseResponse


class ResearchRequest(BaseModel):
    """Request model for the deep research endpoint.

    Attributes:
        query: The user's research question.
    """

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The research question to investigate",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Reject obviously dangerous payloads (script tags, null bytes)."""
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("query contains potentially harmful script tags")
        if "\0" in v:
            raise ValueError("query contains null bytes")
        return v


class ResearchResponse(BaseResponse):
    """Response model for the deep research endpoint.

    Attributes:
        thread_id: Internal thread id used for checkpointing.
        report: The synthesized markdown report.
    """

    thread_id: str = Field(..., description="Unique thread id for this research run")
    report: str = Field(..., description="The synthesized markdown report")
