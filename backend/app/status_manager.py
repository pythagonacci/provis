"""
Status manager for tracking job status and events with persistence.
Provides comprehensive status tracking and event streaming.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import logging

from .models import StatusPayload, Phase, WarningItem
from .events import event_manager

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class JobInfo:
    """Job information with comprehensive tracking."""
    job_id: str
    repo_id: str
    status: JobStatus
    phase: Phase
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    progress_percent: float = 0.0
    current_task: Optional[str] = None
    tasks_completed: int = 0
    total_tasks: int = 0
    warnings: List[WarningItem] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    repo_path: Optional[str] = None

@dataclass
class StatusEvent:
    """Status event with timestamp and data."""
    event_type: str
    job_id: str
    timestamp: float
    data: Dict[str, Any]

class StatusManager:
    """Manages job status and events with persistence."""
    
    def __init__(self, status_dir: Path):
        self.status_dir = status_dir
        self.status_dir.mkdir(exist_ok=True)
        
        # In-memory status tracking
        self.jobs: Dict[str, JobInfo] = {}
        self.events: Dict[str, List[StatusEvent]] = {}
        
        # Persistence
        self.status_file = self.status_dir / "status.json"
        self.events_file = self.status_dir / "events.json"
        
        # Load existing data
        self._load_status()
        self._load_events()
    
    def _load_status(self) -> None:
        """Load status from persistent storage."""
        if not self.status_file.exists():
            return
        
        try:
            with open(self.status_file, 'r') as f:
                data = json.load(f)
            
            for job_data in data.get("jobs", []):
                job = JobInfo(
                    job_id=job_data["job_id"],
                    repo_id=job_data["repo_id"],
                    status=JobStatus(job_data["status"]),
                    phase=Phase(job_data["phase"]),
                    created_at=job_data["created_at"],
                    started_at=job_data.get("started_at"),
                    completed_at=job_data.get("completed_at"),
                    error=job_data.get("error"),
                    progress_percent=job_data.get("progress_percent", 0.0),
                    current_task=job_data.get("current_task"),
                    tasks_completed=job_data.get("tasks_completed", 0),
                    total_tasks=job_data.get("total_tasks", 0),
                    warnings=[WarningItem(**w) for w in job_data.get("warnings", [])],
                    metrics=job_data.get("metrics", {}),
                    artifacts=job_data.get("artifacts", []),
                    repo_path=job_data.get("repo_path")
                )
                self.jobs[job.job_id] = job
                
        except Exception as e:
            logger.error(f"Failed to load status: {e}")
    
    def _load_events(self) -> None:
        """Load events from persistent storage."""
        if not self.events_file.exists():
            return
        
        try:
            with open(self.events_file, 'r') as f:
                data = json.load(f)
            
            for job_id, events_data in data.get("events", {}).items():
                events = []
                for event_data in events_data:
                    event = StatusEvent(
                        event_type=event_data["event_type"],
                        job_id=event_data["job_id"],
                        timestamp=event_data["timestamp"],
                        data=event_data["data"]
                    )
                    events.append(event)
                self.events[job_id] = events
                
        except Exception as e:
            logger.error(f"Failed to load events: {e}")
    
    def _save_status(self) -> None:
        """Save status to persistent storage."""
        try:
            data = {
                "jobs": []
            }
            
            for job in self.jobs.values():
                job_data = {
                    "job_id": job.job_id,
                    "repo_id": job.repo_id,
                    "status": job.status.value,
                    "phase": job.phase.value,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error": job.error,
                    "progress_percent": job.progress_percent,
                    "current_task": job.current_task,
                    "tasks_completed": job.tasks_completed,
                    "total_tasks": job.total_tasks,
                    "warnings": [w.model_dump() for w in job.warnings],
                    "metrics": job.metrics,
                    "artifacts": job.artifacts,
                    "repo_path": job.repo_path
                }
                data["jobs"].append(job_data)
            
            with open(self.status_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save status: {e}")
    
    def _save_events(self) -> None:
        """Save events to persistent storage."""
        try:
            data = {
                "events": {}
            }
            
            for job_id, events in self.events.items():
                events_data = []
                for event in events:
                    event_data = {
                        "event_type": event.event_type,
                        "job_id": event.job_id,
                        "timestamp": event.timestamp,
                        "data": event.data
                    }
                    events_data.append(event_data)
                data["events"][job_id] = events_data
            
            with open(self.events_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save events: {e}")
    
    def create_job(self, job_id: str, repo_id: str, repo_path: Optional[str] = None) -> JobInfo:
        """Create a new job."""
        job = JobInfo(
            job_id=job_id,
            repo_id=repo_id,
            status=JobStatus.QUEUED,
            phase=Phase.QUEUED,
            created_at=time.time(),
            repo_path=repo_path
        )
        
        self.jobs[job_id] = job
        self.events[job_id] = []
        
        # Record creation event
        self._record_event(job_id, "job_created", {
            "repo_id": repo_id,
            "repo_path": repo_path
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
        
        logger.info(f"Created job: {job_id}")
        return job
    
    def update_job_status(self, job_id: str, status: JobStatus, error: Optional[str] = None) -> None:
        """Update job status."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        old_status = job.status
        
        job.status = status
        
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = time.time()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = time.time()
        
        if error:
            job.error = error
        
        # Record status change event
        self._record_event(job_id, "status_changed", {
            "old_status": old_status.value,
            "new_status": status.value,
            "error": error
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
        
        logger.info(f"Updated job {job_id} status: {old_status.value} -> {status.value}")
    
    def update_job_phase(self, job_id: str, phase: Phase) -> None:
        """Update job phase."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        old_phase = job.phase
        
        job.phase = phase
        
        # Record phase change event
        self._record_event(job_id, "phase_changed", {
            "old_phase": old_phase.value,
            "new_phase": phase.value
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
        
        logger.info(f"Updated job {job_id} phase: {old_phase.value} -> {phase.value}")
    
    def update_job_progress(self, job_id: str, progress_percent: float, current_task: Optional[str] = None) -> None:
        """Update job progress."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        old_progress = job.progress_percent
        
        job.progress_percent = progress_percent
        if current_task:
            job.current_task = current_task
        
        # Record progress event (only if significant change)
        if abs(progress_percent - old_progress) >= 5.0:
            self._record_event(job_id, "progress", {
                "progress_percent": progress_percent,
                "current_task": current_task
            })
            
            # Save to persistent storage
            self._save_status()
            self._save_events()
    
    def update_job_tasks(self, job_id: str, tasks_completed: int, total_tasks: int) -> None:
        """Update job task counts."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        job.tasks_completed = tasks_completed
        job.total_tasks = total_tasks
        
        # Update progress percentage
        if total_tasks > 0:
            job.progress_percent = (tasks_completed / total_tasks) * 100
        
        # Record task update event
        self._record_event(job_id, "tasks_updated", {
            "tasks_completed": tasks_completed,
            "total_tasks": total_tasks,
            "progress_percent": job.progress_percent
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
    
    def add_job_warning(self, job_id: str, warning: WarningItem) -> None:
        """Add a warning to a job."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        job.warnings.append(warning)
        
        # Record warning event
        self._record_event(job_id, "warning", {
            "warning": warning.model_dump()
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
        
        logger.warning(f"Added warning to job {job_id}: {warning.message}")
    
    def update_job_metrics(self, job_id: str, metrics: Dict[str, Any]) -> None:
        """Update job metrics."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        job.metrics.update(metrics)
        
        # Record metrics event
        self._record_event(job_id, "metrics_updated", {
            "metrics": metrics
        })
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
    
    def add_job_artifact(self, job_id: str, artifact: str) -> None:
        """Add an artifact to a job."""
        if job_id not in self.jobs:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job = self.jobs[job_id]
        if artifact not in job.artifacts:
            job.artifacts.append(artifact)
            
            # Record artifact event
            self._record_event(job_id, "artifact_created", {
                "artifact": artifact
            })
            
            # Save to persistent storage
            self._save_status()
            self._save_events()
            
            logger.info(f"Added artifact to job {job_id}: {artifact}")
    
    def _record_event(self, job_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Record an event for a job."""
        event = StatusEvent(
            event_type=event_type,
            job_id=job_id,
            timestamp=time.time(),
            data=data
        )
        
        if job_id not in self.events:
            self.events[job_id] = []
        
        self.events[job_id].append(event)
        
        # Limit events per job to prevent memory issues
        max_events = 1000
        if len(self.events[job_id]) > max_events:
            self.events[job_id] = self.events[job_id][-max_events:]
    
    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """Get job information."""
        return self.jobs.get(job_id)
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status as dictionary."""
        job = self.jobs.get(job_id)
        if not job:
            return None
        
        return {
            "job_id": job.job_id,
            "repo_id": job.repo_id,
            "status": job.status.value,
            "phase": job.phase.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error": job.error,
            "progress_percent": job.progress_percent,
            "current_task": job.current_task,
            "tasks_completed": job.tasks_completed,
            "total_tasks": job.total_tasks,
            "warnings": [w.model_dump() for w in job.warnings],
            "metrics": job.metrics,
            "artifacts": job.artifacts,
            "repo_path": job.repo_path
        }
    
    def get_job_events(self, job_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get events for a job."""
        events = self.events.get(job_id, [])
        
        if limit:
            events = events[-limit:]
        
        return [
            {
                "event_type": event.event_type,
                "job_id": event.job_id,
                "timestamp": event.timestamp,
                "data": event.data
            }
            for event in events
        ]
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs."""
        return [self.get_job_status(job_id) for job_id in self.jobs.keys()]
    
    def get_jobs_by_status(self, status: JobStatus) -> List[Dict[str, Any]]:
        """Get jobs by status."""
        return [
            self.get_job_status(job_id)
            for job_id, job in self.jobs.items()
            if job.status == status
        ]
    
    def get_jobs_by_repo(self, repo_id: str) -> List[Dict[str, Any]]:
        """Get jobs by repository ID."""
        return [
            self.get_job_status(job_id)
            for job_id, job in self.jobs.items()
            if job.repo_id == repo_id
        ]
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its events."""
        if job_id not in self.jobs:
            return False
        
        # Remove job
        del self.jobs[job_id]
        
        # Remove events
        if job_id in self.events:
            del self.events[job_id]
        
        # Save to persistent storage
        self._save_status()
        self._save_events()
        
        logger.info(f"Deleted job: {job_id}")
        return True
    
    def cleanup_old_jobs(self, max_age_seconds: int = 86400) -> int:
        """Clean up old completed jobs."""
        current_time = time.time()
        jobs_to_remove = []
        
        for job_id, job in self.jobs.items():
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                age = current_time - job.created_at
                if age > max_age_seconds:
                    jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            self.delete_job(job_id)
        
        logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
        return len(jobs_to_remove)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get status summary."""
        total_jobs = len(self.jobs)
        status_counts = {}
        
        for status in JobStatus:
            status_counts[status.value] = len([
                job for job in self.jobs.values()
                if job.status == status
            ])
        
        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "oldest_job": min(job.created_at for job in self.jobs.values()) if self.jobs else None,
            "newest_job": max(job.created_at for job in self.jobs.values()) if self.jobs else None
        }
    
    async def stream_job_events(self, job_id: str) -> AsyncGenerator[str, None]:
        """Stream events for a job."""
        # Get existing events
        existing_events = self.get_job_events(job_id)
        for event in existing_events:
            yield json.dumps(event)
        
        # Stream new events
        async for event in event_manager.subscribe(job_id):
            yield event
