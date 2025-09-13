"""
Capabilities v2: Lanes by provenance, centrality analysis, and comprehensive data/policies/contracts.
Computes orchestrators, control flow, data flow, and policies with evidence tracking.
"""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import logging

from .config import settings
from .models import (
    CapabilityModel, DataFlowModel, GraphModel, GraphEdge, 
    EvidenceSpan, WarningItem, RouteModel, ImportModel
)
from .observability import record_detector_hit, record_fallback
from .events import event_manager

logger = logging.getLogger(__name__)

@dataclass
class ProvenanceAnalysis:
    """Analysis of code provenance for lane assignment."""
    entrypoints: List[str] = field(default_factory=list)
    orchestrators: List[str] = field(default_factory=list)
    data_stores: List[str] = field(default_factory=list)
    external_services: List[str] = field(default_factory=list)
    policies: List[Dict[str, Any]] = field(default_factory=list)
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[EvidenceSpan] = field(default_factory=list)
    confidence: float = 1.0
    hypothesis: bool = False
    reason_code: Optional[str] = None

@dataclass
class CentralityMetrics:
    """Centrality metrics for capability ranking."""
    betweenness_centrality: float = 0.0
    closeness_centrality: float = 0.0
    degree_centrality: float = 0.0
    eigenvector_centrality: float = 0.0
    evidence: List[EvidenceSpan] = field(default_factory=list)
    confidence: float = 1.0
    hypothesis: bool = False

@dataclass
class CapabilityContext:
    """Context for capability analysis."""
    repo_root: Path
    preflight_data: Dict[str, Any]
    graph: GraphModel
    static_layer: Dict[str, Any]
    llm_layer: Optional[Dict[str, Any]] = None
    job_id: Optional[str] = None

