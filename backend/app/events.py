"""
Event streaming for Provis job progress.
Provides SSE events for real-time status updates.
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ProvisEvent:
    """Base event class for Provis operations."""
    event_type: str
    job_id: str
    timestamp: datetime
    data: Dict[str, Any]

class EventStream:
    """Manages SSE event streams for job progress."""
    
    def __init__(self):
        self._streams: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
    
    async def create_stream(self, job_id: str) -> AsyncGenerator[str, None]:
        """Create a new SSE stream for a job."""
        async with self._lock:
            if job_id not in self._streams:
                self._streams[job_id] = asyncio.Queue()
        
        queue = self._streams[job_id]
        
        try:
            while True:
                try:
                    # Wait for events with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"Event stream cancelled for job {job_id}")
        finally:
            # Clean up stream
            async with self._lock:
                if job_id in self._streams:
                    del self._streams[job_id]
    
    async def emit_event(self, job_id: str, event_type: str, data: Dict[str, Any]):
        """Emit an event to a job's stream."""
        event = ProvisEvent(
            event_type=event_type,
            job_id=job_id,
            timestamp=datetime.now(timezone.utc),
            data=data
        )
        
        async with self._lock:
            if job_id in self._streams:
                try:
                    self._streams[job_id].put_nowait({
                        "type": event.event_type,
                        "job_id": event.job_id,
                        "timestamp": event.timestamp.isoformat(),
                        "data": event.data
                    })
                except asyncio.QueueFull:
                    logger.warning(f"Event queue full for job {job_id}, dropping event")
    
    async def emit_phase_change(self, job_id: str, phase: str, pct: int, message: Optional[str] = None):
        """Emit a phase change event."""
        await self.emit_event(job_id, "phase_changed", {
            "phase": phase,
            "progress": pct,
            "message": message
        })
    
    async def emit_progress(self, job_id: str, pct: int, message: Optional[str] = None):
        """Emit a progress update event."""
        await self.emit_event(job_id, "progress", {
            "progress": pct,
            "message": message
        })
    
    async def emit_warning(self, job_id: str, warning: str, file_path: Optional[str] = None):
        """Emit a warning event."""
        await self.emit_event(job_id, "warning", {
            "warning": warning,
            "file": file_path
        })
    
    async def emit_llm_budget(self, job_id: str, tokens_used: int, budget_remaining: int):
        """Emit an LLM budget update event."""
        await self.emit_event(job_id, "llm_budget", {
            "tokens_used": tokens_used,
            "budget_remaining": budget_remaining
        })
    
    async def emit_completion(self, job_id: str, success: bool, error: Optional[str] = None):
        """Emit a completion event."""
        await self.emit_event(job_id, "completion", {
            "success": success,
            "error": error
        })

# Global event stream instance
_event_stream = EventStream()

def get_event_stream() -> EventStream:
    """Get the global event stream instance."""
    return _event_stream

# Convenience functions
async def emit_phase_change(job_id: str, phase: str, pct: int, message: Optional[str] = None):
    """Emit a phase change event."""
    await _event_stream.emit_phase_change(job_id, phase, pct, message)

async def emit_progress(job_id: str, pct: int, message: Optional[str] = None):
    """Emit a progress update event."""
    await _event_stream.emit_progress(job_id, pct, message)

async def emit_warning(job_id: str, warning: str, file_path: Optional[str] = None):
    """Emit a warning event."""
    await _event_stream.emit_warning(job_id, warning, file_path)

async def emit_llm_budget(job_id: str, tokens_used: int, budget_remaining: int):
    """Emit an LLM budget update event."""
    await _event_stream.emit_llm_budget(job_id, tokens_used, budget_remaining)

async def emit_completion(job_id: str, success: bool, error: Optional[str] = None):
    """Emit a completion event."""
    await _event_stream.emit_completion(job_id, success, error)