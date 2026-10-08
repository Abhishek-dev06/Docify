"""Human decision requests; no anonymous claim of authenticated officer identity."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["approve", "secondary_inspection", "reject"]


class Officer(BaseModel):
    name: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Decision
    note: str = Field(min_length=8, max_length=500)
    expected_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: UUID
    acknowledge_incomplete: bool = False
