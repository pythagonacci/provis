from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any, Union
from datetime import datetime

Phase = Literal[
    "queued", "acquiring", "discovering", "parsing", "merging",
    "mapping", "summarizing", "finalizing", "done", "failed",
]

# Evidence and confidence tracking
class EvidenceSpan(BaseModel):
    file: str = Field(..., description="File path")
    start: int = Field(..., description="Start line number (1-based)")
    end: int = Field(..., description="End line number (1-based)")

class ReasonCode(BaseModel):
    code: Literal[
        "alias-miss", "dynamic-import", "factory-decorator", "pnp", 
        "namespace-pkg", "skipped_large", "timeout", "rate-limit", "unknown"
    ] = Field(..., description="Reason code for degradation")

class WarningItem(BaseModel):
    phase: str = Field(..., description="Phase where warning occurred")
    file: Optional[str] = Field(None, description="File where warning occurred")
    reason_code: str = Field(..., description="Reason code")
    evidence: Optional[EvidenceSpan] = Field(None, description="Evidence span")
    message: str = Field(..., description="Warning message")
    count: int = Field(1, description="Number of occurrences")

class ArtifactMetadata(BaseModel):
    schema_version: str = Field("2.0", description="Schema version")
    content_hash: str = Field(..., description="Content hash for integrity")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    repo_id: str = Field(..., description="Repository identifier")

# ---- Evidence-bound Parser Schema ----
class ImportModel(BaseModel):
    raw: str = Field(..., description="Original import string")
    resolved: Optional[str] = Field(None, description="Resolved file path if internal")
    external: bool = Field(True, description="Whether this is an external dependency")
    kind: Literal["esm", "cjs", "py"] = Field(..., description="Import type")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")
    hypothesis: bool = Field(False, description="Whether this is a hypothesis")
    reason_code: Optional[str] = Field(None, description="Reason code if degraded")

class FunctionModel(BaseModel):
    name: str = Field(..., description="Function name")
    params: List[str] = Field(default_factory=list, description="Parameter names")
    decorators: List[str] = Field(default_factory=list, description="Decorator names")
    returns: Optional[str] = Field(None, description="Return type annotation")
    calls: List[str] = Field(default_factory=list, description="Functions called within")
    sideEffects: List[str] = Field(default_factory=list, description="Side effect tags")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")

class ClassModel(BaseModel):
    name: str = Field(..., description="Class name")
    methods: List[str] = Field(default_factory=list, description="Method names")
    baseClasses: List[str] = Field(default_factory=list, description="Base class names")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")

class RouteModel(BaseModel):
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="Route path")
    handler: str = Field(..., description="Handler function name")
    middlewares: List[str] = Field(default_factory=list, description="Middleware chain")
    statusCodes: List[int] = Field(default_factory=list, description="HTTP status codes")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")
    hypothesis: bool = Field(False, description="Whether this is a hypothesis")
    reason_code: Optional[str] = Field(None, description="Reason code if degraded")

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
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")
    skipped_large: bool = Field(False, description="Whether file was skipped due to size")

# Graph models
class GraphEdge(BaseModel):
    src: str = Field(..., description="Source node")
    dst: str = Field(..., description="Target node") 
    kind: Literal["import", "route", "job", "call", "store", "external", "middleware", "class"] = Field(..., description="Edge type")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    confidence: float = Field(1.0, description="Confidence score (0-1)")
    hypothesis: bool = Field(False, description="Whether this is a hypothesis")
    reason_code: Optional[str] = Field(None, description="Reason code if degraded")

class GraphModel(BaseModel):
    imports: List[GraphEdge] = Field(default_factory=list, description="Import edges")
    routes: List[GraphEdge] = Field(default_factory=list, description="Route edges")
    jobs: List[GraphEdge] = Field(default_factory=list, description="Job edges")
    calls: List[GraphEdge] = Field(default_factory=list, description="Call edges")
    stores: List[GraphEdge] = Field(default_factory=list, description="Store edges")
    externals: List[GraphEdge] = Field(default_factory=list, description="External edges")
    middleware: List[GraphEdge] = Field(default_factory=list, description="Middleware edges")
    classes: List[GraphEdge] = Field(default_factory=list, description="Class edges")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Graph statistics")
    metadata: ArtifactMetadata = Field(..., description="Artifact metadata")

# Capability models
class DataFlowModel(BaseModel):
    inputs: List[Dict[str, Any]] = Field(default_factory=list, description="Input data sources")
    stores: List[Dict[str, Any]] = Field(default_factory=list, description="Data stores")
    externals: List[Dict[str, Any]] = Field(default_factory=list, description="External services")
    outputs: List[Dict[str, Any]] = Field(default_factory=list, description="Output data")

class CapabilityModel(BaseModel):
    id: str = Field(..., description="Capability identifier")
    name: str = Field(..., description="Capability name")
    purpose: str = Field(..., description="Capability purpose")
    entrypoints: List[str] = Field(default_factory=list, description="Entry points")
    orchestrators: List[str] = Field(default_factory=list, description="Orchestrator files")
    control_flow: List[GraphEdge] = Field(default_factory=list, description="Control flow edges")
    data_flow: DataFlowModel = Field(default_factory=DataFlowModel, description="Data flow")
    policies: List[Dict[str, Any]] = Field(default_factory=list, description="Policies")
    contracts: List[Dict[str, Any]] = Field(default_factory=list, description="Contracts")
    lanes: Dict[str, List[str]] = Field(default_factory=dict, description="Swimlanes")
    evidence: List[EvidenceSpan] = Field(default_factory=list, description="Evidence spans")
    suggested_edges: List[GraphEdge] = Field(default_factory=list, description="Hypothesis edges")

class IngestResponse(BaseModel):
    repoId: str = Field(..., description="Repository identifier")
    jobId: str = Field(..., description="Background job identifier")
    snapshotId: str = Field(..., description="Snapshot identifier")
    commitHash: Optional[str] = Field(None, description="Commit hash")
    settingsHash: str = Field(..., description="Settings hash")

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
    
    # New robust metrics
    unresolved_import_ratio: float = Field(0.0, description="Ratio of unresolved imports")
    hypothesis_edge_ratio: float = Field(0.0, description="Ratio of hypothesis edges")
    detector_hit_rates: Dict[str, float] = Field(default_factory=dict, description="Detector hit rates")
    big_file_ratio: float = Field(0.0, description="Ratio of big files")
    llm_tokens_in: int = Field(0, description="LLM input tokens used")
    llm_tokens_out: int = Field(0, description="LLM output tokens used")
    phase_timings: Dict[str, float] = Field(default_factory=dict, description="Phase timings in seconds")


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
