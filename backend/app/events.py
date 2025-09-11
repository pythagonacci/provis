"""
Event streaming system with Redis streams and Postgres persistence.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import redis
from sqlalchemy.orm import Session
from app.database import get_session, Event

logger = logging.getLogger(__name__)

class EventError(Exception):
    """Event-related errors."""
    pass

class EventManager:
    """Manages job events with Redis streams and Postgres persistence."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        
        logger.info(f"Connected to Redis for event management at {self.redis_url}")
    
    def _get_stream_key(self, job_id: str) -> str:
        """Get Redis stream key for job events."""
        return f"job:{job_id}:events"
    
    def append_event(self, job_id: str, *, type_: str, payload: Dict[str, Any] = None) -> None:
        """
        Append an event to the job's event stream.
        
        Args:
            job_id: Job ID
            type_: Event type
            payload: Event payload data
        """
        try:
            stream_key = self._get_stream_key(job_id)
            
            # Prepare event data
            event_data = {
                'type': type_,
                'timestamp': datetime.utcnow().isoformat(),
                'jobId': job_id
            }
            
            if payload:
                event_data['payload'] = json.dumps(payload)
            
            # Add to Redis stream
            message_id = self.redis_client.xadd(stream_key, event_data)
            
            # Persist to Postgres
            self._persist_event_to_postgres(job_id, type_, payload)
            
            logger.debug(f"Added event {type_} for job {job_id}: {message_id}")
            
        except Exception as e:
            logger.error(f"Failed to append event for job {job_id}: {e}")
            raise EventError(f"Failed to append event: {e}")
    
    def _persist_event_to_postgres(self, job_id: str, type_: str, payload: Dict[str, Any] = None) -> None:
        """Persist event to Postgres for long-term storage."""
        try:
            with get_session() as session:
                event = Event(
                    job_id=job_id,
                    type=type_,
                    payload=payload
                )
                session.add(event)
                session.commit()
                
        except Exception as e:
            logger.warning(f"Failed to persist event to Postgres for job {job_id}: {e}")
            # Don't raise - Redis is the primary source of truth
    
    def get_events(self, job_id: str, start_id: str = "0", count: int = 100) -> list[Dict[str, Any]]:
        """
        Get events from the job's event stream.
        
        Args:
            job_id: Job ID
            start_id: Starting message ID (default: "0" for beginning)
            count: Maximum number of events to return
        
        Returns:
            List of events
        """
        try:
            stream_key = self._get_stream_key(job_id)
            
            # Read from Redis stream
            messages = self.redis_client.xrange(stream_key, start_id, count=count)
            
            events = []
            for message_id, fields in messages:
                event = {
                    'id': message_id,
                    'type': fields.get('type'),
                    'timestamp': fields.get('timestamp'),
                    'jobId': fields.get('jobId')
                }
                
                # Parse payload if present
                if 'payload' in fields:
                    try:
                        event['payload'] = json.loads(fields['payload'])
                    except json.JSONDecodeError:
                        event['payload'] = fields['payload']
                
                events.append(event)
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to get events for job {job_id}: {e}")
            raise EventError(f"Failed to get events: {e}")
    
    def stream_events(self, job_id: str, last_id: str = "$") -> list[Dict[str, Any]]:
        """
        Stream new events from the job's event stream (for SSE).
        
        Args:
            job_id: Job ID
            last_id: Last message ID seen (default: "$" for new messages)
        
        Returns:
            List of new events
        """
        try:
            stream_key = self._get_stream_key(job_id)
            
            # Block for new messages (timeout: 10 seconds)
            messages = self.redis_client.xread({stream_key: last_id}, block=10000, count=10)
            
            events = []
            if messages:
                for stream, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        event = {
                            'id': message_id,
                            'type': fields.get('type'),
                            'timestamp': fields.get('timestamp'),
                            'jobId': fields.get('jobId')
                        }
                        
                        # Parse payload if present
                        if 'payload' in fields:
                            try:
                                event['payload'] = json.loads(fields['payload'])
                            except json.JSONDecodeError:
                                event['payload'] = fields['payload']
                        
                        events.append(event)
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to stream events for job {job_id}: {e}")
            raise EventError(f"Failed to stream events: {e}")
    
    def clear_events(self, job_id: str) -> None:
        """
        Clear events for a job (cleanup after completion).
        
        Args:
            job_id: Job ID
        """
        try:
            stream_key = self._get_stream_key(job_id)
            self.redis_client.delete(stream_key)
            logger.debug(f"Cleared events for job {job_id}")
            
        except Exception as e:
            logger.warning(f"Failed to clear events for job {job_id}: {e}")

# Global event manager instance
_event_manager: Optional[EventManager] = None

def get_event_manager() -> EventManager:
    """Get the global event manager instance."""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager

def append_event(job_id: str, *, type_: str, payload: Dict[str, Any] = None) -> None:
    """Convenience function for appending events."""
    event_manager = get_event_manager()
    event_manager.append_event(job_id, type_=type_, payload=payload)

# Common event types and helpers
def on_phase_change(job_id: str, phase: str, pct: int = None):
    """Emit phase change event."""
    payload = {'phase': phase}
    if pct is not None:
        payload['pct'] = pct
    append_event(job_id, type_='phase', payload=payload)

def on_pct_update(job_id: str, pct: int, message: str = None):
    """Emit progress update event."""
    payload = {'pct': pct}
    if message:
        payload['message'] = message
    append_event(job_id, type_='progress', payload=payload)

def on_artifact_ready(job_id: str, kind: str, uri: str, version: int, bytes: int):
    """Emit artifact ready event."""
    payload = {
        'kind': kind,
        'uri': uri,
        'version': version,
        'bytes': bytes
    }
    append_event(job_id, type_='artifact_ready', payload=payload)

def on_warning(job_id: str, message: str, code: str = None, file_path: str = None):
    """Emit warning event."""
    payload = {'message': message}
    if code:
        payload['code'] = code
    if file_path:
        payload['filePath'] = file_path
    append_event(job_id, type_='warning', payload=payload)

def on_error(job_id: str, error: str, phase: str = None):
    """Emit error event."""
    payload = {'error': error}
    if phase:
        payload['phase'] = phase
    append_event(job_id, type_='error', payload=payload)

def on_done(job_id: str, summary: Dict[str, Any] = None):
    """Emit job completion event."""
    payload = summary or {}
    append_event(job_id, type_='done', payload=payload)
