"""
Updated FastAPI application for Step 2 infrastructure upgrade.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .config import settings
from .database import get_session, Repo, Snapshot, Job, Artifact
from .storage import get_storage, presign
from .status import get_status_manager
from .events import get_event_manager
from .jobs_new import get_orchestrator
from .utils.zip_safe import extract_zip_safely, cleanup_extraction
from .models import IngestResponse, StatusPayload
from .observability import get_metrics_endpoint, get_metrics_content_type, get_metrics_collector
from .queue import get_queue

app = FastAPI(title="Provis Backend v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ORIGINS] if settings.CORS_ORIGINS else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "*.yourdomain.com"]  # Configure for production
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    
    # HSTS (only in production with HTTPS)
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

@app.on_event("startup")
async def startup():
    """Initialize database and storage on startup."""
    from .database import init_db
    init_db()

@app.get("/health")
def health():
    """Health check endpoint."""
    return {"ok": True, "version": "2.0"}

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    metrics_handler = get_metrics_endpoint()
    return PlainTextResponse(metrics_handler(), media_type=get_metrics_content_type())

@app.get("/queue/stats")
def queue_stats():
    """Get queue statistics and update Prometheus gauges."""
    try:
        queue_manager = get_queue()
        stats = queue_manager.get_queue_stats()
        
        # Update Prometheus queue size gauges
        metrics = get_metrics_collector()
        for queue_name, queue_stats in stats.items():
            metrics.update_queue_size(queue_name, queue_stats["queued"])
        
        return {
            "queues": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get queue stats: {str(e)}")

@app.post("/ingest", response_model=IngestResponse)
async def ingest_repo(file: UploadFile = File(...), settings: Optional[str] = Query(None)):
    """
    Ingest a repository zip file and start processing.
    
    Args:
        file: Zip file containing the repository
        settings: Optional settings JSON string
    
    Returns:
        IngestResponse with repo_id, snapshot_id, and job_id
    """
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, detail="Only .zip uploads supported")
    
    # Check file size
    max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "536870912"))  # 512MB
    if file.size and file.size > max_upload_bytes:
        raise HTTPException(413, detail=f"File too large: {file.size} bytes (max: {max_upload_bytes})")
    
    try:
        # Read file content
        content = await file.read()
        
        # Compute hashes
        content_hash = hashlib.sha256(content).hexdigest()
        settings_hash = hashlib.sha256(settings.encode() if settings else b"").hexdigest()[:16]
        
        # Create repo and snapshot
        with get_session() as session:
            # Create or get repo
            repo = Repo(name=file.filename.replace('.zip', ''))
            session.add(repo)
            session.commit()
            repo_id = str(repo.id)
            
            # Check if snapshot already exists (idempotency)
            existing_snapshot = session.query(Snapshot).filter(
                Snapshot.repo_id == repo.id,
                Snapshot.commit_hash == content_hash,
                Snapshot.settings_hash == settings_hash
            ).first()
            
            if existing_snapshot and existing_snapshot.status == "completed":
                # Return existing snapshot
                return IngestResponse(
                    repoId=repo_id,
                    snapshotId=str(existing_snapshot.id),
                    jobId=None,  # No new job needed
                    idempotency={
                        "commitHash": existing_snapshot.commit_hash,
                        "settingsHash": existing_snapshot.settings_hash
                    }
                )
            
            # Create new snapshot
            snapshot = Snapshot(
                repo_id=repo.id,
                commit_hash=content_hash,
                settings_hash=settings_hash,
                source="upload",
                status="processing"
            )
            session.add(snapshot)
            session.commit()
            snapshot_id = str(snapshot.id)
        
        # Store upload to S3
        storage = get_storage()
        upload_uri = f"s3://{storage.bucket}/uploads/{snapshot_id}.zip"
        # In a real implementation, you'd upload the content to S3 here
        
        # Create job and start processing
        orchestrator = get_orchestrator()
        job_id = orchestrator.create_job(repo_id, snapshot_id, settings_hash, upload_uri)
        
        return IngestResponse(
            repoId=repo_id,
            snapshotId=snapshot_id,
            jobId=job_id,
            idempotency={
                "commitHash": content_hash,
                "settingsHash": settings_hash
            }
        )
        
    except Exception as e:
        raise HTTPException(500, detail=f"Upload failed: {str(e)}")

@app.get("/status/{job_id}", response_model=StatusPayload)
def get_job_status(job_id: str):
    """
    Get job status with real-time progress information.
    
    Args:
        job_id: Job ID
    
    Returns:
        StatusPayload with current progress
    """
    try:
        status_manager = get_status_manager()
        status = status_manager.get_status(job_id)
        
        return StatusPayload(
            jobId=status.get("jobId", job_id),
            repoId=status.get("repoId"),
            snapshotId=status.get("snapshotId"),
            phase=status.get("phase", "unknown"),
            pct=status.get("pct", 0),
            filesDiscovered=status.get("filesDiscovered", 0),
            filesParsed=status.get("filesParsed", 0),
            importsTotal=status.get("importsTotal", 0),
            importsInternal=status.get("importsInternal", 0),
            importsExternal=status.get("importsExternal", 0),
            filesSummarized=status.get("filesSummarized", 0),
            capabilitiesBuilt=status.get("capabilitiesBuilt", 0),
            warnings=status.get("warnings", 0),
            error=status.get("error"),
            updatedAt=status.get("updatedAt")
        )
        
    except Exception as e:
        raise HTTPException(404, detail=f"Job not found: {str(e)}")

@app.get("/jobs/{job_id}/events")
def stream_job_events(job_id: str, last_event_id: Optional[str] = Query(None)):
    """
    Stream job events as Server-Sent Events (SSE) with backfill support.
    
    Args:
        job_id: Job ID
        last_event_id: Last event ID seen (for backfill)
    
    Returns:
        SSE stream of job events
    """
    def event_generator():
        event_manager = get_event_manager()
        last_id = last_event_id or "0"
        
        # Backfill recent events if last_event_id is provided
        if last_event_id and last_event_id != "0":
            try:
                # Get events since last_event_id
                backfill_events = event_manager.get_events(job_id, last_event_id, count=100)
                for event in backfill_events:
                    # Format as SSE
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event)}\n\n"
                    last_id = event["id"]
            except Exception as e:
                logger.warning(f"Failed to backfill events for job {job_id}: {e}")
        
        # Stream new events
        while True:
            try:
                # Get new events
                events = event_manager.stream_events(job_id, last_id)
                
                for event in events:
                    last_id = event["id"]
                    
                    # Format as SSE
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event)}\n\n"
                
                # Send heartbeat every 10 seconds
                yield f"event: heartbeat\n"
                yield f"data: {json.dumps({'timestamp': datetime.utcnow().isoformat()})}\n\n"
                
            except Exception as e:
                yield f"event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.get("/repos/{repo_id}/snapshots/{snapshot_id}/artifacts")
def list_artifacts(repo_id: str, snapshot_id: str, presign_urls: bool = Query(False)):
    """
    List artifacts for a snapshot with optional presigned URLs.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Snapshot ID
        presign_urls: Whether to include presigned URLs
    
    Returns:
        List of artifacts with metadata
    """
    try:
        with get_session() as session:
            # Verify snapshot exists and belongs to repo
            snapshot = session.query(Snapshot).filter(
                Snapshot.id == snapshot_id,
                Snapshot.repo_id == repo_id
            ).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Snapshot not found")
            
            # Get artifacts
            artifacts = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot_id
            ).all()
            
            result = []
            storage = get_storage()
            
            for artifact in artifacts:
                artifact_data = {
                    "kind": artifact.kind,
                    "version": artifact.version,
                    "bytes": artifact.bytes,
                    "createdAt": artifact.created_at.isoformat(),
                    "uri": artifact.uri
                }
                
                if presign_urls:
                    try:
                        artifact_data["url"] = storage.presign(artifact.uri)
                    except Exception as e:
                        artifact_data["urlError"] = str(e)
                
                result.append(artifact_data)
            
            return {
                "snapshotId": snapshot_id,
                "artifacts": result
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to list artifacts: {str(e)}")

@app.get("/repo/{repo_id}/graph")
def get_graph(repo_id: str, snapshot_id: Optional[str] = Query(None)):
    """
    Get dependency graph for a repository.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Optional snapshot ID (defaults to latest)
    
    Returns:
        Graph data
    """
    try:
        with get_session() as session:
            # Get snapshot
            if snapshot_id:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.id == snapshot_id,
                    Snapshot.repo_id == repo_id
                ).first()
            else:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.repo_id == repo_id
                ).order_by(Snapshot.created_at.desc()).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Snapshot not found")
            
            # Get graph artifact
            artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "graph"
            ).order_by(Artifact.version.desc()).first()
            
            if not artifact:
                raise HTTPException(404, detail="Graph artifact not found")
            
            # Read artifact content
            storage = get_storage()
            content = storage.get_artifact(artifact.uri)
            return json.loads(content.decode('utf-8'))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get graph: {str(e)}")

@app.get("/repo/{repo_id}/files")
def get_files(repo_id: str, snapshot_id: Optional[str] = Query(None)):
    """
    Get parsed files for a repository.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Optional snapshot ID (defaults to latest)
    
    Returns:
        Files data
    """
    try:
        with get_session() as session:
            # Get snapshot
            if snapshot_id:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.id == snapshot_id,
                    Snapshot.repo_id == repo_id
                ).first()
            else:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.repo_id == repo_id
                ).order_by(Snapshot.created_at.desc()).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Snapshot not found")
            
            # Get files artifact
            artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "files"
            ).order_by(Artifact.version.desc()).first()
            
            if not artifact:
                raise HTTPException(404, detail="Files artifact not found")
            
            # Read artifact content
            storage = get_storage()
            content = storage.get_artifact(artifact.uri)
            return json.loads(content.decode('utf-8'))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get files: {str(e)}")

@app.get("/repo/{repo_id}/capabilities")
def get_capabilities(repo_id: str, snapshot_id: Optional[str] = Query(None)):
    """
    Get capabilities for a repository.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Optional snapshot ID (defaults to latest)
    
    Returns:
        Capabilities data
    """
    try:
        with get_session() as session:
            # Get snapshot
            if snapshot_id:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.id == snapshot_id,
                    Snapshot.repo_id == repo_id
                ).first()
            else:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.repo_id == repo_id
                ).order_by(Snapshot.created_at.desc()).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Snapshot not found")
            
            # Get capabilities artifact
            artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "capabilities"
            ).order_by(Artifact.version.desc()).first()
            
            if not artifact:
                raise HTTPException(404, detail="Capabilities artifact not found")
            
            # Read artifact content
            storage = get_storage()
            content = storage.get_artifact(artifact.uri)
            return json.loads(content.decode('utf-8'))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get capabilities: {str(e)}")

@app.get("/repo/{repo_id}/metrics")
def get_metrics(repo_id: str, snapshot_id: Optional[str] = Query(None)):
    """
    Get metrics for a repository.
    
    Args:
        repo_id: Repository ID
        snapshot_id: Optional snapshot ID (defaults to latest)
    
    Returns:
        Metrics data
    """
    try:
        with get_session() as session:
            # Get snapshot
            if snapshot_id:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.id == snapshot_id,
                    Snapshot.repo_id == repo_id
                ).first()
            else:
                snapshot = session.query(Snapshot).filter(
                    Snapshot.repo_id == repo_id
                ).order_by(Snapshot.created_at.desc()).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Snapshot not found")
            
            # Get metrics artifact
            artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "metrics"
            ).order_by(Artifact.version.desc()).first()
            
            if not artifact:
                raise HTTPException(404, detail="Metrics artifact not found")
            
            # Read artifact content
            storage = get_storage()
            content = storage.get_artifact(artifact.uri)
            return json.loads(content.decode('utf-8'))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get metrics: {str(e)}")

# Legacy endpoints for backward compatibility
@app.get("/v1/repo/{repo_id}")
def get_repo_overview_v1(repo_id: str):
    """Legacy endpoint - reads from artifacts for backward compatibility."""
    try:
        with get_session() as session:
            # Get latest snapshot
            snapshot = session.query(Snapshot).filter(
                Snapshot.repo_id == repo_id
            ).order_by(Snapshot.created_at.desc()).first()
            
            if not snapshot:
                raise HTTPException(404, detail="Repository not found")
            
            # Get artifacts
            tree_artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "tree"
            ).order_by(Artifact.version.desc()).first()
            
            files_artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "files"
            ).order_by(Artifact.version.desc()).first()
            
            capabilities_artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "capabilities"
            ).order_by(Artifact.version.desc()).first()
            
            metrics_artifact = session.query(Artifact).filter(
                Artifact.snapshot_id == snapshot.id,
                Artifact.kind == "metrics"
            ).order_by(Artifact.version.desc()).first()
            
            if not all([tree_artifact, files_artifact, capabilities_artifact, metrics_artifact]):
                raise HTTPException(404, detail="One or more artifacts missing")
            
            # Read artifact content
            storage = get_storage()
            
            tree_data = json.loads(storage.get_artifact(tree_artifact.uri).decode('utf-8'))
            files_data = json.loads(storage.get_artifact(files_artifact.uri).decode('utf-8'))
            capabilities_data = json.loads(storage.get_artifact(capabilities_artifact.uri).decode('utf-8'))
            metrics_data = json.loads(storage.get_artifact(metrics_artifact.uri).decode('utf-8'))
            
            # Transform to legacy format
            caps = capabilities_data.get("capabilities", [])
            return {
                "tree": tree_data,
                "files": files_data,
                "capabilities": [
                    {
                        **c,
                        "entryPoints": c.get("entryPoints") or [e.get("path") if isinstance(e, dict) else e for e in c.get("entrypoints", [])],
                    }
                    for c in caps
                ],
                "metrics": metrics_data,
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get repo overview: {str(e)}")

@app.get("/repo/{repo_id}/qa")
def qa_endpoint(repo_id: str, question: str = Query(...)):
    """QA endpoint - placeholder for now."""
    raise HTTPException(501, detail="QA endpoint not yet implemented in v2")
