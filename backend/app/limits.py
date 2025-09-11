"""
Resource limits and token buckets for Node subprocesses and LLM calls.
"""
import os
import time
import logging
import threading
from typing import Dict, Any, Optional
from contextlib import contextmanager
import redis

logger = logging.getLogger(__name__)

class LimitsError(Exception):
    """Limits-related errors."""
    pass

class TokenBucket:
    """Token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float, redis_client: redis.Redis, key: str):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.redis_client = redis_client
        self.key = key
        self.lock = threading.Lock()
    
    def _get_tokens(self) -> float:
        """Get current token count from Redis."""
        try:
            data = self.redis_client.hgetall(self.key)
            if not data:
                return self.capacity
            
            tokens = float(data.get('tokens', self.capacity))
            last_refill = float(data.get('last_refill', time.time()))
            
            # Calculate tokens to add based on time elapsed
            now = time.time()
            time_elapsed = now - last_refill
            tokens_to_add = time_elapsed * self.refill_rate
            
            # Update tokens (don't exceed capacity)
            new_tokens = min(self.capacity, tokens + tokens_to_add)
            
            # Update Redis
            self.redis_client.hset(self.key, mapping={
                'tokens': new_tokens,
                'last_refill': now
            })
            
            return new_tokens
            
        except Exception as e:
            logger.warning(f"Failed to get tokens from Redis: {e}")
            return self.capacity
    
    def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        Acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait (None for no timeout)
        
        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                current_tokens = self._get_tokens()
                
                if current_tokens >= tokens:
                    # We have enough tokens
                    new_tokens = current_tokens - tokens
                    self.redis_client.hset(self.key, 'tokens', new_tokens)
                    return True
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
            
            # Wait a bit before trying again
            time.sleep(0.1)
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting."""
        return self.acquire(tokens, timeout=0)

class ResourceLimits:
    """Manages resource limits and token buckets."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        # Node subprocess limits
        self.node_concurrency = int(os.getenv("NODE_SUBPROC_CONCURRENCY", "2"))
        self.node_file_timeout = int(os.getenv("NODE_FILE_TIMEOUT_S", "20"))
        self.node_batch_timeout = int(os.getenv("NODE_BATCH_TIMEOUT_S", "120"))
        
        # LLM limits
        self.llm_tpm = int(os.getenv("LLM_TPM", "10000"))  # tokens per minute
        self.llm_rpm = int(os.getenv("LLM_RPM", "100"))    # requests per minute
        
        # Create token buckets
        self.node_bucket = TokenBucket(
            capacity=self.node_concurrency,
            refill_rate=0.1,  # Refill 1 token every 10 seconds
            redis_client=self.redis_client,
            key="limits:node_subprocess"
        )
        
        self.llm_tpm_bucket = TokenBucket(
            capacity=self.llm_tpm,
            refill_rate=self.llm_tpm / 60.0,  # Refill at TPM rate
            redis_client=self.redis_client,
            key="limits:llm_tpm"
        )
        
        self.llm_rpm_bucket = TokenBucket(
            capacity=self.llm_rpm,
            refill_rate=self.llm_rpm / 60.0,  # Refill at RPM rate
            redis_client=self.redis_client,
            key="limits:llm_rpm"
        )
        
        logger.info(f"Initialized resource limits: node_concurrency={self.node_concurrency}, "
                   f"llm_tpm={self.llm_tpm}, llm_rpm={self.llm_rpm}")
    
    @contextmanager
    def node_subprocess_token(self, timeout: float = 30.0):
        """Context manager for acquiring Node subprocess token."""
        if not self.node_bucket.acquire(timeout=timeout):
            raise LimitsError("Failed to acquire Node subprocess token within timeout")
        
        try:
            yield
        finally:
            # Token is automatically released when the bucket refills
            pass
    
    @contextmanager
    def llm_tokens(self, tokens: int, timeout: float = 60.0):
        """Context manager for acquiring LLM tokens."""
        if not self.llm_tpm_bucket.acquire(tokens, timeout=timeout):
            raise LimitsError("Failed to acquire LLM tokens within timeout")
        
        try:
            yield
        finally:
            # Tokens are automatically released when the bucket refills
            pass
    
    @contextmanager
    def llm_request(self, timeout: float = 60.0):
        """Context manager for acquiring LLM request token."""
        if not self.llm_rpm_bucket.acquire(timeout=timeout):
            raise LimitsError("Failed to acquire LLM request token within timeout")
        
        try:
            yield
        finally:
            # Token is automatically released when the bucket refills
            pass
    
    @contextmanager
    def dummy_token(self):
        """Dummy context manager for tasks that don't need tokens."""
        yield
    
    def get_limits_status(self) -> Dict[str, Any]:
        """Get current status of all limits."""
        try:
            return {
                'node_subprocess': {
                    'capacity': self.node_concurrency,
                    'available': self.node_bucket._get_tokens(),
                    'file_timeout': self.node_file_timeout,
                    'batch_timeout': self.node_batch_timeout
                },
                'llm_tpm': {
                    'capacity': self.llm_tpm,
                    'available': self.llm_tpm_bucket._get_tokens()
                },
                'llm_rpm': {
                    'capacity': self.llm_rpm,
                    'available': self.llm_rpm_bucket._get_tokens()
                }
            }
        except Exception as e:
            logger.error(f"Failed to get limits status: {e}")
            return {}

# Global limits instance
_limits_instance: Optional[ResourceLimits] = None

def get_limits() -> ResourceLimits:
    """Get the global limits instance."""
    global _limits_instance
    if _limits_instance is None:
        _limits_instance = ResourceLimits()
    return _limits_instance
