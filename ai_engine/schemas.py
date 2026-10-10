
from typing import Literal

from pydantic import BaseModel, Field


class RepairProposal(BaseModel):
    change_summary: str
    evidence: list[str]
    potential_impact: str
    proposed_repair: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_validation: Literal[True] = True
