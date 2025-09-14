"""
Graph builder that merges static and LLM layers with hypothesis quarantine.
Builds import, route, job, and call graphs with evidence tracking.
"""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from .config import settings
from .models import (
    GraphModel, GraphEdge, EvidenceSpan, ImportModel, 
    RouteModel, FileNodeModel, WarningItem
)
from .observability import record_detector_hit, record_fallback
from .import_resolver import ImportResolver

logger = logging.getLogger(__name__)

@dataclass
class StaticLayer:
    """Static analysis layer results."""
    imports: Dict[str, List[ImportModel]] = field(default_factory=dict)
    routes: Dict[str, List[RouteModel]] = field(default_factory=dict)
    jobs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    stores: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    externals: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    files: Dict[str, FileNodeModel] = field(default_factory=dict)
    confidence_threshold: float = 0.7

@dataclass
class LLMLayer:
    """LLM completion layer results."""
    route_completions: Dict[str, List[RouteModel]] = field(default_factory=dict)
    job_completions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    call_completions: Dict[str, List[GraphEdge]] = field(default_factory=dict)
    schema_completions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    confidence_threshold: float = 0.5

class GraphBuilder:
    """Builds comprehensive graphs from static and LLM analysis."""
    
    def __init__(self, repo_root: Path, preflight_data: Dict[str, Any]):
        self.repo_root = repo_root
        self.preflight_data = preflight_data
        self.import_resolver = ImportResolver(repo_root, preflight_data)
        
        # Graph storage
        self.import_graph: Dict[str, Set[str]] = defaultdict(set)
        self.route_graph: Dict[str, Set[str]] = defaultdict(set)
        self.job_graph: Dict[str, Set[str]] = defaultdict(set)
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.store_graph: Dict[str, Set[str]] = defaultdict(set)
        self.external_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Evidence tracking
        self.edge_evidence: Dict[Tuple[str, str, str], List[EvidenceSpan]] = {}
        self.edge_confidence: Dict[Tuple[str, str, str], float] = {}
        self.edge_hypothesis: Dict[Tuple[str, str, str], bool] = {}
        self.edge_reason_code: Dict[Tuple[str, str, str], Optional[str]] = {}
        
        # Metrics
        self.static_edges = 0
        self.llm_edges = 0
        self.hypothesis_edges = 0
        self.quarantined_edges = 0
    
    def build_graphs(self, static_layer: StaticLayer, llm_layer: Optional[LLMLayer] = None) -> GraphModel:
        """Build comprehensive graphs from static and LLM layers."""
        logger.info("Building graphs from static and LLM layers")
        
        # Build static graphs
        self._build_static_graphs(static_layer)
        
        # Merge LLM layer if provided
        if llm_layer:
            self._merge_llm_layer(llm_layer)
        
        # Quarantine low-confidence hypotheses
        self._quarantine_hypotheses()
        
        # Build final graph structure
        graph = self._build_final_graph()
        
        logger.info(f"Graph building complete: {self.static_edges} static, {self.llm_edges} LLM, {self.hypothesis_edges} hypothesis, {self.quarantined_edges} quarantined")
        
        return graph
    
    def _build_static_graphs(self, static_layer: StaticLayer) -> None:
        """Build graphs from static analysis."""
        logger.info("Building static graphs")
        
        # Build import graph
        self._build_import_graph(static_layer.imports)
        
        # Build route graph
        self._build_route_graph(static_layer.routes)
        
        # Build job graph
        self._build_job_graph(static_layer.jobs)
        
        # Build store graph
        self._build_store_graph(static_layer.stores)
        
        # Build external graph
        self._build_external_graph(static_layer.externals)
        
        # Build call graph from file relationships
        self._build_call_graph_from_files(static_layer.files)
    
    def _build_import_graph(self, imports: Dict[str, List[ImportModel]]) -> None:
        """Build import dependency graph."""
        for file_path, import_list in imports.items():
            for imp in import_list:
                if not imp.external and imp.resolved:
                    # Add edge from importing file to imported file
                    edge_key = (file_path, imp.resolved, "imports")
                    
                    self.import_graph[file_path].add(imp.resolved)
                    self.edge_evidence[edge_key] = imp.evidence
                    self.edge_confidence[edge_key] = imp.confidence
                    self.edge_hypothesis[edge_key] = imp.hypothesis
                    self.edge_reason_code[edge_key] = imp.reason_code
                    
                    self.static_edges += 1
    
    def _build_route_graph(self, routes: Dict[str, List[RouteModel]]) -> None:
        """Build route relationship graph."""
        for file_path, route_list in routes.items():
            for route in route_list:
                # Connect route to its file
                route_id = f"{route.method}:{route.path}"
                edge_key = (route_id, file_path, "routes")
                
                self.route_graph[route_id].add(file_path)
                self.edge_evidence[edge_key] = route.evidence
                self.edge_confidence[edge_key] = route.confidence
                self.edge_hypothesis[edge_key] = route.hypothesis
                self.edge_reason_code[edge_key] = route.reason_code
                
                self.static_edges += 1
                
                # Connect route to middlewares
                for middleware in route.middlewares:
                    middleware_edge_key = (route_id, middleware, "middleware")
                    self.route_graph[route_id].add(middleware)
                    self.edge_evidence[middleware_edge_key] = route.evidence
                    self.edge_confidence[middleware_edge_key] = route.confidence * 0.8
                    self.edge_hypothesis[middleware_edge_key] = route.hypothesis
                    self.edge_reason_code[middleware_edge_key] = route.reason_code
                    
                    self.static_edges += 1
    
    def _build_job_graph(self, jobs: Dict[str, List[Dict[str, Any]]]) -> None:
        """Build job relationship graph."""
        for file_path, job_list in jobs.items():
            for job in job_list:
                job_name = job.get("name", "unknown")
                job_type = job.get("type", "unknown")
                
                # Connect job to its file
                edge_key = (job_name, file_path, "jobs")
                
                self.job_graph[job_name].add(file_path)
                self.edge_evidence[edge_key] = job.get("evidence", [])
                self.edge_confidence[edge_key] = job.get("confidence", 0.5)
                self.edge_hypothesis[edge_key] = job.get("hypothesis", False)
                self.edge_reason_code[edge_key] = job.get("reason_code")
                
                self.static_edges += 1
                
                # Connect producer and consumer
                producer = job.get("producer")
                consumer = job.get("consumer")
                
                if producer and producer != "unknown":
                    producer_edge_key = (job_name, producer, "producer")
                    self.job_graph[job_name].add(producer)
                    self.edge_evidence[producer_edge_key] = job.get("evidence", [])
                    self.edge_confidence[producer_edge_key] = job.get("confidence", 0.5) * 0.8
                    self.edge_hypothesis[producer_edge_key] = job.get("hypothesis", False)
                    self.edge_reason_code[producer_edge_key] = job.get("reason_code")
                    
                    self.static_edges += 1
                
                if consumer and consumer != "unknown":
                    consumer_edge_key = (job_name, consumer, "consumer")
                    self.job_graph[job_name].add(consumer)
                    self.edge_evidence[consumer_edge_key] = job.get("evidence", [])
                    self.edge_confidence[consumer_edge_key] = job.get("confidence", 0.5) * 0.8
                    self.edge_hypothesis[consumer_edge_key] = job.get("hypothesis", False)
                    self.edge_reason_code[consumer_edge_key] = job.get("reason_code")
                    
                    self.static_edges += 1
    
    def _build_store_graph(self, stores: Dict[str, List[Dict[str, Any]]]) -> None:
        """Build data store relationship graph."""
        for file_path, store_list in stores.items():
            for store in store_list:
                store_name = store.get("name", "unknown")
                store_type = store.get("type", "unknown")
                
                # Connect store to its file
                edge_key = (store_name, file_path, "stores")
                
                self.store_graph[store_name].add(file_path)
                self.edge_evidence[edge_key] = store.get("evidence", [])
                self.edge_confidence[edge_key] = store.get("confidence", 0.5)
                self.edge_hypothesis[edge_key] = store.get("hypothesis", False)
                self.edge_reason_code[edge_key] = store.get("reason_code")
                
                self.static_edges += 1
    
    def _build_external_graph(self, externals: Dict[str, List[Dict[str, Any]]]) -> None:
        """Build external service relationship graph."""
        for file_path, external_list in externals.items():
            for external in external_list:
                external_name = external.get("name", "unknown")
                external_type = external.get("type", "unknown")
                
                # Connect external to its file
                edge_key = (external_name, file_path, "externals")
                
                self.external_graph[external_name].add(file_path)
                self.edge_evidence[edge_key] = external.get("evidence", [])
                self.edge_confidence[edge_key] = external.get("confidence", 0.5)
                self.edge_hypothesis[edge_key] = external.get("hypothesis", False)
                self.edge_reason_code[edge_key] = external.get("reason_code")
                
                self.static_edges += 1
    
    def _build_call_graph_from_files(self, files: Dict[str, FileNodeModel]) -> None:
        """Build call graph from file relationships."""
        for file_path, file_node in files.items():
            # Connect file to its functions
            for func in file_node.functions:
                func_name = func.get("name", "unknown")
                edge_key = (file_path, func_name, "calls")
                
                self.call_graph[file_path].add(func_name)
                self.edge_evidence[edge_key] = func.get("evidence", [])
                self.edge_confidence[edge_key] = func.get("confidence", 0.8)
                self.edge_hypothesis[edge_key] = func.get("hypothesis", False)
                self.edge_reason_code[edge_key] = func.get("reason_code")
                
                self.static_edges += 1
            
            # Connect file to its classes
            for cls in file_node.classes:
                cls_name = cls.get("name", "unknown")
                edge_key = (file_path, cls_name, "classes")
                
                self.call_graph[file_path].add(cls_name)
                self.edge_evidence[edge_key] = cls.get("evidence", [])
                self.edge_confidence[edge_key] = cls.get("confidence", 0.8)
                self.edge_hypothesis[edge_key] = cls.get("hypothesis", False)
                self.edge_reason_code[edge_key] = cls.get("reason_code")
                
                self.static_edges += 1
    
    def _merge_llm_layer(self, llm_layer: LLMLayer) -> None:
        """Merge LLM completion layer results."""
        logger.info("Merging LLM layer")
        
        # Merge route completions
        self._merge_route_completions(llm_layer.route_completions)
        
        # Merge job completions
        self._merge_job_completions(llm_layer.job_completions)
        
        # Merge call completions
        self._merge_call_completions(llm_layer.call_completions)
        
        # Merge schema completions
        self._merge_schema_completions(llm_layer.schema_completions)
    
    def _merge_route_completions(self, route_completions: Dict[str, List[RouteModel]]) -> None:
        """Merge LLM route completions."""
        for file_path, routes in route_completions.items():
            for route in routes:
                route_id = f"{route.method}:{route.path}"
                edge_key = (route_id, file_path, "routes_llm")
                
                # Only add if not already present or if LLM has higher confidence
                existing_confidence = self.edge_confidence.get((route_id, file_path, "routes"), 0.0)
                
                if route.confidence > existing_confidence:
                    self.route_graph[route_id].add(file_path)
                    self.edge_evidence[edge_key] = route.evidence
                    self.edge_confidence[edge_key] = route.confidence
                    self.edge_hypothesis[edge_key] = route.hypothesis
                    self.edge_reason_code[edge_key] = route.reason_code
                    
                    self.llm_edges += 1
                    
                    # Update hypothesis count
                    if route.hypothesis:
                        self.hypothesis_edges += 1
    
    def _merge_job_completions(self, job_completions: Dict[str, List[Dict[str, Any]]]) -> None:
        """Merge LLM job completions."""
        for file_path, jobs in job_completions.items():
            for job in jobs:
                job_name = job.get("name", "unknown")
                edge_key = (job_name, file_path, "jobs_llm")
                
                # Only add if not already present or if LLM has higher confidence
                existing_confidence = self.edge_confidence.get((job_name, file_path, "jobs"), 0.0)
                
                if job.get("confidence", 0.0) > existing_confidence:
                    self.job_graph[job_name].add(file_path)
                    self.edge_evidence[edge_key] = job.get("evidence", [])
                    self.edge_confidence[edge_key] = job.get("confidence", 0.5)
                    self.edge_hypothesis[edge_key] = job.get("hypothesis", False)
                    self.edge_reason_code[edge_key] = job.get("reason_code")
                    
                    self.llm_edges += 1
                    
                    # Update hypothesis count
                    if job.get("hypothesis", False):
                        self.hypothesis_edges += 1
    
    def _merge_call_completions(self, call_completions: Dict[str, List[GraphEdge]]) -> None:
        """Merge LLM call completions."""
        for file_path, edges in call_completions.items():
            for edge in edges:
                edge_key = (edge.from_node, edge.to_node, "calls_llm")
                
                # Only add if not already present or if LLM has higher confidence
                existing_confidence = self.edge_confidence.get((edge.from_node, edge.to_node, "calls"), 0.0)
                
                if edge.confidence > existing_confidence:
                    self.call_graph[edge.from_node].add(edge.to_node)
                    self.edge_evidence[edge_key] = edge.evidence
                    self.edge_confidence[edge_key] = edge.confidence
                    self.edge_hypothesis[edge_key] = edge.hypothesis
                    self.edge_reason_code[edge_key] = edge.reason_code
                    
                    self.llm_edges += 1
                    
                    # Update hypothesis count
                    if edge.hypothesis:
                        self.hypothesis_edges += 1
    
    def _merge_schema_completions(self, schema_completions: Dict[str, Dict[str, Any]]) -> None:
        """Merge LLM schema completions."""
        # Schema completions are used to enhance existing edges with type information
        # This is a placeholder for future schema completion logic
        pass
    
    def _quarantine_hypotheses(self) -> None:
        """Quarantine low-confidence hypothesis edges."""
        logger.info("Quarantining low-confidence hypotheses")
        
        quarantine_threshold = 0.3
        
        for edge_key, is_hypothesis in self.edge_hypothesis.items():
            if is_hypothesis:
                confidence = self.edge_confidence.get(edge_key, 0.0)
                if confidence < quarantine_threshold:
                    # Move to quarantined
                    self.quarantined_edges += 1
                    
                    # Record fallback
                    reason_code = self.edge_reason_code.get(edge_key, "unknown")
                    record_fallback(reason_code)
                    
                    logger.debug(f"Quarantined low-confidence hypothesis: {edge_key} (confidence: {confidence})")
    
    def _build_final_graph(self) -> GraphModel:
        """Build final graph structure."""
        edges = []
        suggested_edges = []
        
        # Convert all graphs to edges
        for from_node, to_nodes in self.import_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "imports")
                edge = self._create_edge(from_node, to_node, "imports", edge_key)
                if edge:
                    edges.append(edge)
        
        for from_node, to_nodes in self.route_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "routes")
                edge = self._create_edge(from_node, to_node, "routes", edge_key)
                if edge:
                    edges.append(edge)
        
        for from_node, to_nodes in self.job_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "jobs")
                edge = self._create_edge(from_node, to_node, "jobs", edge_key)
                if edge:
                    edges.append(edge)
        
        for from_node, to_nodes in self.call_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "calls")
                edge = self._create_edge(from_node, to_node, "calls", edge_key)
                if edge:
                    edges.append(edge)
        
        for from_node, to_nodes in self.store_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "stores")
                edge = self._create_edge(from_node, to_node, "stores", edge_key)
                if edge:
                    edges.append(edge)
        
        for from_node, to_nodes in self.external_graph.items():
            for to_node in to_nodes:
                edge_key = (from_node, to_node, "externals")
                edge = self._create_edge(from_node, to_node, "externals", edge_key)
                if edge:
                    edges.append(edge)
        
        # Separate high-confidence edges from suggestions
        for edge in edges:
            if edge.hypothesis or edge.confidence < 0.5:
                suggested_edges.append(edge)
        
        # Remove suggested edges from main edges
        main_edges = [edge for edge in edges if not (edge.hypothesis or edge.confidence < 0.5)]
        
        # Create metadata
        metadata = {
            "total_edges": len(edges),
            "main_edges": len(main_edges),
            "suggested_edges": len(suggested_edges),
            "static_edges": self.static_edges,
            "llm_edges": self.llm_edges,
            "hypothesis_edges": self.hypothesis_edges,
            "quarantined_edges": self.quarantined_edges,
            "unresolved_import_ratio": self._calculate_unresolved_import_ratio(),
            "hypothesis_edge_ratio": self.hypothesis_edges / max(len(edges), 1)
        }
        
        return GraphModel(
            edges=main_edges,
            suggested_edges=suggested_edges,
            metadata=metadata
        )
    
    def _create_edge(self, from_node: str, to_node: str, kind: str, edge_key: Tuple[str, str, str]) -> Optional[GraphEdge]:
        """Create a GraphEdge from stored data."""
        evidence = self.edge_evidence.get(edge_key, [])
        confidence = self.edge_confidence.get(edge_key, 0.5)
        hypothesis = self.edge_hypothesis.get(edge_key, False)
        reason_code = self.edge_reason_code.get(edge_key)
        
        # Skip quarantined edges
        if hypothesis and confidence < 0.3:
            return None
        
        return GraphEdge(
            src=from_node,
            dst=to_node,
            kind=kind,
            evidence=evidence,
            confidence=confidence,
            hypothesis=hypothesis,
            reason_code=reason_code
        )
    
    def _calculate_unresolved_import_ratio(self) -> float:
        """Calculate ratio of unresolved imports."""
        total_imports = 0
        unresolved_imports = 0
        
        # This would need access to the original import data
        # For now, return a placeholder
        return 0.0
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get comprehensive graph statistics."""
        return {
            "import_graph_size": len(self.import_graph),
            "route_graph_size": len(self.route_graph),
            "job_graph_size": len(self.job_graph),
            "call_graph_size": len(self.call_graph),
            "store_graph_size": len(self.store_graph),
            "external_graph_size": len(self.external_graph),
            "total_static_edges": self.static_edges,
            "total_llm_edges": self.llm_edges,
            "total_hypothesis_edges": self.hypothesis_edges,
            "total_quarantined_edges": self.quarantined_edges,
            "edge_evidence_count": len(self.edge_evidence),
            "edge_confidence_count": len(self.edge_confidence),
            "edge_hypothesis_count": len(self.edge_hypothesis)
        }
