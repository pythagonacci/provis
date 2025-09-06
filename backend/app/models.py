from pydantic import BaseModel, Field
from typing import Literal, Optional

Phase = Literal[
    "queued", "acquiring", "discovering", "parsing",
    "mapping", "summarizing", "done", "failed",
]

class IngestResponse(BaseModel):
    repoId: str = Field(..., description="Repository identifier")
    jobId: str = Field(..., description="Background job identifier")

class StatusPayload(BaseModel):
    jobId: str
    repoId: str
    phase: Phase
    pct: int
    filesParsed: int
    imports: int
    warnings: list[str] = []
    error: Optional[str] = None
