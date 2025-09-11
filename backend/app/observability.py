"""
Observability system with structured logging and Prometheus metrics.
"""
import os
import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager
from functools import wraps

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes for when prometheus_client is not available
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def time(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collects and exposes Prometheus metrics."""
    
    def __init__(self):
        if not PROMETHEUS_AVAILABLE:
            logger.warning("prometheus_client not available, metrics will be disabled")
            return
        
        # Job metrics
        self.jobs_total = Counter(
            'provis_jobs_total',
            'Total number of jobs',
            ['phase', 'status']
        )
        
        self.job_duration_ms = Histogram(
            'provis_job_duration_ms',
            'Job duration in milliseconds',
            ['phase'],
            buckets=[100, 500, 1000, 5000, 10000, 30000, 60000, 300000, 600000, 1800000]
        )
        
        # Task metrics
        self.tasks_total = Counter(
            'provis_tasks_total',
            'Total number of tasks',
            ['name', 'state']
        )
        
        self.task_duration_ms = Histogram(
            'provis_task_duration_ms',
            'Task duration in milliseconds',
            ['name'],
            buckets=[10, 50, 100, 500, 1000, 5000, 10000, 30000, 60000, 300000]
        )
        
        # File parsing metrics
        self.files_parsed_total = Counter(
            'provis_files_parsed_total',
            'Total number of files parsed',
            ['language', 'status']
        )
        
        self.node_parse_ms = Histogram(
            'provis_node_parse_ms',
            'Node.js subprocess parse duration in milliseconds',
            buckets=[100, 500, 1000, 5000, 10000, 20000, 30000]
        )
        
        # Import metrics
        self.imports_total = Counter(
            'provis_imports_total',
            'Total number of imports processed',
            ['type']  # internal, external
        )
        
        # Artifact metrics
        self.artifacts_created_total = Counter(
            'provis_artifacts_created_total',
            'Total number of artifacts created',
            ['kind']
        )
        
        self.artifact_bytes = Histogram(
            'provis_artifact_bytes',
            'Artifact size in bytes',
            ['kind'],
            buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600, 1073741824]
        )
        
        # Queue metrics
        self.queue_size = Gauge(
            'provis_queue_size',
            'Current queue size',
            ['queue_name']
        )
        
        # Error metrics
        self.errors_total = Counter(
            'provis_errors_total',
            'Total number of errors',
            ['component', 'error_type']
        )
        
        logger.info("Initialized Prometheus metrics collector")
    
    def record_job_start(self, job_id: str, phase: str):
        """Record job start."""
        if PROMETHEUS_AVAILABLE:
            self.jobs_total.labels(phase=phase, status='started').inc()
    
    def record_job_completion(self, job_id: str, phase: str, duration_ms: float, success: bool):
        """Record job completion."""
        if PROMETHEUS_AVAILABLE:
            status = 'completed' if success else 'failed'
            self.jobs_total.labels(phase=phase, status=status).inc()
            self.job_duration_ms.labels(phase=phase).observe(duration_ms)
    
    def record_task_start(self, task_name: str):
        """Record task start."""
        if PROMETHEUS_AVAILABLE:
            self.tasks_total.labels(name=task_name, state='started').inc()
    
    def record_task_completion(self, task_name: str, duration_ms: float, success: bool):
        """Record task completion."""
        if PROMETHEUS_AVAILABLE:
            state = 'completed' if success else 'failed'
            self.tasks_total.labels(name=task_name, state=state).inc()
            self.task_duration_ms.labels(name=task_name).observe(duration_ms)
    
    def record_file_parsed(self, language: str, success: bool):
        """Record file parsing."""
        if PROMETHEUS_AVAILABLE:
            status = 'success' if success else 'failed'
            self.files_parsed_total.labels(language=language, status=status).inc()
    
    def record_node_parse(self, duration_ms: float):
        """Record Node.js subprocess parse duration."""
        if PROMETHEUS_AVAILABLE:
            self.node_parse_ms.observe(duration_ms)
    
    def record_imports(self, internal_count: int, external_count: int):
        """Record import processing."""
        if PROMETHEUS_AVAILABLE:
            self.imports_total.labels(type='internal').inc(internal_count)
            self.imports_total.labels(type='external').inc(external_count)
    
    def record_artifact_created(self, kind: str, bytes_size: int):
        """Record artifact creation."""
        if PROMETHEUS_AVAILABLE:
            self.artifacts_created_total.labels(kind=kind).inc()
            self.artifact_bytes.labels(kind=kind).observe(bytes_size)
    
    def update_queue_size(self, queue_name: str, size: int):
        """Update queue size."""
        if PROMETHEUS_AVAILABLE:
            self.queue_size.labels(queue_name=queue_name).set(size)
    
    def record_error(self, component: str, error_type: str):
        """Record error occurrence."""
        if PROMETHEUS_AVAILABLE:
            self.errors_total.labels(component=component, error_type=error_type).inc()

# Global metrics collector
_metrics_collector: Optional[MetricsCollector] = None

def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector

class StructuredLogger:
    """Provides structured logging with consistent format."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up structured logging configuration."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _log_structured(self, level: str, message: str, **kwargs):
        """Log with structured data."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message,
            **kwargs
        }
        
        if level == 'INFO':
            self.logger.info(json.dumps(log_data))
        elif level == 'WARNING':
            self.logger.warning(json.dumps(log_data))
        elif level == 'ERROR':
            self.logger.error(json.dumps(log_data))
        elif level == 'DEBUG':
            self.logger.debug(json.dumps(log_data))
    
    def info(self, message: str, **kwargs):
        """Log info message with structured data."""
        self._log_structured('INFO', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured data."""
        self._log_structured('WARNING', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with structured data."""
        self._log_structured('ERROR', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured data."""
        self._log_structured('DEBUG', message, **kwargs)

def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)

# Decorators for automatic metrics collection
def track_job_metrics(phase: str):
    """Decorator to track job metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            start_time = time.time()
            
            # Extract job_id from kwargs if available
            job_id = kwargs.get('job_id', 'unknown')
            
            try:
                metrics.record_job_start(job_id, phase)
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                metrics.record_job_completion(job_id, phase, duration_ms, True)
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                metrics.record_job_completion(job_id, phase, duration_ms, False)
                metrics.record_error('job', type(e).__name__)
                raise
        return wrapper
    return decorator

def track_task_metrics(task_name: str):
    """Decorator to track task metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            start_time = time.time()
            
            try:
                metrics.record_task_start(task_name)
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                metrics.record_task_completion(task_name, duration_ms, True)
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                metrics.record_task_completion(task_name, duration_ms, False)
                metrics.record_error('task', type(e).__name__)
                raise
        return wrapper
    return decorator

@contextmanager
def track_node_parse():
    """Context manager to track Node.js subprocess parse duration."""
    metrics = get_metrics_collector()
    start_time = time.time()
    
    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        metrics.record_node_parse(duration_ms)

def get_metrics_endpoint():
    """Get Prometheus metrics endpoint handler."""
    if not PROMETHEUS_AVAILABLE:
        return lambda: "prometheus_client not available"
    
    def metrics_handler():
        return generate_latest()
    
    return metrics_handler

def get_metrics_content_type():
    """Get Prometheus metrics content type."""
    return CONTENT_TYPE_LATEST if PROMETHEUS_AVAILABLE else "text/plain"
