"""
Status management with Redis overlay on Postgres for real-time updates.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import redis
from sqlalchemy.orm import Session
from app.database import get_session, Job

logger = logging.getLogger(__name__)

class StatusError(Exception):
    """Status-related errors."""
    pass

class StatusManager:
    """Manages job status with Redis overlay on Postgres."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        logger.info(f"Connected to Redis for status management at {self.redis_url}")
    
    def _get_status_key(self, job_id: str) -> str:
        """Get Redis key for job status."""
        return f"job:{job_id}:status"
    
    def set_status(self, job_id: str, *, phase: str, pct: Optional[int] = None, 
                  message: Optional[str] = None, **fields) -> None:
        """
        Update job status in Redis with optional Postgres persistence.
        
        Args:
            job_id: Job ID
            phase: Current phase
            pct: Progress percentage (0-100)
            message: Status message
            **fields: Additional status fields
        """
        try:
            status_key = self._get_status_key(job_id)
            
            # Prepare status data
            status_data = {
                'phase': phase,
                'updatedAt': datetime.utcnow().isoformat()
            }
            
            if pct is not None:
                status_data['pct'] = pct
            
            if message is not None:
                status_data['message'] = message
            
            # Add any additional fields
            status_data.update(fields)
            
            # Update Redis
            self.redis_client.hset(status_key, mapping=status_data)
            
            # Set expiration (24 hours)
            self.redis_client.expire(status_key, 86400)
            
            # Update Postgres for persistence
            self._update_postgres_status(job_id, phase, pct, message, fields)
            
            logger.debug(f"Updated status for job {job_id}: {status_data}")
            
        except Exception as e:
            logger.error(f"Failed to update status for job {job_id}: {e}")
            raise StatusError(f"Failed to update status: {e}")
    
    def _update_postgres_status(self, job_id: str, phase: str, pct: Optional[int], 
                               message: Optional[str], fields: Dict[str, Any]) -> None:
        """Update job status in Postgres."""
        try:
            with get_session() as session:
                job = session.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.phase = phase
                    job.updated_at = datetime.utcnow()
                    
                    if pct is not None:
                        job.pct = pct
                    
                    if message is not None:
                        job.error = message
                    
                    session.commit()
                    
        except Exception as e:
            logger.warning(f"Failed to update Postgres status for job {job_id}: {e}")
            # Don't raise - Redis is the primary source of truth
    
    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get job status from Redis with Postgres fallback.
        
        Args:
            job_id: Job ID
        
        Returns:
            Status information
        """
        try:
            status_key = self._get_status_key(job_id)
            
            # Try Redis first
            redis_status = self.redis_client.hgetall(status_key)
            
            if redis_status:
                # Convert string values to appropriate types
                status = {}
                for key, value in redis_status.items():
                    if key in ['pct', 'filesDiscovered', 'filesParsed', 'importsTotal', 
                              'importsInternal', 'importsExternal', 'filesSummarized', 
                              'capabilitiesBuilt', 'warnings']:
                        try:
                            status[key] = int(value)
                        except ValueError:
                            status[key] = value
                    else:
                        status[key] = value
                
                return status
            
            # Fallback to Postgres
            return self._get_postgres_status(job_id)
            
        except Exception as e:
            logger.error(f"Failed to get status for job {job_id}: {e}")
            raise StatusError(f"Failed to get status: {e}")
    
    def _get_postgres_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status from Postgres."""
        try:
            with get_session() as session:
                job = session.query(Job).filter(Job.id == job_id).first()
                if job:
                    return {
                        'jobId': str(job.id),
                        'repoId': str(job.repo_id),
                        'snapshotId': str(job.snapshot_id),
                        'phase': job.phase,
                        'pct': job.pct,
                        'error': job.error,
                        'updatedAt': job.updated_at.isoformat() if job.updated_at else None
                    }
                else:
                    raise StatusError(f"Job {job_id} not found")
                    
        except Exception as e:
            logger.error(f"Failed to get Postgres status for job {job_id}: {e}")
            raise StatusError(f"Failed to get status from database: {e}")
    
    def clear_status(self, job_id: str) -> None:
        """
        Clear job status from Redis.
        
        Args:
            job_id: Job ID
        """
        try:
            status_key = self._get_status_key(job_id)
            self.redis_client.delete(status_key)
            logger.debug(f"Cleared status for job {job_id}")
            
        except Exception as e:
            logger.warning(f"Failed to clear status for job {job_id}: {e}")

# Global status manager instance
_status_manager: Optional[StatusManager] = None

def get_status_manager() -> StatusManager:
    """Get the global status manager instance."""
    global _status_manager
    if _status_manager is None:
        _status_manager = StatusManager()
    return _status_manager

def set_status(job_id: str, *, phase: str, pct: Optional[int] = None, 
              message: Optional[str] = None, **fields) -> None:
    """Convenience function for updating job status."""
    status_manager = get_status_manager()
    status_manager.set_status(job_id, phase=phase, pct=pct, message=message, **fields)

def get_status(job_id: str) -> Dict[str, Any]:
    """Convenience function for getting job status."""
    status_manager = get_status_manager()
    return status_manager.get_status(job_id)