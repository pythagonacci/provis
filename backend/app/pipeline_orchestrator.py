"""
Pipeline orchestrator with rate limits, observability, and real-time events/status.
Manages the complete analysis pipeline from ingest to finalize.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import logging

from .config import settings
from .models import Phase, StatusPayload, WarningItem, EvidenceSpan
from .observability import get_metrics_collector, record_fallback
from .events import get_event_stream
from .preflight import run_preflight_scan
from .language_services import get_ts_program_service, get_python_cst_service
from .detectors import DetectorRegistry
from .python_detectors import PythonDetectorRegistry
from .graph_builder import GraphBuilder, StaticLayer, LLMLayer
from .capabilities_v2 import CapabilityAnalyzer, CapabilityContext
from .llm_client import LLMClient
from .llm_graph_completion import LLMGraphCompleter
from .storage import ArtifactStorage
from .models import GraphModel, CapabilityModel, ArtifactMetadata

logger = logging.getLogger(__name__)

class PipelinePhase(Enum):
    """Pipeline phases with ordering."""
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    DISCOVERING = "discovering"
    PARSING = "parsing"
    MERGING = "merging"
    MAPPING = "mapping"
    SUMMARIZING = "summarizing"
    FINALIZING = "finalizing"
    DONE = "done"
    FAILED = "failed"

@dataclass
class PipelineTask:
    """Individual pipeline task with rate limiting and observability."""
    task_id: str
    phase: PipelinePhase
    repo_id: str
    repo_path: Path
    job_id: str
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    dependencies: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RateLimiter:
    """Rate limiter for different resource types."""
    max_concurrent: int
    current_usage: int = 0
    queue: List[PipelineTask] = field(default_factory=list)
    semaphore: Optional[asyncio.Semaphore] = None
    
    def __post_init__(self):
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

class PipelineOrchestrator:
    """Main pipeline orchestrator with comprehensive management."""
    
    def __init__(self):
        self.tasks: Dict[str, PipelineTask] = {}
        self.task_dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.completed_tasks: Set[str] = set()
        self.failed_tasks: Set[str] = set()
        
        # Rate limiters
        self.node_parse_limiter = RateLimiter(max_concurrent=settings.NODE_PARSE_CONCURRENCY)
        self.llm_limiter = RateLimiter(max_concurrent=settings.LLM_CONCURRENCY)
        
        # Pipeline state
        self.active_jobs: Dict[str, Dict[str, Any]] = {}
        self.job_phases: Dict[str, PipelinePhase] = {}
        self.job_progress: Dict[str, Dict[str, Any]] = {}
        
        # Metrics and observability
        self.metrics_collector = get_metrics_collector()
        self.phase_start_times: Dict[str, Dict[PipelinePhase, float]] = {}
        self.phase_durations: Dict[str, Dict[PipelinePhase, float]] = {}
        
        # Services
        self.llm_client = LLMClient()
        self.detector_registry = DetectorRegistry()
        self.python_detector_registry = PythonDetectorRegistry()
        self.storage = ArtifactStorage()
        
        # Shutdown handling
        self.shutdown_requested = False
        self.background_tasks: Set[asyncio.Task] = set()
    
    async def start(self) -> None:
        """Start the pipeline orchestrator."""
        logger.info("Starting pipeline orchestrator")
        
        # Start background tasks
        self.background_tasks.add(asyncio.create_task(self._task_processor()))
        self.background_tasks.add(asyncio.create_task(self._metrics_collector()))
        self.background_tasks.add(asyncio.create_task(self._cleanup_old_jobs()))
        
        logger.info("Pipeline orchestrator started")
    
    async def stop(self) -> None:
        """Stop the pipeline orchestrator gracefully."""
        logger.info("Stopping pipeline orchestrator")
        
        self.shutdown_requested = True
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Pipeline orchestrator stopped")
    
    async def ingest_repository(self, repo_id: str, repo_path: Path) -> str:
        """Ingest a repository and start analysis pipeline."""
        job_id = f"job_{repo_id}_{int(time.time())}"
        
        logger.info(f"Starting repository ingestion: {repo_id} (job: {job_id})")
        
        # Initialize job state
        self.active_jobs[job_id] = {
            "repo_id": repo_id,
            "repo_path": repo_path,
            "created_at": time.time(),
            "status": "queued"
        }
        self.job_phases[job_id] = PipelinePhase.QUEUED
        self.job_progress[job_id] = {
            "current_phase": "queued",
            "progress_percent": 0,
            "tasks_completed": 0,
            "total_tasks": 0,
            "warnings": [],
            "metrics": {}
        }
        
        # Create pipeline tasks
        await self._create_pipeline_tasks(job_id, repo_id, repo_path)
        
        # Publish initial event
        event_stream = get_event_stream()
        await event_stream.emit_event(job_id, "job_started", {
            "job_id": job_id,
            "repo_id": repo_id,
            "phase": "queued"
        })
        
        return job_id
    
    async def _create_pipeline_tasks(self, job_id: str, repo_id: str, repo_path: Path) -> None:
        """Create all pipeline tasks for a job."""
        tasks = [
            ("preflight", PipelinePhase.DISCOVERING, self._run_preflight_task),
            ("parse_batch", PipelinePhase.PARSING, self._run_parse_batch_task),
            ("merge", PipelinePhase.MERGING, self._run_merge_task),
            ("map", PipelinePhase.MAPPING, self._run_map_task),
            ("summarize", PipelinePhase.SUMMARIZING, self._run_summarize_task),
            ("finalize", PipelinePhase.FINALIZING, self._run_finalize_task),
        ]
        
        for task_id, phase, task_func in tasks:
            task = PipelineTask(
                task_id=f"{job_id}_{task_id}",
                phase=phase,
                repo_id=repo_id,
                repo_path=repo_path,
                job_id=job_id,
                created_at=time.time(),
                max_retries=3
            )
            
            self.tasks[task.task_id] = task
            
            # Set up dependencies
            if task_id == "parse_batch":
                self.task_dependencies[task.task_id].add(f"{job_id}_preflight")
            elif task_id == "merge":
                self.task_dependencies[task.task_id].add(f"{job_id}_parse_batch")
            elif task_id == "map":
                self.task_dependencies[task.task_id].add(f"{job_id}_merge")
            elif task_id == "summarize":
                self.task_dependencies[task.task_id].add(f"{job_id}_map")
            elif task_id == "finalize":
                self.task_dependencies[task.task_id].add(f"{job_id}_summarize")
        
        # Update total tasks
        self.job_progress[job_id]["total_tasks"] = len(tasks)
    
    async def _run_preflight_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run preflight scan task."""
        logger.info(f"Running preflight scan for {task.repo_id}")
        
        try:
            preflight_data = await run_preflight_scan(task.repo_path, task.repo_id)
            
            # Store preflight data
            preflight_path = task.repo_path / "preflight.json"
            preflight_path.write_text(json.dumps(preflight_data, indent=2))
            
            return {
                "preflight_data": preflight_data,
                "artifacts": ["preflight.json"]
            }
            
        except Exception as e:
            logger.error(f"Preflight scan failed for {task.repo_id}: {e}")
            raise
    
    async def _run_parse_batch_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run parsing batch task with rate limiting."""
        logger.info(f"Running parse batch for {task.repo_id}")
        
        async with self.node_parse_limiter.semaphore:
            try:
                # Get preflight data
                preflight_path = task.repo_path / "preflight.json"
                if not preflight_path.exists():
                    raise FileNotFoundError("Preflight data not found")
                
                preflight_data = json.loads(preflight_path.read_text())
                
                # Parse files in batches
                parsed_files = await self._parse_files_batch(task.repo_path, preflight_data)
                
                # Store parsed data
                parsed_path = task.repo_path / "parsed.json"
                parsed_path.write_text(json.dumps(parsed_files, indent=2))
                
                return {
                    "parsed_files": parsed_files,
                    "artifacts": ["parsed.json"]
                }
                
            except Exception as e:
                logger.error(f"Parse batch failed for {task.repo_id}: {e}")
                raise
    
    async def _parse_files_batch(self, repo_path: Path, preflight_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse files in batches with rate limiting."""
        parsed_files = {}
        
        # Get all source files
        source_files = []
        for file_info in preflight_data.get("files", []):
            if file_info.get("type") == "source":
                source_files.append(file_info["path"])
        
        # Parse in batches
        batch_size = settings.PARSE_BATCH_SIZE
        for i in range(0, len(source_files), batch_size):
            batch = source_files[i:i + batch_size]
            
            # Parse batch with timeout
            try:
                batch_results = await asyncio.wait_for(
                    self._parse_file_batch(repo_path, batch),
                    timeout=settings.PARSE_PER_FILE_TIMEOUT * len(batch)
                )
                parsed_files.update(batch_results)
                
            except asyncio.TimeoutError:
                logger.warning(f"Batch parsing timeout for {len(batch)} files")
                record_fallback("timeout", f"batch_{i}")
                
                # Continue with next batch
                continue
        
        return parsed_files
    
    async def _parse_file_batch(self, repo_path: Path, file_paths: List[str]) -> Dict[str, Any]:
        """Parse a batch of files."""
        batch_results = {}
        
        # Create tasks for parallel parsing
        parse_tasks = []
        for file_path in file_paths:
            task = asyncio.create_task(self._parse_single_file(repo_path, file_path))
            parse_tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*parse_tasks, return_exceptions=True)
        
        # Process results
        for file_path, result in zip(file_paths, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to parse {file_path}: {result}")
                record_fallback("parse_error", file_path)
                continue
            
            batch_results[file_path] = result
        
        return batch_results
    
    async def _parse_single_file(self, repo_path: Path, file_path: str) -> Dict[str, Any]:
        """Parse a single file."""
        full_path = repo_path / "snapshot" / file_path
        
        if not full_path.exists():
            return {}
        
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            
            # Determine file type and parse accordingly
            if file_path.endswith(('.py', '.pyx')):
                return await self._parse_python_file(file_path, content)
            elif file_path.endswith(('.js', '.jsx', '.ts', '.tsx')):
                return await self._parse_js_ts_file(repo_path, file_path, content)
            else:
                return {}
                
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            record_fallback("file_read_error", file_path)
            return {}
    
    async def _parse_python_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Parse a Python file."""
        try:
            # Use Python detectors
            detectors = self.python_detector_registry.detect_all(Path(file_path), content)
            
            # Use Python CST service if available
            cst_service = get_python_cst_service()
            if cst_service.available:
                cst_result = cst_service.parse_file(Path(file_path), content)
            else:
                cst_result = {}
            
            return {
                "language": "python",
                "detectors": {name: result.model_dump() for name, result in detectors.items()},
                "cst_result": cst_result,
                "content": content
            }
            
        except Exception as e:
            logger.warning(f"Python parsing failed for {file_path}: {e}")
            record_fallback("python_parse_error", file_path)
            return {}
    
    async def _parse_js_ts_file(self, repo_path: Path, file_path: str, content: str) -> Dict[str, Any]:
        """Parse a JavaScript/TypeScript file."""
        try:
            # Use JS/TS detectors
            detectors = self.detector_registry.detect_all(Path(file_path), content)
            
            # Use TypeScript program service if available
            ts_service = await get_ts_program_service(repo_path)
            if ts_service:
                ts_result = await ts_service.parse_file(Path(file_path))
            else:
                ts_result = {}
            
            return {
                "language": "typescript" if file_path.endswith(('.ts', '.tsx')) else "javascript",
                "detectors": {name: result.model_dump() for name, result in detectors.items()},
                "ts_result": ts_result,
                "content": content
            }
            
        except Exception as e:
            logger.warning(f"JS/TS parsing failed for {file_path}: {e}")
            record_fallback("js_ts_parse_error", file_path)
            return {}
    
    async def _run_merge_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run merge task to combine static analysis results."""
        logger.info(f"Running merge task for {task.repo_id}")
        
        try:
            # Get parsed data
            parsed_path = task.repo_path / "parsed.json"
            if not parsed_path.exists():
                raise FileNotFoundError("Parsed data not found")
            
            parsed_data = json.loads(parsed_path.read_text())
            
            # Merge static analysis results
            merged_data = await self._merge_static_analysis(parsed_data)
            
            # Store merged data
            merged_path = task.repo_path / "merged.json"
            merged_path.write_text(json.dumps(merged_data, indent=2))
            
            return {
                "merged_data": merged_data,
                "artifacts": ["merged.json"]
            }
            
        except Exception as e:
            logger.error(f"Merge task failed for {task.repo_id}: {e}")
            raise
    
    async def _merge_static_analysis(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge static analysis results from all files."""
        merged = {
            "imports": {},
            "routes": {},
            "jobs": {},
            "stores": {},
            "externals": {},
            "files": {},
            "summary": {
                "total_files": len(parsed_data),
                "languages": defaultdict(int),
                "frameworks": defaultdict(int),
                "detectors": defaultdict(int)
            }
        }
        
        for file_path, file_data in parsed_data.items():
            # Merge file data
            merged["files"][file_path] = file_data
            
            # Update summary
            merged["summary"]["languages"][file_data.get("language", "unknown")] += 1
            
            # Merge detector results
            for detector_name, detector_result in file_data.get("detectors", {}).items():
                merged["summary"]["detectors"][detector_name] += 1
                
                # Merge specific detector results
                if detector_name in ["nextjs", "express", "react_router", "fastapi", "flask", "django"]:
                    # Route detectors
                    if "routes" in detector_result:
                        merged["routes"][file_path] = detector_result["routes"]
                
                elif detector_name in ["queue", "celery"]:
                    # Job detectors
                    if "jobs" in detector_result:
                        merged["jobs"][file_path] = detector_result["jobs"]
                
                elif detector_name in ["store", "python_store"]:
                    # Store detectors
                    if "stores" in detector_result:
                        merged["stores"][file_path] = detector_result["stores"]
                
                elif detector_name == "external":
                    # External detectors
                    if "externals" in detector_result:
                        merged["externals"][file_path] = detector_result["externals"]
        
        return merged
    
    async def _run_map_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run mapping task to build graphs and capabilities."""
        logger.info(f"Running map task for {task.repo_id}")
        
        try:
            # Get merged data
            merged_path = task.repo_path / "merged.json"
            if not merged_path.exists():
                raise FileNotFoundError("Merged data not found")
            
            merged_data = json.loads(merged_path.read_text())
            
            # Build graphs using GraphBuilder
            graph_builder = GraphBuilder()
            static_layer = StaticLayer(merged_data)
            llm_layer = LLMLayer(self.llm_client, merged_data)
            
            graph_model = await graph_builder.build_graph(static_layer, llm_layer)
            
            # Build capabilities using CapabilityAnalyzer
            capability_analyzer = CapabilityAnalyzer()
            capability_context = CapabilityContext(graph_model, merged_data)
            
            capabilities = await capability_analyzer.analyze_capabilities(capability_context)
            
            # Store artifacts using storage system
            repo_id = task.repo_id
            snapshot_id = task.metadata.get("snapshot_id", "unknown")
            
            # Write graph artifact
            graph_artifact_id = await self.storage.save_artifact(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                artifact_type="graph",
                content=graph_model.dict(),
                metadata=ArtifactMetadata(
                    schema_version="2.0",
                    content_hash="",  # Will be calculated by storage
                    repo_id=repo_id
                )
            )
            
            # Write capabilities artifact
            capabilities_artifact_id = await self.storage.save_artifact(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                artifact_type="capabilities",
                content=[cap.dict() for cap in capabilities],
                metadata=ArtifactMetadata(
                    schema_version="2.0",
                    content_hash="",  # Will be calculated by storage
                    repo_id=repo_id
                )
            )
            
            # Also write warnings if any
            warnings = self._collect_warnings_from_graph(graph_model)
            if warnings:
                warnings_artifact_id = await self.storage.save_artifact(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    artifact_type="warnings",
                    content=[w.dict() for w in warnings],
                    metadata=ArtifactMetadata(
                        schema_version="2.0",
                        content_hash="",  # Will be calculated by storage
                        repo_id=repo_id
                    )
                )
            
            return {
                "graph_artifact_id": graph_artifact_id,
                "capabilities_artifact_id": capabilities_artifact_id,
                "warnings_artifact_id": warnings_artifact_id if warnings else None,
                "artifacts": ["graphs.json", "capabilities.json", "warnings.json"]
            }
            
        except Exception as e:
            logger.error(f"Map task failed for {task.repo_id}: {e}")
            raise
    
    def _collect_warnings_from_graph(self, graph_model: GraphModel) -> List[WarningItem]:
        """Collect warnings from graph model."""
        warnings = []
        
        # Collect warnings from low-confidence edges
        for edge in graph_model.edges:
            if edge.confidence < 0.7:
                warnings.append(WarningItem(
                    phase="mapping",
                    file=edge.evidence[0].file if edge.evidence else None,
                    reason_code=edge.reason_code or "low_confidence",
                    evidence=edge.evidence[0] if edge.evidence else None,
                    message=f"Low confidence edge: {edge.from_} -> {edge.to}",
                    count=1
                ))
        
        # Collect warnings from hypothesis edges
        for edge in graph_model.suggested_edges:
            warnings.append(WarningItem(
                phase="mapping",
                file=edge.evidence[0].file if edge.evidence else None,
                reason_code=edge.reason_code or "hypothesis",
                evidence=edge.evidence[0] if edge.evidence else None,
                message=f"Hypothesis edge: {edge.from_} -> {edge.to}",
                count=1
            ))
        
        return warnings
    
    async def _build_graphs(self, repo_path: Path, merged_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build graphs from merged data."""
        # This would use the GraphBuilder class
        # For now, return a simplified structure
        return {
            "import_graph": {},
            "route_graph": {},
            "job_graph": {},
            "call_graph": {},
            "store_graph": {},
            "external_graph": {}
        }
    
    async def _build_capabilities(self, repo_path: Path, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build capabilities from graph data."""
        # This would use the CapabilityAnalyzer class
        # For now, return a simplified structure
        return {
            "capabilities": [],
            "summary": {
                "total_capabilities": 0,
                "lanes": {},
                "centrality_scores": {}
            }
        }
    
    async def _run_summarize_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run summarization task with LLM."""
        logger.info(f"Running summarize task for {task.repo_id}")
        
        async with self.llm_limiter.semaphore:
            try:
                # Get mapped data
                mapped_path = task.repo_path / "mapped.json"
                if not mapped_path.exists():
                    raise FileNotFoundError("Mapped data not found")
                
                mapped_data = json.loads(mapped_path.read_text())
                
                # Generate summaries
                summaries = await self._generate_summaries(task.repo_path, mapped_data)
                
                # Store summaries
                summaries_path = task.repo_path / "summaries.json"
                summaries_path.write_text(json.dumps(summaries, indent=2))
                
                return {
                    "summaries": summaries,
                    "artifacts": ["summaries.json"]
                }
                
            except Exception as e:
                logger.error(f"Summarize task failed for {task.repo_id}: {e}")
                raise
    
    async def _generate_summaries(self, repo_path: Path, mapped_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summaries using LLM."""
        summaries = {
            "repo_summary": "Repository analysis complete",
            "capability_summaries": [],
            "file_summaries": [],
            "llm_usage": self.llm_client.get_usage_stats()
        }
        
        # Generate capability summaries
        for capability in mapped_data.get("capabilities", {}).get("capabilities", []):
            summary = {
                "capability_id": capability.get("id"),
                "summary": f"Capability: {capability.get('name', 'Unknown')}"
            }
            summaries["capability_summaries"].append(summary)
        
        return summaries
    
    async def _run_finalize_task(self, task: PipelineTask) -> Dict[str, Any]:
        """Run finalization task to complete the pipeline."""
        logger.info(f"Running finalize task for {task.repo_id}")
        
        try:
            # Collect all artifacts
            artifacts = await self._collect_artifacts(task.repo_path)
            
            # Generate final metrics
            metrics = await self._generate_final_metrics(task.job_id)
            
            # Store final results
            final_path = task.repo_path / "final.json"
            final_data = {
                "artifacts": artifacts,
                "metrics": metrics,
                "completed_at": time.time()
            }
            final_path.write_text(json.dumps(final_data, indent=2))
            
            return {
                "final_data": final_data,
                "artifacts": ["final.json"]
            }
            
        except Exception as e:
            logger.error(f"Finalize task failed for {task.repo_id}: {e}")
            raise
    
    async def _collect_artifacts(self, repo_path: Path) -> List[str]:
        """Collect all generated artifacts."""
        artifacts = []
        
        artifact_files = [
            "preflight.json",
            "parsed.json", 
            "merged.json",
            "mapped.json",
            "summaries.json",
            "final.json"
        ]
        
        for artifact_file in artifact_files:
            artifact_path = repo_path / artifact_file
            if artifact_path.exists():
                artifacts.append(artifact_file)
        
        return artifacts
    
    async def _generate_final_metrics(self, job_id: str) -> Dict[str, Any]:
        """Generate final metrics for the job."""
        metrics = self.metrics_collector.get_metrics()
        
        # Add job-specific metrics
        job_metrics = {
            "job_id": job_id,
            "total_duration": time.time() - self.active_jobs[job_id]["created_at"],
            "phases_completed": len(self.completed_tasks),
            "phases_failed": len(self.failed_tasks),
            "llm_usage": self.llm_client.get_usage_stats()
        }
        
        metrics.update(job_metrics)
        return metrics
    
    async def _task_processor(self) -> None:
        """Background task processor."""
        while not self.shutdown_requested:
            try:
                # Process ready tasks
                await self._process_ready_tasks()
                
                # Wait before next iteration
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Task processor error: {e}")
                await asyncio.sleep(5)
    
    async def _process_ready_tasks(self) -> None:
        """Process tasks that are ready to run."""
        for task_id, task in self.tasks.items():
            if task.phase == PipelinePhase.QUEUED and self._are_dependencies_met(task_id):
                # Start task
                task.phase = PipelinePhase.ACQUIRING
                task.started_at = time.time()
                
                # Update job progress
                self.job_progress[task.job_id]["current_phase"] = task.phase.value
                
                # Publish event
                event_stream = get_event_stream()
                await event_stream.emit_phase_change(task.job_id, task.phase.value, task.progress, f"Phase: {task.phase.value}")
                
                # Run task
                asyncio.create_task(self._run_task(task))
    
    def _are_dependencies_met(self, task_id: str) -> bool:
        """Check if all dependencies for a task are met."""
        dependencies = self.task_dependencies.get(task_id, set())
        return all(dep in self.completed_tasks for dep in dependencies)
    
    async def _run_task(self, task: PipelineTask) -> None:
        """Run a single task."""
        try:
            # Get task function
            task_func = self._get_task_function(task.task_id)
            
            # Run task
            result = await task_func(task)
            
            # Mark as completed
            task.phase = PipelinePhase.DONE
            task.completed_at = time.time()
            self.completed_tasks.add(task.task_id)
            
            # Update job progress
            self.job_progress[task.job_id]["tasks_completed"] += 1
            self.job_progress[task.job_id]["progress_percent"] = (
                self.job_progress[task.job_id]["tasks_completed"] / 
                self.job_progress[task.job_id]["total_tasks"] * 100
            )
            
            # Publish completion event
            event_stream = get_event_stream()
            await event_stream.emit_event(task.job_id, "task_completed", {
                "task_id": task.task_id,
                "result": result
            })
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            
            # Handle retry
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.phase = PipelinePhase.QUEUED
                task.started_at = None
                logger.info(f"Retrying task {task.task_id} (attempt {task.retry_count})")
            else:
                # Mark as failed
                task.phase = PipelinePhase.FAILED
                task.error = str(e)
                self.failed_tasks.add(task.task_id)
                
                # Publish failure event
                event_stream = get_event_stream()
                await event_stream.emit_event(task.job_id, "task_failed", {
                    "task_id": task.task_id,
                    "error": str(e)
                })
    
    def _get_task_function(self, task_id: str):
        """Get the function for a task."""
        task_functions = {
            "preflight": self._run_preflight_task,
            "parse_batch": self._run_parse_batch_task,
            "merge": self._run_merge_task,
            "map": self._run_map_task,
            "summarize": self._run_summarize_task,
            "finalize": self._run_finalize_task,
        }
        
        for task_name, task_func in task_functions.items():
            if task_name in task_id:
                return task_func
        
        raise ValueError(f"Unknown task: {task_id}")
    
    async def _metrics_collector(self) -> None:
        """Background metrics collector."""
        while not self.shutdown_requested:
            try:
                # Collect metrics
                metrics = self.metrics_collector.get_metrics()
                
                # Update job metrics
                for job_id in self.active_jobs:
                    self.job_progress[job_id]["metrics"] = metrics
                
                # Wait before next collection
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Metrics collector error: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_old_jobs(self) -> None:
        """Clean up old completed jobs."""
        while not self.shutdown_requested:
            try:
                current_time = time.time()
                cleanup_threshold = 3600  # 1 hour
                
                jobs_to_remove = []
                for job_id, job_data in self.active_jobs.items():
                    if (current_time - job_data["created_at"]) > cleanup_threshold:
                        jobs_to_remove.append(job_id)
                
                for job_id in jobs_to_remove:
                    await self._cleanup_job(job_id)
                
                # Wait before next cleanup
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(300)
    
    async def _cleanup_job(self, job_id: str) -> None:
        """Clean up a completed job."""
        try:
            # Remove from active jobs
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
            
            # Remove from job phases
            if job_id in self.job_phases:
                del self.job_phases[job_id]
            
            # Remove from job progress
            if job_id in self.job_progress:
                del self.job_progress[job_id]
            
            # Remove related tasks
            tasks_to_remove = [task_id for task_id in self.tasks.keys() if task_id.startswith(job_id)]
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
            
            logger.info(f"Cleaned up job: {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup job {job_id}: {e}")
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a job."""
        if job_id not in self.active_jobs:
            return None
        
        return {
            "job_id": job_id,
            "repo_id": self.active_jobs[job_id]["repo_id"],
            "status": self.active_jobs[job_id]["status"],
            "phase": self.job_phases.get(job_id, PipelinePhase.QUEUED).value,
            "progress": self.job_progress.get(job_id, {}),
            "created_at": self.active_jobs[job_id]["created_at"]
        }
    
    async def get_job_events(self, job_id: str):
        """Get event stream for a job."""
        event_stream = get_event_stream()
        async for event in event_stream.create_stream(job_id):
            yield event
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "active_jobs": len(self.active_jobs),
            "total_tasks": len(self.tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "node_parse_usage": {
                "current": self.node_parse_limiter.current_usage,
                "max": self.node_parse_limiter.max_concurrent,
                "queue_size": len(self.node_parse_limiter.queue)
            },
            "llm_usage": {
                "current": self.llm_limiter.current_usage,
                "max": self.llm_limiter.max_concurrent,
                "queue_size": len(self.llm_limiter.queue)
            },
            "metrics": self.metrics_collector.get_metrics()
        }
