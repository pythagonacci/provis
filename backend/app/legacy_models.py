"""
Legacy models for backward compatibility with existing API contracts.
These are lightweight versions used by the frontend and existing endpoints.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

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
