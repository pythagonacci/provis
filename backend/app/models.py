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
    imports: int  # Total imports (for backward compatibility)
    importsTotal: int = Field(..., description="Total number of imports (internal + external)")
    importsInternal: int = Field(..., description="Number of internal imports resolved to repo files")
    importsExternal: int = Field(..., description="Number of external imports (stdlib, npm, etc.)")
    filesSummarized: int = Field(0, description="Number of files with LLM summaries")
    capabilitiesBuilt: int = Field(0, description="Number of capabilities generated")
    warnings: list[str] = []
    error: Optional[str] = None
