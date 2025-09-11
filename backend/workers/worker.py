"""
Worker process for executing tasks with resource limits and monitoring.
"""
import os
import sys
import json
import logging
import signal
import time
from typing import Dict, Any
from datetime import datetime
import redis
from rq import Worker, Connection
from rq.worker import WorkerStatus

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.queue import get_queue
from app.limits import get_limits

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('worker.log')
    ]
)

logger = logging.getLogger(__name__)

class ProvisWorker:
    """Worker process with resource limits and monitoring."""
    
    def __init__(self, queues: list[str] = None):
        self.queues = queues or ['high', 'normal', 'low']
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        self.limits = get_limits()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.shutdown_requested = False
        
        logger.info(f"Initialized worker for queues: {self.queues}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def _setup_resource_limits(self):
        """Set up OS-level resource limits."""
        try:
            import resource
            
            # Set memory limit (512MB)
            memory_limit = 512 * 1024 * 1024  # 512MB in bytes
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
            
            # Set CPU time limit (1 hour)
            cpu_limit = 3600  # 1 hour in seconds
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
            
            logger.info(f"Set resource limits: memory={memory_limit}, cpu={cpu_limit}")
            
        except ImportError:
            logger.warning("resource module not available, skipping resource limits")
        except Exception as e:
            logger.warning(f"Failed to set resource limits: {e}")
    
    def _log_task_start(self, job):
        """Log task start with structured data."""
        meta = job.meta or {}
        logger.info(json.dumps({
            'event': 'task_start',
            'job_id': job.id,
            'task_name': job.func_name,
            'repo_id': meta.get('job_id'),
            'phase': meta.get('phase', 'unknown'),
            'attempt': job.retries_left + 1,
            'started_at': datetime.utcnow().isoformat()
        }))
    
    def _log_task_end(self, job, success: bool, duration_ms: int, error: str = None):
        """Log task completion with structured data."""
        meta = job.meta or {}
        log_data = {
            'event': 'task_end',
            'job_id': job.id,
            'task_name': job.func_name,
            'repo_id': meta.get('job_id'),
            'phase': meta.get('phase', 'unknown'),
            'success': success,
            'duration_ms': duration_ms,
            'ended_at': datetime.utcnow().isoformat()
        }
        
        if error:
            log_data['error'] = error
        
        if success:
            logger.info(json.dumps(log_data))
        else:
            logger.error(json.dumps(log_data))
    
    def _execute_with_limits(self, job):
        """Execute a job with resource limits and monitoring."""
        start_time = time.time()
        success = False
        error = None
        
        try:
            # Acquire necessary tokens
            with self.limits.node_subprocess_token() if 'parse' in job.func_name else self.limits.dummy_token():
                # Execute the job
                result = job.perform()
                success = True
                return result
                
        except Exception as e:
            error = str(e)
            logger.error(f"Task {job.id} failed: {e}")
            raise
        finally:
            # Log completion
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_task_end(job, success, duration_ms, error)
    
    def run(self):
        """Run the worker process."""
        logger.info("Starting Provis worker...")
        
        # Set up resource limits
        self._setup_resource_limits()
        
        # Create worker
        with Connection(self.redis_client):
            worker = Worker(self.queues, name=f"provis-worker-{os.getpid()}")
            
            # Override job execution to add monitoring
            original_execute_job = worker.execute_job
            
            def monitored_execute_job(job):
                self._log_task_start(job)
                return self._execute_with_limits(job)
            
            worker.execute_job = monitored_execute_job
            
            logger.info(f"Worker {worker.name} ready, listening on queues: {self.queues}")
            
            try:
                # Start working
                worker.work(with_scheduler=True)
            except KeyboardInterrupt:
                logger.info("Worker interrupted by user")
            except Exception as e:
                logger.error(f"Worker error: {e}")
                raise
            finally:
                logger.info("Worker shutting down...")

def main():
    """Main entry point for the worker."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Provis Worker')
    parser.add_argument('--queues', nargs='+', default=['high', 'normal', 'low'],
                       help='Queues to listen on')
    parser.add_argument('--name', help='Worker name')
    
    args = parser.parse_args()
    
    # Set worker name if provided
    if args.name:
        os.environ['RQ_WORKER_NAME'] = args.name
    
    # Create and run worker
    worker = ProvisWorker(queues=args.queues)
    worker.run()

if __name__ == '__main__':
    main()
