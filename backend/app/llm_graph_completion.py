"""
LLM layer for graph completion and enhancement.
Handles route completion, job completion, call graph completion, and schema inference.
"""
import json
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
import logging

from .config import settings
from .models import GraphEdge, RouteModel, EvidenceSpan, WarningItem
from .observability import record_llm_call, record_detector_hit
from .events import get_event_stream

logger = logging.getLogger(__name__)

@dataclass
class LLMCompletionRequest:
    """Request for LLM completion."""
    prompt: str
    context: Dict[str, Any]
    expected_schema: Dict[str, Any]
    max_tokens: int = 1000
    temperature: float = 0.0

@dataclass
class LLMCompletionResponse:
    """Response from LLM completion."""
    content: Dict[str, Any]
    usage: Dict[str, int]
    cached: bool = False
    error: Optional[str] = None

class LLMClient:
    """Client for LLM interactions with caching and token budgeting."""
    
    def __init__(self):
        self.cache: Dict[str, LLMCompletionResponse] = {}
        self.token_budget = settings.LLM_PER_REPO_TOKEN_BUDGET
        self.used_tokens = 0
        self.call_count = 0
        self.error_count = 0
    
    async def complete(self, request: LLMCompletionRequest, job_id: Optional[str] = None) -> LLMCompletionResponse:
        """Complete a request using LLM with caching and budgeting."""
        # Check cache first
        cache_key = self._generate_cache_key(request)
        if cache_key in self.cache:
            cached_response = self.cache[cache_key]
            cached_response.cached = True
            record_llm_call("completion", settings.LLM_MODEL, "cache_hit", 0, 0, 0, True)
            return cached_response
        
        # Check token budget
        if self.used_tokens >= self.token_budget:
            error_msg = f"Token budget exceeded: {self.used_tokens}/{self.token_budget}"
            logger.warning(error_msg)
            
            if job_id:
                event_stream = get_event_stream()
                await event_stream.emit_llm_budget(job_id, self.used_tokens, self.token_budget - self.used_tokens)
            
            return LLMCompletionResponse(
                content={},
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                error=error_msg
            )
        
        try:
            # Make LLM call
            start_time = asyncio.get_event_loop().time()
            
            # Simulate LLM call (replace with actual OpenAI client)
            response = await self._make_llm_call(request)
            
            end_time = asyncio.get_event_loop().time()
            duration_ms = (end_time - start_time) * 1000
            
            # Update token usage
            tokens_in = len(request.prompt.split())
            tokens_out = response.usage.get("completion_tokens", 0)
            self.used_tokens += tokens_in + tokens_out
            self.call_count += 1
            
            # Cache response
            self.cache[cache_key] = response
            
            # Record metrics
            record_llm_call(
                "completion", 
                settings.LLM_MODEL, 
                "success", 
                duration_ms, 
                tokens_in, 
                tokens_out, 
                False
            )
            
            # Publish token usage event
            if job_id:
                event_stream = get_event_stream()
                await event_stream.emit_llm_budget(job_id, self.used_tokens, self.token_budget - self.used_tokens)
            
            return response
            
        except Exception as e:
            self.error_count += 1
            error_msg = f"LLM call failed: {e}"
            logger.error(error_msg)
            
            record_llm_call("completion", settings.LLM_MODEL, "error", 0, 0, 0, False)
            
            return LLMCompletionResponse(
                content={},
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                error=error_msg
            )
    
    async def _make_llm_call(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        """Make actual LLM call (placeholder for OpenAI client)."""
        # This would be replaced with actual OpenAI client
        # For now, return a mock response
        
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        # Mock response based on request type
        if "route" in request.context.get("type", ""):
            content = self._mock_route_completion(request)
        elif "job" in request.context.get("type", ""):
            content = self._mock_job_completion(request)
        elif "call" in request.context.get("type", ""):
            content = self._mock_call_completion(request)
        elif "schema" in request.context.get("type", ""):
            content = self._mock_schema_completion(request)
        else:
            content = {}
        
        return LLMCompletionResponse(
            content=content,
            usage={
                "prompt_tokens": len(request.prompt.split()),
                "completion_tokens": 50  # Mock completion tokens
            }
        )
    
    def _mock_route_completion(self, request: LLMCompletionRequest) -> Dict[str, Any]:
        """Mock route completion response."""
        context = request.context
        file_path = context.get("file_path", "unknown")
        
        return {
            "routes": [
                {
                    "method": "GET",
                    "path": "/api/health",
                    "handler": "health_check",
                    "middlewares": ["auth_middleware"],
                    "statusCodes": [200],
                    "evidence": [{"file": file_path, "start": 1, "end": 1}],
                    "confidence": 0.7,
                    "hypothesis": True,
                    "reason_code": "llm_completion"
                }
            ]
        }
    
    def _mock_job_completion(self, request: LLMCompletionRequest) -> Dict[str, Any]:
        """Mock job completion response."""
        context = request.context
        file_path = context.get("file_path", "unknown")
        
        return {
            "jobs": [
                {
                    "name": "process_payment",
                    "type": "celery",
                    "producer": "payment_service",
                    "consumer": "worker",
                    "evidence": [{"file": file_path, "start": 1, "end": 1}],
                    "confidence": 0.6,
                    "hypothesis": True,
                    "reason_code": "llm_completion"
                }
            ]
        }
    
    def _mock_call_completion(self, request: LLMCompletionRequest) -> Dict[str, Any]:
        """Mock call completion response."""
        context = request.context
        file_path = context.get("file_path", "unknown")
        
        return {
            "calls": [
                {
                    "from_node": f"{file_path}:main",
                    "to_node": "utils:helper_function",
                    "kind": "function_call",
                    "evidence": [{"file": file_path, "start": 1, "end": 1}],
                    "confidence": 0.5,
                    "hypothesis": True,
                    "reason_code": "llm_completion"
                }
            ]
        }
    
    def _mock_schema_completion(self, request: LLMCompletionRequest) -> Dict[str, Any]:
        """Mock schema completion response."""
        return {
            "schemas": {
                "UserModel": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string"}
                    },
                    "confidence": 0.8,
                    "hypothesis": False
                }
            }
        }
    
    def _generate_cache_key(self, request: LLMCompletionRequest) -> str:
        """Generate cache key for request."""
        key_data = {
            "prompt": request.prompt,
            "context": request.context,
            "schema": request.expected_schema
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics."""
        return {
            "used_tokens": self.used_tokens,
            "budget": self.token_budget,
            "remaining": self.token_budget - self.used_tokens,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "cache_size": len(self.cache),
            "cache_hit_rate": self.call_count / max(len(self.cache), 1)
        }

class LLMGraphCompleter:
    """Completes graphs using LLM analysis."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.llm_client = LLMClient()
        self.completion_prompts = CompletionPrompts()
    
    async def complete_routes(self, static_routes: Dict[str, List[RouteModel]], job_id: Optional[str] = None) -> Dict[str, List[RouteModel]]:
        """Complete route information using LLM."""
        logger.info("Completing routes with LLM")
        
        completed_routes = {}
        
        for file_path, routes in static_routes.items():
            try:
                # Build completion request
                request = self.completion_prompts.build_route_completion_request(file_path, routes)
                
                # Get LLM completion
                response = await self.llm_client.complete(request, job_id)
                
                if response.error:
                    logger.warning(f"Route completion failed for {file_path}: {response.error}")
                    continue
                
                # Parse response
                completed_routes[file_path] = self._parse_route_completion(response.content, file_path)
                
            except Exception as e:
                logger.error(f"Route completion error for {file_path}: {e}")
                continue
        
        record_detector_hit("llm_route_completion")
        return completed_routes
    
    async def complete_jobs(self, static_jobs: Dict[str, List[Dict[str, Any]]], job_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Complete job information using LLM."""
        logger.info("Completing jobs with LLM")
        
        completed_jobs = {}
        
        for file_path, jobs in static_jobs.items():
            try:
                # Build completion request
                request = self.completion_prompts.build_job_completion_request(file_path, jobs)
                
                # Get LLM completion
                response = await self.llm_client.complete(request, job_id)
                
                if response.error:
                    logger.warning(f"Job completion failed for {file_path}: {response.error}")
                    continue
                
                # Parse response
                completed_jobs[file_path] = self._parse_job_completion(response.content, file_path)
                
            except Exception as e:
                logger.error(f"Job completion error for {file_path}: {e}")
                continue
        
        record_detector_hit("llm_job_completion")
        return completed_jobs
    
    async def complete_calls(self, static_calls: Dict[str, List[GraphEdge]], job_id: Optional[str] = None) -> Dict[str, List[GraphEdge]]:
        """Complete call graph using LLM."""
        logger.info("Completing call graph with LLM")
        
        completed_calls = {}
        
        for file_path, calls in static_calls.items():
            try:
                # Build completion request
                request = self.completion_prompts.build_call_completion_request(file_path, calls)
                
                # Get LLM completion
                response = await self.llm_client.complete(request, job_id)
                
                if response.error:
                    logger.warning(f"Call completion failed for {file_path}: {response.error}")
                    continue
                
                # Parse response
                completed_calls[file_path] = self._parse_call_completion(response.content, file_path)
                
            except Exception as e:
                logger.error(f"Call completion error for {file_path}: {e}")
                continue
        
        record_detector_hit("llm_call_completion")
        return completed_calls
    
    async def infer_schemas(self, file_paths: List[str], job_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Infer data schemas using LLM."""
        logger.info("Inferring schemas with LLM")
        
        inferred_schemas = {}
        
        for file_path in file_paths:
            try:
                # Read file content
                full_path = self.repo_root / "snapshot" / file_path
                if not full_path.exists():
                    continue
                
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                
                # Build completion request
                request = self.completion_prompts.build_schema_completion_request(file_path, content)
                
                # Get LLM completion
                response = await self.llm_client.complete(request, job_id)
                
                if response.error:
                    logger.warning(f"Schema inference failed for {file_path}: {response.error}")
                    continue
                
                # Parse response
                inferred_schemas[file_path] = self._parse_schema_completion(response.content, file_path)
                
            except Exception as e:
                logger.error(f"Schema inference error for {file_path}: {e}")
                continue
        
        record_detector_hit("llm_schema_inference")
        return inferred_schemas
    
    def _parse_route_completion(self, content: Dict[str, Any], file_path: str) -> List[RouteModel]:
        """Parse route completion response."""
        routes = []
        
        for route_data in content.get("routes", []):
            try:
                route = RouteModel(
                    method=route_data.get("method", "GET"),
                    path=route_data.get("path", "/"),
                    handler=route_data.get("handler", "unknown"),
                    middlewares=route_data.get("middlewares", []),
                    statusCodes=route_data.get("statusCodes", []),
                    evidence=[EvidenceSpan(**span) for span in route_data.get("evidence", [])],
                    confidence=route_data.get("confidence", 0.5),
                    hypothesis=route_data.get("hypothesis", True),
                    reason_code=route_data.get("reason_code", "llm_completion")
                )
                routes.append(route)
            except Exception as e:
                logger.warning(f"Failed to parse route completion: {e}")
                continue
        
        return routes
    
    def _parse_job_completion(self, content: Dict[str, Any], file_path: str) -> List[Dict[str, Any]]:
        """Parse job completion response."""
        jobs = []
        
        for job_data in content.get("jobs", []):
            try:
                job = {
                    "name": job_data.get("name", "unknown"),
                    "type": job_data.get("type", "unknown"),
                    "producer": job_data.get("producer", "unknown"),
                    "consumer": job_data.get("consumer", "unknown"),
                    "evidence": [EvidenceSpan(**span) for span in job_data.get("evidence", [])],
                    "confidence": job_data.get("confidence", 0.5),
                    "hypothesis": job_data.get("hypothesis", True),
                    "reason_code": job_data.get("reason_code", "llm_completion")
                }
                jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to parse job completion: {e}")
                continue
        
        return jobs
    
    def _parse_call_completion(self, content: Dict[str, Any], file_path: str) -> List[GraphEdge]:
        """Parse call completion response."""
        edges = []
        
        for call_data in content.get("calls", []):
            try:
                edge = GraphEdge(
                    from_node=call_data.get("from_node", "unknown"),
                    to_node=call_data.get("to_node", "unknown"),
                    kind=call_data.get("kind", "call"),
                    evidence=[EvidenceSpan(**span) for span in call_data.get("evidence", [])],
                    confidence=call_data.get("confidence", 0.5),
                    hypothesis=call_data.get("hypothesis", True),
                    reason_code=call_data.get("reason_code", "llm_completion")
                )
                edges.append(edge)
            except Exception as e:
                logger.warning(f"Failed to parse call completion: {e}")
                continue
        
        return edges
    
    def _parse_schema_completion(self, content: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Parse schema completion response."""
        return content.get("schemas", {})
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics."""
        return self.llm_client.get_usage_stats()

class CompletionPrompts:
    """Prompts for LLM completion tasks."""
    
    def build_route_completion_request(self, file_path: str, routes: List[RouteModel]) -> LLMCompletionRequest:
        """Build route completion request."""
        prompt = f"""
Analyze this file and complete missing route information:

File: {file_path}
Existing routes: {[r.model_dump() for r in routes]}

Return JSON with additional routes that might exist in this file.
Focus on:
- API endpoints
- Route handlers
- Middleware usage
- HTTP methods

Required JSON schema:
{{
  "routes": [
    {{
      "method": "string",
      "path": "string", 
      "handler": "string",
      "middlewares": ["string"],
      "statusCodes": [number],
      "evidence": [{{"file": "string", "start": number, "end": number}}],
      "confidence": number,
      "hypothesis": boolean,
      "reason_code": "string"
    }}
  ]
}}
"""
        
        return LLMCompletionRequest(
            prompt=prompt,
            context={"type": "route_completion", "file_path": file_path},
            expected_schema={"routes": []},
            max_tokens=1000,
            temperature=0.0
        )
    
    def build_job_completion_request(self, file_path: str, jobs: List[Dict[str, Any]]) -> LLMCompletionRequest:
        """Build job completion request."""
        prompt = f"""
Analyze this file and complete missing job/queue information:

File: {file_path}
Existing jobs: {jobs}

Return JSON with additional jobs that might exist in this file.
Focus on:
- Background tasks
- Queue workers
- Scheduled jobs
- Async processing

Required JSON schema:
{{
  "jobs": [
    {{
      "name": "string",
      "type": "string",
      "producer": "string",
      "consumer": "string", 
      "evidence": [{{"file": "string", "start": number, "end": number}}],
      "confidence": number,
      "hypothesis": boolean,
      "reason_code": "string"
    }}
  ]
}}
"""
        
        return LLMCompletionRequest(
            prompt=prompt,
            context={"type": "job_completion", "file_path": file_path},
            expected_schema={"jobs": []},
            max_tokens=1000,
            temperature=0.0
        )
    
    def build_call_completion_request(self, file_path: str, calls: List[GraphEdge]) -> LLMCompletionRequest:
        """Build call completion request."""
        prompt = f"""
Analyze this file and complete missing function call information:

File: {file_path}
Existing calls: {[c.model_dump() for c in calls]}

Return JSON with additional function calls that might exist in this file.
Focus on:
- Function invocations
- Method calls
- Import usage
- Dependency relationships

Required JSON schema:
{{
  "calls": [
    {{
      "from_node": "string",
      "to_node": "string",
      "kind": "string",
      "evidence": [{{"file": "string", "start": number, "end": number}}],
      "confidence": number,
      "hypothesis": boolean,
      "reason_code": "string"
    }}
  ]
}}
"""
        
        return LLMCompletionRequest(
            prompt=prompt,
            context={"type": "call_completion", "file_path": file_path},
            expected_schema={"calls": []},
            max_tokens=1000,
            temperature=0.0
        )
    
    def build_schema_completion_request(self, file_path: str, content: str) -> LLMCompletionRequest:
        """Build schema completion request."""
        prompt = f"""
Analyze this file and infer data schemas:

File: {file_path}
Content: {content[:2000]}...

Return JSON with inferred data schemas.
Focus on:
- Data models
- API schemas
- Database schemas
- Type definitions

Required JSON schema:
{{
  "schemas": {{
    "ModelName": {{
      "type": "object",
      "properties": {{
        "field": {{"type": "string"}}
      }},
      "confidence": number,
      "hypothesis": boolean
    }}
  }}
}}
"""
        
        return LLMCompletionRequest(
            prompt=prompt,
            context={"type": "schema_completion", "file_path": file_path},
            expected_schema={"schemas": {}},
            max_tokens=1500,
            temperature=0.0
        )
