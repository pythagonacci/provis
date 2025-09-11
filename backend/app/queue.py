"""
Queue management for RQ (Redis Queue) with task enqueueing and monitoring.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import redis
from rq import Queue, Worker, Connection
from rq.job import Job
from rq.exceptions import NoSuchJobError
from rq.retry import Retry

logger = logging.getLogger(__name__)

class QueueError(Exception):
    """Queue-related errors."""
    pass

class TaskQueue:
    """Manages task queues and job enqueueing."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        # Create queues for different priorities
        self.high_priority_queue = Queue('high', connection=self.redis_client)
        self.normal_priority_queue = Queue('normal', connection=self.redis_client)
        self.low_priority_queue = Queue('low', connection=self.redis_client)
        
        # Map priority levels to queues
        self.queues = {
            3: self.high_priority_queue,    # High priority
            2: self.high_priority_queue,    # High priority
            1: self.normal_priority_queue,  # Normal priority
            0: self.low_priority_queue,     # Low priority
            -1: self.low_priority_queue,    # Low priority
        }
        
        logger.info(f"Connected to Redis at {self.redis_url}")
    
    def enqueue(self, fn_path: str, *, queue: str = 'normal', kwargs: Dict[str, Any], 
                retries: int = 2, priority: int = 1, job_id: Optional[str] = None,
                timeout: int = 3600, retry_policy: Optional[Retry] = None) -> str:
        """
        Enqueue a task for execution.
        
        Args:
            fn_path: Path to the function (e.g., 'app.tasks.ingest_task')
            queue: Queue name ('high', 'normal', 'low')
            kwargs: Function arguments (must be JSON serializable)
            retries: Number of retry attempts
            priority: Priority level (3=high, 1=normal, 0=low)
            job_id: Optional custom job ID
            timeout: Job timeout in seconds
        
        Returns:
            Task ID
        """
        try:
            # Select queue based on priority
            selected_queue = self.queues.get(priority, self.normal_priority_queue)
            
            # Validate kwargs are JSON serializable
            json.dumps(kwargs)
            
            # Use custom retry policy if provided, otherwise use default
            retry_config = retry_policy if retry_policy else retries
            
            # Enqueue the job
            job = selected_queue.enqueue(
                fn_path,
                kwargs=kwargs,
                retry=retry_config,
                job_id=job_id,
                timeout=timeout,
                job_timeout=timeout,
                result_ttl=86400,  # Keep results for 24 hours
                failure_ttl=86400,  # Keep failures for 24 hours
                meta={
                    'job_id': kwargs.get('job_id'),
                    'phase': kwargs.get('phase', 'unknown'),
                    'enqueued_at': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Enqueued task {fn_path} with ID {job.id}")
            return job.id
            
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize task arguments: {e}")
            raise QueueError(f"Invalid task arguments: {e}")
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            raise QueueError(f"Failed to enqueue task: {e}")
    
    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a job.
        
        Args:
            task_id: Task ID
        
        Returns:
            Job status information
        """
        try:
            # Try to find the job in any queue
            job = None
            for queue in [self.high_priority_queue, self.normal_priority_queue, self.low_priority_queue]:
                try:
                    job = queue.fetch_job(task_id)
                    if job:
                        break
                except NoSuchJobError:
                    continue
            
            if not job:
                raise QueueError(f"Job {task_id} not found")
            
            return {
                'id': job.id,
                'status': job.get_status(),
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'ended_at': job.ended_at.isoformat() if job.ended_at else None,
                'result': job.result,
                'exc_info': job.exc_info,
                'meta': job.meta,
                'timeout': job.timeout
            }
            
        except Exception as e:
            logger.error(f"Failed to get job status for {task_id}: {e}")
            raise QueueError(f"Failed to get job status: {e}")
    
    def cancel_job(self, task_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if cancelled, False if not found
        """
        try:
            # Try to find and cancel the job in any queue
            for queue in [self.high_priority_queue, self.normal_priority_queue, self.low_priority_queue]:
                try:
                    job = queue.fetch_job(task_id)
                    if job and job.get_status() in ['queued', 'started']:
                        job.cancel()
                        logger.info(f"Cancelled job {task_id}")
                        return True
                except NoSuchJobError:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to cancel job {task_id}: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all queues.
        
        Returns:
            Queue statistics
        """
        try:
            stats = {}
            
            for name, queue in [
                ('high', self.high_priority_queue),
                ('normal', self.normal_priority_queue),
                ('low', self.low_priority_queue)
            ]:
                stats[name] = {
                    'queued': len(queue),
                    'started': len(queue.started_job_registry),
                    'finished': len(queue.finished_job_registry),
                    'failed': len(queue.failed_job_registry),
                    'scheduled': len(queue.scheduled_job_registry)
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}

# Global queue instance
_queue_instance: Optional[TaskQueue] = None

def get_queue() -> TaskQueue:
    """Get the global queue instance."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = TaskQueue()
    return _queue_instance

def enqueue(fn_path: str, *, queue: str = 'normal', kwargs: Dict[str, Any], 
           retries: int = 2, priority: int = 1, job_id: Optional[str] = None) -> str:
    """Convenience function for enqueueing tasks."""
    task_queue = get_queue()
    return task_queue.enqueue(fn_path, queue=queue, kwargs=kwargs, 
                            retries=retries, priority=priority, job_id=job_id)
