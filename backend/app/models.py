from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any, Union

Phase = Literal[
    "queued", "acquiring", "discovering", "parsing",
    "mapping", "summarizing", "done", "failed",
]

# ---- Unified Parser Schema ----
class ImportModel(BaseModel):
    raw: str = Field(..., description="Original import string")
    resolved: Optional[str] = Field(None, description="Resolved file path if internal")
    external: bool = Field(True, description="Whether this is an external dependency")
    kind: Literal["esm", "cjs", "py"] = Field(..., description="Import type")

class FunctionModel(BaseModel):
    name: str = Field(..., description="Function name")
    params: List[str] = Field(default_factory=list, description="Parameter names")
    decorators: List[str] = Field(default_factory=list, description="Decorator names")
    returns: Optional[str] = Field(None, description="Return type annotation")
    calls: List[str] = Field(default_factory=list, description="Functions called within")
    sideEffects: List[str] = Field(default_factory=list, description="Side effect tags")

class ClassModel(BaseModel):
    name: str = Field(..., description="Class name")
    methods: List[str] = Field(default_factory=list, description="Method names")
    baseClasses: List[str] = Field(default_factory=list, description="Base class names")

class RouteModel(BaseModel):
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="Route path")
    handler: str = Field(..., description="Handler function name")
    middlewares: List[str] = Field(default_factory=list, description="Middleware chain")
    statusCodes: List[int] = Field(default_factory=list, description="HTTP status codes")

class SymbolsModel(BaseModel):
    constants: List[str] = Field(default_factory=list, description="Constant declarations")
    hooks: List[str] = Field(default_factory=list, description="React hooks used")
    dbModels: List[str] = Field(default_factory=list, description="Database model classes")
    middleware: List[str] = Field(default_factory=list, description="Middleware functions/classes")
    components: List[str] = Field(default_factory=list, description="React components")
    utilities: List[str] = Field(default_factory=list, description="Utility functions")

class FileNodeModel(BaseModel):
    path: str = Field(..., description="Repo-relative file path")
    language: Literal["js", "ts", "py"] = Field(..., description="Programming language")
    exports: List[str] = Field(default_factory=list, description="Exported symbols")
    imports: List[ImportModel] = Field(default_factory=list, description="Import statements")
    functions: List[FunctionModel] = Field(default_factory=list, description="Function declarations")
    classes: List[ClassModel] = Field(default_factory=list, description="Class declarations")
    routes: List[RouteModel] = Field(default_factory=list, description="Route definitions")
    symbols: SymbolsModel = Field(default_factory=SymbolsModel, description="Framework-specific symbols")
    hints: Dict[str, Any] = Field(default_factory=dict, description="Framework hints")

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


# API Response Models
class RepoOverviewModel(BaseModel):
    tree: Dict[str, Any]
    files: Dict[str, Any] 
    capabilities: List[Dict[str, Any]]
    metrics: Dict[str, Any]

class CapabilitySummaryModel(BaseModel):
    id: str
    name: str
    purpose: str
    entryPoints: List[str] = Field(default_factory=list)
    keyFiles: List[str] = Field(default_factory=list)
    dataIn: List[str] = Field(default_factory=list)
    dataOut: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    sinks: List[str] = Field(default_factory=list)

class CapabilityDetailModel(BaseModel):
    id: str
    name: str
    purpose: str
    entryPoints: List[str] = Field(default_factory=list)
    orchestrators: List[str] = Field(default_factory=list)
    keyFiles: List[str] = Field(default_factory=list)
    dataIn: List[str] = Field(default_factory=list)
    dataOut: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    sinks: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    controlFlow: List[Dict[str, Any]] = Field(default_factory=list)
    dataFlow: Dict[str, Any] = Field(default_factory=dict)
    swimlanes: Dict[str, Any] = Field(default_factory=dict)
    nodeIndex: Dict[str, Any] = Field(default_factory=dict)
    policies: List[Dict[str, Any]] = Field(default_factory=list)
    contracts: List[Dict[str, Any]] = Field(default_factory=list)
    suspectRank: List[str] = Field(default_factory=list)
    recentChanges: List[Dict[str, Any]] = Field(default_factory=list)

# Legacy models moved to legacy_models.py for backward compatibility
