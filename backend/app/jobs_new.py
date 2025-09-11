"""
New job orchestration system using task-based architecture.
This replaces the old in-process JobQueue with distributed tasks.
"""
import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from app.database import get_session, Repo, Snapshot, Job, Task
from app.queue import enqueue, get_queue
from app.status import set_status
from app.events import append_event, on_phase_change
from app.tasks import (ingest_task, discover_task, parse_batch_task, merge_files_task, 
                      map_task, summarize_task, finalize_task)
from rq.retry import Retry

logger = logging.getLogger(__name__)

class JobOrchestrator:
    """Orchestrates job execution using distributed tasks."""
    
    def __init__(self):
        self.batch_size = int(os.getenv("PARSE_BATCH_SIZE", "50"))
        
        # Define retry policies for different task types
        self.retry_policies = {
            'ingest': Retry(max=3, interval=[30, 60, 120]),  # 30s, 1m, 2m
            'discover': Retry(max=2, interval=[10, 30]),     # 10s, 30s
            'parse_batch': Retry(max=3, interval=[60, 120, 300]),  # 1m, 2m, 5m (Node parsing can be slow)
            'merge': Retry(max=2, interval=[30, 60]),        # 30s, 1m
            'map': Retry(max=2, interval=[30, 60]),          # 30s, 1m
            'summarize': Retry(max=3, interval=[120, 300, 600]),  # 2m, 5m, 10m (LLM rate limits)
            'finalize': Retry(max=2, interval=[30, 60])      # 30s, 1m
        }
        
    def create_job(self, repo_id: str, snapshot_id: str, settings_hash: str, 
                   upload_uri: str = None) -> str:
        """
        Create a new job and enqueue the first task.
        
        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            settings_hash: Settings hash for idempotency
            upload_uri: URI to uploaded zip file
        
        Returns:
            Job ID
        """
        try:
            # Create job record
            with get_session() as session:
                job = Job(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    phase="queued",
                    pct=0
                )
                session.add(job)
                session.commit()
                job_id = str(job.id)
            
            # Enqueue ingest task
            queue_manager = get_queue()
            task_id = queue_manager.enqueue(
                "app.tasks.ingest_task",
                queue="high",
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id,
                    "upload_uri": upload_uri or "",
                    "settings_hash": settings_hash
                },
                priority=3,
                job_id=f"ingest_{job_id}",
                retry_policy=self.retry_policies['ingest']
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="ingest",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Created job {job_id} with ingest task {task_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to create job: {e}")
            raise
    
    def enqueue_discover_task(self, repo_id: str, snapshot_id: str, job_id: str) -> str:
        """Enqueue discover task after ingest completes."""
        try:
            task_id = enqueue(
                "app.tasks.discover_task",
                queue="normal",
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id
                },
                priority=2,
                job_id=f"discover_{job_id}"
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="discover",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Enqueued discover task {task_id} for job {job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue discover task: {e}")
            raise
    
    def enqueue_parse_batches(self, repo_id: str, snapshot_id: str, job_id: str, 
                             file_paths: List[str]) -> List[str]:
        """Enqueue parse batch tasks for all files."""
        try:
            # Split files into batches
            batches = [file_paths[i:i + self.batch_size] 
                      for i in range(0, len(file_paths), self.batch_size)]
            total_batches = len(batches)
            
            task_ids = []
            queue_manager = get_queue()
            for batch_index, batch_files in enumerate(batches):
                task_id = queue_manager.enqueue(
                    "app.tasks.parse_batch_task",
                    queue="normal",
                    kwargs={
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "job_id": job_id,
                        "file_paths": batch_files,
                        "batch_index": batch_index,
                        "total_batches": total_batches
                    },
                    priority=1,
                    job_id=f"parse_batch_{batch_index}_{job_id}",
                    retry_policy=self.retry_policies['parse_batch']
                )
                
                # Create task record
                with get_session() as session:
                    task = Task(
                        job_id=job_id,
                        name="parse_batch",
                        batch_index=batch_index,
                        state="queued"
                    )
                    session.add(task)
                    session.commit()
                
                task_ids.append(task_id)
            
            logger.info(f"Enqueued {total_batches} parse batch tasks for job {job_id}")
            return task_ids
            
        except Exception as e:
            logger.error(f"Failed to enqueue parse batches: {e}")
            raise
    
    def enqueue_merge_task(self, repo_id: str, snapshot_id: str, job_id: str) -> str:
        """Enqueue merge task after all parse batches complete."""
        try:
            task_id = enqueue(
                "app.tasks.merge_files_task",
                queue="normal",
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id
                },
                priority=2,
                job_id=f"merge_{job_id}"
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="merge",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Enqueued merge task {task_id} for job {job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue merge task: {e}")
            raise
    
    def enqueue_map_task(self, repo_id: str, snapshot_id: str, job_id: str) -> str:
        """Enqueue map task after merge completes."""
        try:
            task_id = enqueue(
                "app.tasks.map_task",
                queue="normal",
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id
                },
                priority=2,
                job_id=f"map_{job_id}"
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="map",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Enqueued map task {task_id} for job {job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue map task: {e}")
            raise
    
    def enqueue_summarize_task(self, repo_id: str, snapshot_id: str, job_id: str) -> str:
        """Enqueue summarize task after map completes."""
        try:
            task_id = enqueue(
                "app.tasks.summarize_task",
                queue="low",  # Lower priority for LLM work
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id
                },
                priority=0,
                job_id=f"summarize_{job_id}"
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="summarize",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Enqueued summarize task {task_id} for job {job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue summarize task: {e}")
            raise
    
    def enqueue_finalize_task(self, repo_id: str, snapshot_id: str, job_id: str) -> str:
        """Enqueue finalize task after summarize completes."""
        try:
            task_id = enqueue(
                "app.tasks.finalize_task",
                queue="high",
                kwargs={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id
                },
                priority=3,
                job_id=f"finalize_{job_id}"
            )
            
            # Create task record
            with get_session() as session:
                task = Task(
                    job_id=job_id,
                    name="finalize",
                    state="queued"
                )
                session.add(task)
                session.commit()
            
            logger.info(f"Enqueued finalize task {task_id} for job {job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue finalize task: {e}")
            raise
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get comprehensive job status."""
        try:
            with get_session() as session:
                job = session.query(Job).filter(Job.id == job_id).first()
                if not job:
                    raise ValueError(f"Job {job_id} not found")
                
                # Get task statuses
                tasks = session.query(Task).filter(Task.job_id == job_id).all()
                task_statuses = []
                for task in tasks:
                    task_statuses.append({
                        "name": task.name,
                        "batch_index": task.batch_index,
                        "state": task.state,
                        "attempt": task.attempt,
                        "started_at": task.started_at.isoformat() if task.started_at else None,
                        "ended_at": task.ended_at.isoformat() if task.ended_at else None,
                        "error": task.error
                    })
                
                return {
                    "jobId": str(job.id),
                    "repoId": str(job.repo_id),
                    "snapshotId": str(job.snapshot_id),
                    "phase": job.phase,
                    "pct": job.pct,
                    "error": job.error,
                    "createdAt": job.created_at.isoformat(),
                    "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
                    "tasks": task_statuses
                }
                
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            raise

# Global orchestrator instance
_orchestrator_instance: Optional[JobOrchestrator] = None

def get_orchestrator() -> JobOrchestrator:
    """Get the global job orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = JobOrchestrator()
    return _orchestrator_instance
