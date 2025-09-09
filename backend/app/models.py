from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict

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


# ---- V1 models (lightweight contracts) ----
class FunctionModel(BaseModel):
    name: str
    sideEffects: List[str] | None = None

class FileNodeModel(BaseModel):
    id: str
    path: str
    purpose: str | None = ""
    exports: List[str] | None = []
    imports: List[str] | None = []
    functions: List[FunctionModel] | None = []

class FolderNodeModel(BaseModel):
    id: str
    path: str
    purpose: str | None = ""
    children: List['FolderNodeModel | FileNodeModel']

class CapabilitySummaryModel(BaseModel):
    id: str
    name: str
    purpose: Optional[str] = None
    entryPoints: Optional[List[str]] = None

class EdgeModel(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    kind: Literal["import","call","http","queue","webhook","component"] = "import"

class PolicyModel(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    path: Optional[str] = None
    appliedAt: Optional[str] = None

class ContractModel(BaseModel):
    name: str
    kind: str
    path: Optional[str] = None
    fields: Optional[List[str]] = None

class CapabilityDetailModel(BaseModel):
    id: str
    name: str
    purpose: Optional[str] = None
    entryPoints: Optional[List[str]] = None
    controlFlow: List[EdgeModel] = []
    dataFlow: Dict[str, List[Dict[str, str]]] = {}
    swimlanes: Dict[str, List[str]] = {}
    steps: List[Dict[str, Optional[str]]] = []
    nodeIndex: Dict[str, Dict[str, object]] = {}
    policies: List[PolicyModel] = []
    contracts: List[ContractModel] = []

class RepoOverviewModel(BaseModel):
    tree: Dict[str, object] | FolderNodeModel
    files: Dict[str, object]
    capabilities: List[CapabilitySummaryModel]
    metrics: Dict[str, object]

FolderNodeModel.model_rebuild()
