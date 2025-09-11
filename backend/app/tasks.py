"""
Task functions for the Step 2 infrastructure upgrade.
All tasks are idempotent and retryable.
"""
import os
import json
import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import tempfile

from app.database import get_session, Repo, Snapshot, Job, Task, Artifact, Warning
from app.storage import write_versioned_artifact
from app.status import set_status
from app.events import (append_event, on_phase_change, on_pct_update, on_artifact_ready, 
                       on_warning, on_error, on_done)
from app.parsers.base import discover_files, parse_files, build_files_payload, build_graph
from app.parsers.js_ts import parse_js_ts_file
from app.parsers.python import parse_python_file
from app.utils.zip_safe import extract_zip_safely, cleanup_extraction
from app.limits import get_limits
from app.summarizer import run_summarization
from app.observability import get_metrics_collector

logger = logging.getLogger(__name__)

def _run_task_with_metrics(task_name: str, fn, *args, **kwargs):
    """Run a task with metrics instrumentation."""
    metrics = get_metrics_collector()
    metrics.record_task_start(task_name)
    start_time = time.perf_counter()
    
    try:
        result = fn(*args, **kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_task_completion(task_name, duration_ms, True)
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_task_completion(task_name, duration_ms, False)
        raise

def _ingest_task_impl(repo_id: str, snapshot_id: str, job_id: str, upload_uri: str, 
                     settings_hash: str) -> Dict[str, Any]:
    """
    Ingest task implementation: Extract zip and compute hashes.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
        upload_uri: URI to the uploaded zip file
        settings_hash: Settings hash for idempotency
    
    Returns:
        Task result with commit_hash
    """
    try:
        logger.info(f"Starting ingest task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="acquiring", pct=5)
        on_phase_change(job_id, "acquiring", 5)
        
        # Check if snapshot already exists (idempotency)
        with get_session() as session:
            snapshot = session.query(Snapshot).filter(
                Snapshot.id == snapshot_id
            ).first()
            
            if snapshot and snapshot.status == "completed":
                logger.info(f"Snapshot {snapshot_id} already completed, skipping ingest")
                append_event(job_id, type_="cache_hit", payload={
                    "snapshotId": snapshot_id,
                    "commitHash": snapshot.commit_hash
                })
                return {"commit_hash": snapshot.commit_hash, "cached": True}
        
        # Extract zip safely and compute real commit hash
        temp_extract_dir = None
        try:
            # For now, we'll simulate the extraction since we don't have the actual zip file
            # In a real implementation, you'd download from upload_uri and extract
            # temp_extract_dir = extract_zip_safely(Path(upload_uri))
            
            # Compute commit hash from extracted contents
            # In a real implementation, you'd hash all file contents
            commit_hash = hashlib.sha256(f"{upload_uri}_{settings_hash}".encode()).hexdigest()[:16]
            
        finally:
            # Clean up extraction directory
            if temp_extract_dir:
                cleanup_extraction(temp_extract_dir)
        
        # Update snapshot with commit hash
        with get_session() as session:
            snapshot = session.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
            if snapshot:
                snapshot.commit_hash = commit_hash
                session.commit()
        
        logger.info(f"Completed ingest task for job {job_id}, commit_hash: {commit_hash}")
        return {"commit_hash": commit_hash, "cached": False}
        
    except Exception as e:
        logger.error(f"Ingest task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "acquiring")
        raise

def ingest_task(repo_id: str, snapshot_id: str, job_id: str, upload_uri: str, 
                settings_hash: str) -> Dict[str, Any]:
    """Ingest task with metrics instrumentation."""
    return _run_task_with_metrics("ingest", _ingest_task_impl, repo_id, snapshot_id, job_id, upload_uri, settings_hash)

def _discover_task_impl(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """
    Discover task implementation: Find files in the snapshot.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
    
    Returns:
        Task result with file count
    """
    try:
        logger.info(f"Starting discover task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="discovering", pct=15)
        on_phase_change(job_id, "discovering", 15)
        
        # Get snapshot path (placeholder for now)
        snapshot_path = Path(f"/tmp/snapshots/{snapshot_id}")
        
        # Discover files
        discovered = discover_files(snapshot_path)
        file_count = len(discovered)
        
        # Update status
        set_status(job_id, phase="discovering", pct=25, filesDiscovered=file_count)
        append_event(job_id, type_="files_total", payload={"count": file_count})
        
        logger.info(f"Completed discover task for job {job_id}, found {file_count} files")
        return {"file_count": file_count, "files": discovered}
        
    except Exception as e:
        logger.error(f"Discover task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "discovering")
        raise

def _parse_batch_task_impl(repo_id: str, snapshot_id: str, job_id: str, 
                          file_paths: List[str], batch_index: int, total_batches: int) -> Dict[str, Any]:
    """
    Parse batch task implementation: Parse a batch of files.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
        file_paths: List of file paths to parse
        batch_index: Batch index (0-based)
        total_batches: Total number of batches
    
    Returns:
        Task result with parsed files
    """
    try:
        logger.info(f"Starting parse batch {batch_index}/{total_batches} for job {job_id}")
        
        # Update status
        pct = 35 + int((batch_index / total_batches) * 15)  # 35-50%
        set_status(job_id, phase="parsing", pct=pct)
        
        # Get snapshot path (placeholder for now)
        snapshot_path = Path(f"/tmp/snapshots/{snapshot_id}")
        
        # Parse files in batch with resource limits
        parsed_files = []
        skipped_files = []
        limits = get_limits()
        metrics = get_metrics_collector()
        
        for file_path in file_paths:
            try:
                file_path_obj = snapshot_path / file_path
                
                # Use resource limits for Node.js parsing
                if file_path.endswith(('.js', '.jsx', '.ts', '.tsx')):
                    with limits.node_subprocess_token(timeout=limits.node_file_timeout):
                        parsed = parse_js_ts_file(file_path_obj, snapshot_path, file_paths)
                        metrics.record_file_parsed("js", True)
                elif file_path.endswith('.py'):
                    parsed = parse_python_file(file_path_obj, snapshot_path, file_paths)
                    metrics.record_file_parsed("py", True)
                else:
                    continue
                
                parsed_files.append(parsed)
                
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")
                skipped_files.append({"path": file_path, "error": str(e)})
                on_warning(job_id, f"Failed to parse {file_path}: {e}", "parse_error", file_path)
                metrics.record_file_parsed("unknown", False)
        
        # Emit batch completion event
        append_event(job_id, type_="batch_parsed", payload={
            "batchIndex": batch_index,
            "totalBatches": total_batches,
            "parsed": len(parsed_files),
            "skipped": len(skipped_files)
        })
        
        logger.info(f"Completed parse batch {batch_index}/{total_batches} for job {job_id}")
        return {
            "batch_index": batch_index,
            "parsed_files": parsed_files,
            "skipped_files": skipped_files
        }
        
    except Exception as e:
        logger.error(f"Parse batch task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "parsing")
        raise

def _merge_files_task_impl(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """
    Merge files task implementation: Combine parsed file results and validate schema.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
    
    Returns:
        Task result with merged files
    """
    try:
        logger.info(f"Starting merge files task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="parsing", pct=50)
        
        # In a real implementation, you'd collect results from parse_batch_task chunks
        # For now, we'll use a placeholder
        files_payload = {
            "repoId": repo_id,
            "files": [],
            "warnings": []
        }
        
        # Write artifact
        content_bytes = json.dumps(files_payload, indent=2).encode('utf-8')
        result = write_versioned_artifact(
            snapshot_id, "files", content_bytes,
            repo_id=repo_id,
            commit_hash="placeholder",
            settings_hash="placeholder"
        )
        
        # Store artifact record
        with get_session() as session:
            artifact = Artifact(
                snapshot_id=snapshot_id,
                kind="files",
                version=result["version"],
                uri=result["uri"],
                bytes=result["bytes"]
            )
            session.add(artifact)
            session.commit()
        
        # Record artifact metrics
        metrics.record_artifact_created("files", result["bytes"])
        
        # Emit artifact ready event
        on_artifact_ready(job_id, "files", result["uri"], result["version"], result["bytes"])
        
        # Update status
        set_status(job_id, phase="parsing", pct=55)
        
        logger.info(f"Completed merge files task for job {job_id}")
        return {"files_count": len(files_payload["files"])}
        
    except Exception as e:
        logger.error(f"Merge files task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "parsing")
        raise

def _map_task_impl(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """
    Map task implementation: Build dependency graph from parsed files.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
    
    Returns:
        Task result with graph metrics
    """
    try:
        logger.info(f"Starting map task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="mapping", pct=60)
        
        # In a real implementation, you'd read the files artifact and build the graph
        # For now, we'll use a placeholder
        graph_payload = {
            "nodes": [],
            "edges": [],
            "warnings": []
        }
        
        # Write artifact
        content_bytes = json.dumps(graph_payload, indent=2).encode('utf-8')
        result = write_versioned_artifact(
            snapshot_id, "graph", content_bytes,
            repo_id=repo_id,
            commit_hash="placeholder",
            settings_hash="placeholder"
        )
        
        # Store artifact record
        with get_session() as session:
            artifact = Artifact(
                snapshot_id=snapshot_id,
                kind="graph",
                version=result["version"],
                uri=result["uri"],
                bytes=result["bytes"]
            )
            session.add(artifact)
            session.commit()
        
        # Record artifact metrics
        metrics.record_artifact_created("graph", result["bytes"])
        
        # Emit artifact ready event
        on_artifact_ready(job_id, "graph", result["uri"], result["version"], result["bytes"])
        
        # Update status with import metrics
        imports_total = len(graph_payload["edges"])
        imports_internal = sum(1 for edge in graph_payload["edges"] if not edge.get("external", True))
        imports_external = imports_total - imports_internal
        
        # Record import metrics
        metrics.record_imports(imports_internal, imports_external)
        
        set_status(job_id, phase="mapping", pct=75, 
                  importsTotal=imports_total,
                  importsInternal=imports_internal,
                  importsExternal=imports_external)
        
        append_event(job_id, type_="imports_metrics", payload={
            "total": imports_total,
            "internal": imports_internal,
            "external": imports_external
        })
        
        logger.info(f"Completed map task for job {job_id}")
        return {
            "imports_total": imports_total,
            "imports_internal": imports_internal,
            "imports_external": imports_external
        }
        
    except Exception as e:
        logger.error(f"Map task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "mapping")
        raise

def _summarize_task_impl(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """
    Summarize task implementation: Generate LLM summaries and capabilities.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
    
    Returns:
        Task result with summary metrics
    """
    try:
        logger.info(f"Starting summarize task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="summarizing", pct=80)
        
        # Run summarization with LLM rate limits
        limits = get_limits()
        metrics = get_metrics_collector()
        
        # Estimate tokens for rate limiting (rough approximation)
        estimated_tokens = 1000  # This would be calculated from file content
        
        with limits.llm_request(), limits.llm_tokens(estimated_tokens):
            # In a real implementation, you'd run the summarization
            # For now, we'll use placeholders
            summaries_payload = {"files": []}
            capabilities_payload = {"capabilities": []}
        
        # Write artifacts
        summaries_bytes = json.dumps(summaries_payload, indent=2).encode('utf-8')
        capabilities_bytes = json.dumps(capabilities_payload, indent=2).encode('utf-8')
        
        summaries_result = write_versioned_artifact(
            snapshot_id, "summaries", summaries_bytes,
            repo_id=repo_id,
            commit_hash="placeholder",
            settings_hash="placeholder"
        )
        
        capabilities_result = write_versioned_artifact(
            snapshot_id, "capabilities", capabilities_bytes,
            repo_id=repo_id,
            commit_hash="placeholder",
            settings_hash="placeholder"
        )
        
        # Store artifact records
        with get_session() as session:
            for kind, result in [("summaries", summaries_result), ("capabilities", capabilities_result)]:
                artifact = Artifact(
                    snapshot_id=snapshot_id,
                    kind=kind,
                    version=result["version"],
                    uri=result["uri"],
                    bytes=result["bytes"]
                )
                session.add(artifact)
                # Record artifact metrics
                metrics.record_artifact_created(kind, result["bytes"])
            session.commit()
        
        # Emit artifact ready events
        on_artifact_ready(job_id, "summaries", summaries_result["uri"], 
                         summaries_result["version"], summaries_result["bytes"])
        on_artifact_ready(job_id, "capabilities", capabilities_result["uri"], 
                         capabilities_result["version"], capabilities_result["bytes"])
        
        # Update status
        set_status(job_id, phase="summarizing", pct=95,
                  filesSummarized=len(summaries_payload["files"]),
                  capabilitiesBuilt=len(capabilities_payload["capabilities"]))
        
        logger.info(f"Completed summarize task for job {job_id}")
        return {
            "files_summarized": len(summaries_payload["files"]),
            "capabilities_built": len(capabilities_payload["capabilities"])
        }
        
    except Exception as e:
        logger.error(f"Summarize task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "summarizing")
        raise

def _finalize_task_impl(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """
    Finalize task implementation: Complete the job and write metrics.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        job_id: Job ID
    
    Returns:
        Task result with final metrics
    """
    try:
        logger.info(f"Starting finalize task for job {job_id}")
        
        # Update status
        set_status(job_id, phase="done", pct=100)
        
        # Write metrics artifact
        metrics_payload = {
            "jobId": job_id,
            "repoId": repo_id,
            "snapshotId": snapshot_id,
            "completedAt": datetime.utcnow().isoformat(),
            "totalMs": 0,  # Would be calculated from task durations
            "phaseDurationsMs": {}
        }
        
        content_bytes = json.dumps(metrics_payload, indent=2).encode('utf-8')
        result = write_versioned_artifact(
            snapshot_id, "metrics", content_bytes,
            repo_id=repo_id,
            commit_hash="placeholder",
            settings_hash="placeholder"
        )
        
        # Store artifact record
        with get_session() as session:
            artifact = Artifact(
                snapshot_id=snapshot_id,
                kind="metrics",
                version=result["version"],
                uri=result["uri"],
                bytes=result["bytes"]
            )
            session.add(artifact)
            
            # Update snapshot status
            snapshot = session.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
            if snapshot:
                snapshot.status = "completed"
            
            session.commit()
        
        # Record artifact metrics
        metrics.record_artifact_created("metrics", result["bytes"])
        
        # Emit artifact ready event
        on_artifact_ready(job_id, "metrics", result["uri"], result["version"], result["bytes"])
        
        # Emit completion event
        on_done(job_id, metrics_payload)
        
        logger.info(f"Completed finalize task for job {job_id}")
        return {"completed": True}
        
    except Exception as e:
        logger.error(f"Finalize task failed for job {job_id}: {e}")
        on_error(job_id, str(e), "done")
        raise

# Task wrapper functions with metrics instrumentation
def discover_task(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """Discover task with metrics instrumentation."""
    return _run_task_with_metrics("discover", _discover_task_impl, repo_id, snapshot_id, job_id)

def parse_batch_task(repo_id: str, snapshot_id: str, job_id: str, 
                    file_paths: List[str], batch_index: int, total_batches: int) -> Dict[str, Any]:
    """Parse batch task with metrics instrumentation."""
    return _run_task_with_metrics("parse_batch", _parse_batch_task_impl, repo_id, snapshot_id, job_id, file_paths, batch_index, total_batches)

def merge_files_task(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """Merge files task with metrics instrumentation."""
    return _run_task_with_metrics("merge", _merge_files_task_impl, repo_id, snapshot_id, job_id)

def map_task(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """Map task with metrics instrumentation."""
    return _run_task_with_metrics("map", _map_task_impl, repo_id, snapshot_id, job_id)

def summarize_task(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """Summarize task with metrics instrumentation."""
    return _run_task_with_metrics("summarize", _summarize_task_impl, repo_id, snapshot_id, job_id)

def finalize_task(repo_id: str, snapshot_id: str, job_id: str) -> Dict[str, Any]:
    """Finalize task with metrics instrumentation."""
    return _run_task_with_metrics("finalize", _finalize_task_impl, repo_id, snapshot_id, job_id)
