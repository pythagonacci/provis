"""Consolidated API v2 with new endpoints and improved structure."""
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .models import IngestResponse, StatusPayload
from .pipeline_orchestrator import PipelineOrchestrator
from .status_manager import StatusManager, JobStatus
from .storage import ArtifactStorage
from .events import get_event_stream

logger = logging.getLogger(__name__)

# Global instances
pipeline_orchestrator: Optional[PipelineOrchestrator] = None
status_manager: Optional[StatusManager] = None
artifact_storage: Optional[ArtifactStorage] = None

def create_app() -> FastAPI:
    """Create FastAPI application with v2 API."""
    app = FastAPI(
        title="Provis API v2",
        description="Repository analysis and capability extraction API",
        version="2.0.0"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize services
    @app.on_event("startup")
    async def startup_event():
        global pipeline_orchestrator, status_manager, artifact_storage
        
        # Initialize services
        status_dir = Path("data/status")
        storage_dir = Path("data/storage")
        
        status_manager = StatusManager(status_dir)
        artifact_storage = ArtifactStorage(storage_dir)
        pipeline_orchestrator = PipelineOrchestrator()
        
        # Start pipeline orchestrator
        await pipeline_orchestrator.start()
        
        logger.info("API v2 services initialized")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        global pipeline_orchestrator
        
        if pipeline_orchestrator:
            await pipeline_orchestrator.stop()
        
        logger.info("API v2 services shut down")
    
    # Health check
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "2.0.0"}
    
    # Repository ingestion
    @app.post("/ingest", response_model=IngestResponse)
    async def ingest_repository(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
    ):
        """Ingest a repository ZIP file for analysis."""
        try:
            # Generate repo ID
            repo_id = f"repo_{int(asyncio.get_event_loop().time())}"
            
            # Create repo directory
            repo_dir = Path("data/repos") / repo_id
            repo_dir.mkdir(parents=True, exist_ok=True)
            
            # Save uploaded file
            zip_path = repo_dir / "repository.zip"
            with open(zip_path, "wb") as f:
                content = await file.read()
                f.write(content)
            
            # Extract ZIP file
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(repo_dir / "snapshot")
            
            # Start analysis pipeline
            job_id = await pipeline_orchestrator.ingest_repository(repo_id, repo_dir)
            
            # Create job in status manager
            status_manager.create_job(job_id, repo_id, str(repo_dir))
            
            return IngestResponse(
                job_id=job_id,
                repo_id=repo_id,
                status="queued",
                message="Repository ingestion started"
            )
            
        except Exception as e:
            logger.error(f"Repository ingestion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Job status
    @app.get("/status/{job_id}", response_model=StatusPayload)
    async def get_job_status(job_id: str):
        """Get status of a job."""
        status_data = status_manager.get_job_status(job_id)
        if not status_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return StatusPayload(**status_data)
    
    # Job events stream
    @app.get("/events/{job_id}")
    async def get_job_events(job_id: str):
        """Get real-time events for a job."""
        async def event_generator():
            async for event in status_manager.stream_job_events(job_id):
                yield f"data: {event}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    
    # Artifacts
    @app.get("/artifacts/{repo_id}")
    async def get_artifacts(repo_id: str):
        """Get all artifacts for a repository."""
        try:
            artifacts = {}
            
            artifact_types = ["tree", "files", "graphs", "capabilities", "summaries", "warnings", "metrics", "preflight"]
            
            for artifact_type in artifact_types:
                artifact_data = artifact_storage.retrieve_artifact(repo_id, artifact_type)
                if artifact_data:
                    artifacts[artifact_type] = artifact_data
            
            return {"repo_id": repo_id, "artifacts": artifacts}
            
        except Exception as e:
            logger.error(f"Failed to get artifacts for repo {repo_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/artifacts/{repo_id}/{artifact_type}")
    async def get_artifact(repo_id: str, artifact_type: str):
        """Get a specific artifact for a repository."""
        try:
            artifact_data = artifact_storage.retrieve_artifact(repo_id, artifact_type)
            if not artifact_data:
                raise HTTPException(status_code=404, detail="Artifact not found")
            
            return artifact_data
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get artifact {artifact_type} for repo {repo_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Pipeline statistics
    @app.get("/stats")
    async def get_pipeline_stats():
        """Get pipeline statistics."""
        try:
            stats = pipeline_orchestrator.get_pipeline_stats()
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get pipeline stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Status summary
    @app.get("/status")
    async def get_status_summary():
        """Get status summary."""
        try:
            summary = status_manager.get_status_summary()
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get status summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return app