class CapabilityAnalyzer:
    """Analyzes capabilities with provenance-based lane assignment."""
    
    def __init__(self, context: CapabilityContext):
        self.context = context
        self.repo_root = context.repo_root
        self.preflight_data = context.preflight_data
        self.graph = context.graph
        self.static_layer = context.static_layer
        self.llm_layer = context.llm_layer or {}
        
        # Analysis results
        self.capabilities: List[CapabilityModel] = []
        self.provenance_analysis: Dict[str, ProvenanceAnalysis] = {}
        self.centrality_metrics: Dict[str, CentralityMetrics] = {}
        
        # Lane definitions
        self.lanes = {
            "web": {"description": "Web interfaces and user-facing routes", "patterns": ["/", "/app/", "/pages/"]},
            "api": {"description": "API endpoints and services", "patterns": ["/api/", "/graphql/", "/rpc/"]},
            "worker": {"description": "Background jobs and async processing", "patterns": ["/workers/", "/jobs/", "/tasks/"]},
            "scheduler": {"description": "Scheduled tasks and cron jobs", "patterns": ["/scheduler/", "/cron/", "/periodic/"]},
            "cli": {"description": "Command-line interfaces and scripts", "patterns": ["/cli/", "/scripts/", "/bin/"]},
        }
    
    async def analyze_capabilities(self) -> List[CapabilityModel]:
        """Analyze all capabilities in the repository."""
        logger.info("Starting capability analysis")
        
        # 1. Identify entrypoints
        entrypoints = await self._identify_entrypoints()
        
        # 2. Analyze each entrypoint
        for entrypoint in entrypoints:
            try:
                capability = await self._analyze_entrypoint(entrypoint)
                if capability:
                    self.capabilities.append(capability)
            except Exception as e:
                logger.error(f"Failed to analyze entrypoint {entrypoint}: {e}")
                continue
        
        # 3. Compute centrality metrics
        await self._compute_centrality_metrics()
        
        # 4. Rank capabilities by importance
        self._rank_capabilities()
        
        logger.info(f"Capability analysis complete: {len(self.capabilities)} capabilities identified")
        return self.capabilities
    
    async def _identify_entrypoints(self) -> List[str]:
        """Identify entrypoints from routes, jobs, and CLI scripts."""
        entrypoints = set()
        
        # From routes
        for edge in self.graph.edges:
            if edge.kind == "routes":
                entrypoints.add(edge.from_node)
        
        # From jobs
        for edge in self.graph.edges:
            if edge.kind == "jobs":
                entrypoints.add(edge.from_node)
        
        # From file analysis
        for file_path, file_data in self.static_layer.get("files", {}).items():
            if self._is_entrypoint_file(file_path, file_data):
                entrypoints.add(file_path)
        
        # From LLM layer
        for file_path, llm_data in self.llm_layer.items():
            if self._is_entrypoint_file(file_path, llm_data):
                entrypoints.add(file_path)
        
        return list(entrypoints)
    
    def _is_entrypoint_file(self, file_path: str, file_data: Dict[str, Any]) -> bool:
        """Determine if a file is an entrypoint."""
        # Check file name patterns
        file_name = Path(file_path).name.lower()
        entrypoint_patterns = [
            "main", "index", "app", "server", "start",
            "cli", "command", "script", "worker", "job"
        ]
        
        if any(pattern in file_name for pattern in entrypoint_patterns):
            return True
        
        # Check for main functions
        if "main" in file_data.get("functions", []):
            return True
        
        # Check for route definitions
        if file_data.get("routes"):
            return True
        
        # Check for job definitions
        if file_data.get("jobs"):
            return True
        
        return False
    
    async def _analyze_entrypoint(self, entrypoint: str) -> Optional[CapabilityModel]:
        """Analyze a single entrypoint to create a capability."""
        logger.debug(f"Analyzing entrypoint: {entrypoint}")
        
        # 1. Analyze provenance
        provenance = await self._analyze_provenance(entrypoint)
        
        # 2. Determine lane
        lane = self._determine_lane(entrypoint, provenance)
        
        # 3. Compute orchestrators
        orchestrators = await self._compute_orchestrators(entrypoint, provenance)
        
        # 4. Build control flow
        control_flow = await self._build_control_flow(entrypoint)
        
        # 5. Build data flow
        data_flow = await self._build_data_flow(entrypoint, provenance)
        
        # 6. Extract policies
        policies = await self._extract_policies(entrypoint, provenance)
        
        # 7. Extract contracts
        contracts = await self._extract_contracts(entrypoint, provenance)
        
        # 8. Generate capability metadata
        capability_id = self._generate_capability_id(entrypoint, lane)
        name = self._generate_capability_name(entrypoint, lane)
        purpose = self._generate_capability_purpose(entrypoint, lane, data_flow)
        
        # 9. Collect evidence
        evidence = self._collect_capability_evidence(entrypoint, provenance, control_flow, data_flow)
        
        # 10. Identify suggested edges
        suggested_edges = self._identify_suggested_edges(entrypoint, control_flow, data_flow)
        
        return CapabilityModel(
            id=capability_id,
            name=name,
            purpose=purpose,
            entrypoints=[entrypoint],
            orchestrators=orchestrators,
            control_flow=control_flow,
            data_flow=data_flow,
            policies=policies,
            contracts=contracts,
            lanes=[lane],
            evidence=evidence,
            suggested_edges=suggested_edges
        )
    
    async def _analyze_provenance(self, entrypoint: str) -> ProvenanceAnalysis:
        """Analyze the provenance of an entrypoint."""
        provenance = ProvenanceAnalysis()
        
        # Collect evidence from graph edges
        evidence = []
        
        # Find routes associated with this entrypoint
        for edge in self.graph.edges:
            if edge.kind == "routes" and edge.from_node == entrypoint:
                provenance.entrypoints.append(edge.to_node)
                evidence.extend(edge.evidence)
        
        # Find jobs associated with this entrypoint
        for edge in self.graph.edges:
            if edge.kind == "jobs" and edge.from_node == entrypoint:
                provenance.entrypoints.append(edge.to_node)
                evidence.extend(edge.evidence)
        
        # Find orchestrators (files that coordinate this capability)
        orchestrators = await self._find_orchestrators(entrypoint)
        provenance.orchestrators.extend(orchestrators)
        
        # Find data stores
        data_stores = await self._find_data_stores(entrypoint)
        provenance.data_stores.extend(data_stores)
        
        # Find external services
        external_services = await self._find_external_services(entrypoint)
        provenance.external_services.extend(external_services)
        
        # Extract policies and contracts
        provenance.policies = await self._extract_policies(entrypoint, provenance)
        provenance.contracts = await self._extract_contracts(entrypoint, provenance)
        
        provenance.evidence = evidence
        provenance.confidence = self._calculate_provenance_confidence(provenance)
        provenance.hypothesis = provenance.confidence < 0.7
        provenance.reason_code = "provenance_analysis"
        
        return provenance
    
    async def _find_orchestrators(self, entrypoint: str) -> List[str]:
        """Find orchestrator files for a capability."""
        orchestrators = set()
        
        # Add the entrypoint itself
        orchestrators.add(entrypoint)
        
        # Find files that import or are imported by the entrypoint
        for edge in self.graph.edges:
            if edge.kind == "imports":
                if edge.from_node == entrypoint:
                    orchestrators.add(edge.to_node)
                elif edge.to_node == entrypoint:
                    orchestrators.add(edge.from_node)
        
        # Find files that call or are called by the entrypoint
        for edge in self.graph.edges:
            if edge.kind == "calls":
                if edge.from_node == entrypoint:
                    orchestrators.add(edge.to_node)
                elif edge.to_node == entrypoint:
                    orchestrators.add(edge.from_node)
        
        return list(orchestrators)
    
    async def _find_data_stores(self, entrypoint: str) -> List[str]:
        """Find data stores used by a capability."""
        data_stores = set()
        
        # Find stores connected to this entrypoint
        for edge in self.graph.edges:
            if edge.kind == "stores":
                if edge.from_node == entrypoint or edge.to_node == entrypoint:
                    data_stores.add(edge.from_node if edge.from_node != entrypoint else edge.to_node)
        
        return list(data_stores)
    
    async def _find_external_services(self, entrypoint: str) -> List[str]:
        """Find external services used by a capability."""
        external_services = set()
        
        # Find externals connected to this entrypoint
        for edge in self.graph.edges:
            if edge.kind == "externals":
                if edge.from_node == entrypoint or edge.to_node == entrypoint:
                    external_services.add(edge.from_node if edge.from_node != entrypoint else edge.to_node)
        
        return list(external_services)
    
    def _determine_lane(self, entrypoint: str, provenance: ProvenanceAnalysis) -> str:
        """Determine the lane for a capability based on provenance."""
        # Check file path patterns
        for lane, config in self.lanes.items():
            for pattern in config["patterns"]:
                if pattern in entrypoint:
                    return lane
        
        # Check route patterns
        for route in provenance.entrypoints:
            if "/api/" in route:
                return "api"
            elif "/" in route and not route.startswith("/api/"):
                return "web"
        
        # Check job patterns
        if any("job" in str(ep).lower() or "task" in str(ep).lower() for ep in provenance.entrypoints):
            return "worker"
        
        # Check CLI patterns
        if any("cli" in str(ep).lower() or "script" in str(ep).lower() for ep in provenance.entrypoints):
            return "cli"
        
        # Default to web
        return "web"
    
    async def _compute_orchestrators(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[str]:
        """Compute orchestrator files for a capability."""
        orchestrators = set(provenance.orchestrators)
        
        # Add core framework files
        core_files = await self._identify_core_files()
        orchestrators.update(core_files)
        
        # Add configuration files
        config_files = await self._identify_config_files()
        orchestrators.update(config_files)
        
        return list(orchestrators)
    
    async def _identify_core_files(self) -> List[str]:
        """Identify core framework files."""
        core_files = set()
        
        # Look for main application files
        for file_path in self.static_layer.get("files", {}):
            if any(pattern in file_path.lower() for pattern in ["main.py", "app.py", "server.py", "index.js", "app.js"]):
                core_files.add(file_path)
        
        return list(core_files)
    
    async def _identify_config_files(self) -> List[str]:
        """Identify configuration files."""
        config_files = set()
        
        # Look for configuration files
        config_patterns = ["config", "settings", "env", "package.json", "requirements.txt", "pyproject.toml"]
        
        for file_path in self.static_layer.get("files", {}):
            if any(pattern in file_path.lower() for pattern in config_patterns):
                config_files.add(file_path)
        
        return list(config_files)
    
    async def _build_control_flow(self, entrypoint: str) -> List[GraphEdge]:
        """Build control flow for a capability."""
        control_flow = []
        
        # Find all edges related to this entrypoint
        for edge in self.graph.edges:
            if edge.from_node == entrypoint or edge.to_node == entrypoint:
                control_flow.append(edge)
        
        # Add suggested edges if they're relevant
        for edge in self.graph.suggested_edges:
            if edge.from_node == entrypoint or edge.to_node == entrypoint:
                control_flow.append(edge)
        
        return control_flow
    
    async def _build_data_flow(self, entrypoint: str, provenance: ProvenanceAnalysis) -> DataFlowModel:
        """Build data flow for a capability."""
        # Extract inputs (environment variables, request schemas)
        inputs = await self._extract_inputs(entrypoint, provenance)
        
        # Extract stores (database models, data stores)
        stores = await self._extract_stores(entrypoint, provenance)
        
        # Extract externals (external services, APIs)
        externals = await self._extract_externals(entrypoint, provenance)
        
        # Extract outputs (response schemas, artifacts)
        outputs = await self._extract_outputs(entrypoint, provenance)
        
        return DataFlowModel(
            inputs=inputs,
            stores=stores,
            externals=externals,
            outputs=outputs
        )
    
    async def _extract_inputs(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract input data for a capability."""
        inputs = []
        
        # Environment variables
        env_inputs = await self._extract_env_inputs(entrypoint)
        inputs.extend(env_inputs)
        
        # Request schemas
        request_schemas = await self._extract_request_schemas(entrypoint)
        inputs.extend(request_schemas)
        
        return inputs
    
    async def _extract_env_inputs(self, entrypoint: str) -> List[Dict[str, Any]]:
        """Extract environment variable inputs."""
        env_inputs = []
        
        # Look for environment variable usage
        for edge in self.graph.edges:
            if edge.kind == "externals" and "env" in edge.from_node.lower():
                env_inputs.append({
                    "name": edge.from_node,
                    "type": "environment",
                    "required": True,
                    "description": f"Environment variable: {edge.from_node}",
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "hypothesis": edge.hypothesis,
                    "reason_code": edge.reason_code
                })
        
        return env_inputs
    
    async def _extract_request_schemas(self, entrypoint: str) -> List[Dict[str, Any]]:
        """Extract request schema inputs."""
        request_schemas = []
        
        # Look for route definitions to extract request schemas
        for edge in self.graph.edges:
            if edge.kind == "routes" and edge.from_node == entrypoint:
                # Extract HTTP method and path
                method = "GET"  # Default, would be extracted from route
                path = edge.to_node
                
                request_schemas.append({
                    "name": f"{method} {path}",
                    "type": "request",
                    "schema": {
                        "method": method,
                        "path": path,
                        "contentType": "application/json"
                    },
                    "required": True,
                    "description": f"Request schema for {method} {path}",
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "hypothesis": edge.hypothesis,
                    "reason_code": edge.reason_code
                })
        
        return request_schemas
    
    async def _extract_stores(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract data stores for a capability."""
        stores = []
        
        for store_name in provenance.data_stores:
            stores.append({
                "name": store_name,
                "type": "database",
                "schema": {
                    "tables": [],
                    "relationships": []
                },
                "evidence": [EvidenceSpan(file=entrypoint, start=1, end=1)],
                "confidence": 0.8,
                "hypothesis": False,
                "reason_code": "store_detection"
            })
        
        return stores
    
    async def _extract_externals(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract external services for a capability."""
        externals = []
        
        for external_name in provenance.external_services:
            externals.append({
                "name": external_name,
                "type": "service",
                "description": f"External service: {external_name}",
                "evidence": [EvidenceSpan(file=entrypoint, start=1, end=1)],
                "confidence": 0.7,
                "hypothesis": True,
                "reason_code": "external_detection"
            })
        
        return externals
    
    async def _extract_outputs(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract output artifacts for a capability."""
        outputs = []
        
        # Look for route definitions to extract response schemas
        for edge in self.graph.edges:
            if edge.kind == "routes" and edge.from_node == entrypoint:
                method = "GET"  # Default, would be extracted from route
                path = edge.to_node
                
                outputs.append({
                    "name": f"{method} {path} Response",
                    "type": "response",
                    "schema": {
                        "statusCode": 200,
                        "contentType": "application/json"
                    },
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "hypothesis": edge.hypothesis,
                    "reason_code": edge.reason_code
                })
        
        return outputs
    
    async def _extract_policies(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract policies for a capability."""
        policies = []
        
        # Look for middleware and policies in the graph
        for edge in self.graph.edges:
            if edge.kind == "routes" and edge.from_node == entrypoint:
                # Check for middleware
                if hasattr(edge, 'middlewares') and edge.middlewares:
                    for middleware in edge.middlewares:
                        policies.append({
                            "name": f"Middleware: {middleware}",
                            "type": "middleware",
                            "description": f"Middleware applied to {edge.from_node}",
                            "evidence": edge.evidence,
                            "confidence": edge.confidence,
                            "hypothesis": edge.hypothesis,
                            "reason_code": edge.reason_code
                        })
        
        return policies
    
    async def _extract_contracts(self, entrypoint: str, provenance: ProvenanceAnalysis) -> List[Dict[str, Any]]:
        """Extract contracts for a capability."""
        contracts = []
        
        # Look for schema definitions
        for edge in self.graph.edges:
            if edge.kind == "stores" and (edge.from_node == entrypoint or edge.to_node == entrypoint):
                contracts.append({
                    "name": f"Schema: {edge.from_node if edge.from_node != entrypoint else edge.to_node}",
                    "type": "schema",
                    "description": f"Data schema for {edge.from_node if edge.from_node != entrypoint else edge.to_node}",
                    "evidence": edge.evidence,
                    "confidence": edge.confidence,
                    "hypothesis": edge.hypothesis,
                    "reason_code": edge.reason_code
                })
        
        return contracts
    
    def _generate_capability_id(self, entrypoint: str, lane: str) -> str:
        """Generate a unique capability ID."""
        # Create a deterministic ID based on entrypoint and lane
        id_data = f"{entrypoint}:{lane}"
        return hashlib.sha256(id_data.encode()).hexdigest()[:16]
    
    def _generate_capability_name(self, entrypoint: str, lane: str) -> str:
        """Generate a human-readable capability name."""
        # Extract meaningful name from entrypoint
        file_name = Path(entrypoint).stem
        lane_title = lane.title()
        
        return f"{lane_title} - {file_name}"
    
    def _generate_capability_purpose(self, entrypoint: str, lane: str, data_flow: DataFlowModel) -> str:
        """Generate a capability purpose description."""
        lane_descriptions = {
            "web": "Web interface and user interaction",
            "api": "API service and data access",
            "worker": "Background processing and job execution",
            "scheduler": "Scheduled task execution",
            "cli": "Command-line interface and scripting"
        }
        
        base_purpose = lane_descriptions.get(lane, "Application capability")
        
        # Add data flow context
        if data_flow.inputs:
            base_purpose += f" with {len(data_flow.inputs)} input sources"
        if data_flow.stores:
            base_purpose += f" using {len(data_flow.stores)} data stores"
        if data_flow.externals:
            base_purpose += f" integrating {len(data_flow.externals)} external services"
        
        return base_purpose
    
    def _collect_capability_evidence(self, entrypoint: str, provenance: ProvenanceAnalysis, control_flow: List[GraphEdge], data_flow: DataFlowModel) -> List[EvidenceSpan]:
        """Collect all evidence for a capability."""
        evidence = []
        
        # Add provenance evidence
        evidence.extend(provenance.evidence)
        
        # Add control flow evidence
        for edge in control_flow:
            evidence.extend(edge.evidence)
        
        # Add data flow evidence
        for input_item in data_flow.inputs:
            evidence.extend(input_item.get("evidence", []))
        for store in data_flow.stores:
            evidence.extend(store.get("evidence", []))
        for external in data_flow.externals:
            evidence.extend(external.get("evidence", []))
        for output in data_flow.outputs:
            evidence.extend(output.get("evidence", []))
        
        # Deduplicate evidence
        evidence_set = set()
        unique_evidence = []
        for span in evidence:
            span_key = (span.file, span.start, span.end)
            if span_key not in evidence_set:
                evidence_set.add(span_key)
                unique_evidence.append(span)
        
        return unique_evidence
    
    def _identify_suggested_edges(self, entrypoint: str, control_flow: List[GraphEdge], data_flow: DataFlowModel) -> List[GraphEdge]:
        """Identify suggested edges for a capability."""
        suggested_edges = []
        
        # Add low-confidence edges from control flow
        for edge in control_flow:
            if edge.hypothesis or edge.confidence < 0.5:
                suggested_edges.append(edge)
        
        return suggested_edges
    
    def _calculate_provenance_confidence(self, provenance: ProvenanceAnalysis) -> float:
        """Calculate confidence score for provenance analysis."""
        confidence_factors = []
        
        # Factor in number of entrypoints
        if provenance.entrypoints:
            confidence_factors.append(0.9)
        else:
            confidence_factors.append(0.3)
        
        # Factor in number of orchestrators
        if len(provenance.orchestrators) > 1:
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.5)
        
        # Factor in evidence quality
        if len(provenance.evidence) > 0:
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.2)
        
        return sum(confidence_factors) / len(confidence_factors)
    
    async def _compute_centrality_metrics(self) -> None:
        """Compute centrality metrics for all capabilities."""
        logger.info("Computing centrality metrics")
        
        for capability in self.capabilities:
            try:
                metrics = await self._compute_capability_centrality(capability)
                self.centrality_metrics[capability.id] = metrics
            except Exception as e:
                logger.error(f"Failed to compute centrality for {capability.id}: {e}")
                continue
    
    async def _compute_capability_centrality(self, capability: CapabilityModel) -> CentralityMetrics:
        """Compute centrality metrics for a single capability."""
        # Simplified centrality calculation
        # In a real implementation, this would use network analysis libraries
        
        # Degree centrality (number of connections)
        degree_centrality = len(capability.control_flow) / max(len(self.graph.edges), 1)
        
        # Betweenness centrality (simplified)
        betweenness_centrality = degree_centrality * 0.5
        
        # Closeness centrality (simplified)
        closeness_centrality = degree_centrality * 0.7
        
        # Eigenvector centrality (simplified)
        eigenvector_centrality = degree_centrality * 0.6
        
        return CentralityMetrics(
            betweenness_centrality=betweenness_centrality,
            closeness_centrality=closeness_centrality,
            degree_centrality=degree_centrality,
            eigenvector_centrality=eigenvector_centrality,
            evidence=capability.evidence,
            confidence=0.8,
            hypothesis=False
        )
    
    def _rank_capabilities(self) -> None:
        """Rank capabilities by importance using centrality metrics."""
        # Sort capabilities by combined centrality score
        for capability in self.capabilities:
            metrics = self.centrality_metrics.get(capability.id)
            if metrics:
                # Calculate combined score
                combined_score = (
                    metrics.degree_centrality * 0.3 +
                    metrics.betweenness_centrality * 0.3 +
                    metrics.closeness_centrality * 0.2 +
                    metrics.eigenvector_centrality * 0.2
                )
                capability.ranking_score = combined_score
        
        # Sort by ranking score
        self.capabilities.sort(key=lambda c: getattr(c, 'ranking_score', 0), reverse=True)
        
        # Assign ranks
        for i, capability in enumerate(self.capabilities):
            capability.rank = i + 1
