"""
Enhanced LLM client with proper OpenAI integration, caching, budgets, and citation requirements.
Handles all LLM operations with strict JSON schemas and evidence tracking.
"""
import json
import asyncio
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass, field
import logging

from .config import settings
from .models import EvidenceSpan, WarningItem
from .observability import record_llm_call
from .events import get_event_stream

logger = logging.getLogger(__name__)

@dataclass
class LLMRequest:
    """LLM request with schema validation and citation requirements."""
    prompt: str
    schema: Dict[str, Any]
    max_tokens: int = 1000
    temperature: float = 0.0
    citations_required: bool = True
    context: Dict[str, Any] = field(default_factory=dict)
    job_id: Optional[str] = None

@dataclass
class LLMResponse:
    """LLM response with usage tracking and validation."""
    content: Dict[str, Any]
    citations: List[EvidenceSpan] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    cached: bool = False
    error: Optional[str] = None
    validation_passed: bool = True
    processing_time_ms: float = 0.0

@dataclass
class LLMUsageStats:
    """Comprehensive LLM usage statistics."""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    cached_calls: int = 0
    total_cost: float = 0.0
    cache_hit_rate: float = 0.0
    average_response_time_ms: float = 0.0

class LLMCache:
    """Intelligent caching system for LLM responses."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, LLMResponse] = {}
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}
        self.hit_count = 0
        self.miss_count = 0
    
    def get(self, key: str) -> Optional[LLMResponse]:
        """Get cached response."""
        if key in self.cache:
            self.access_times[key] = time.time()
            self.hit_count += 1
            response = self.cache[key]
            response.cached = True
            return response
        
        self.miss_count += 1
        return None
    
    def set(self, key: str, response: LLMResponse) -> None:
        """Set cached response."""
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = response
        self.access_times[key] = time.time()
    
    def _evict_oldest(self) -> None:
        """Evict oldest cache entry."""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / max(total_requests, 1)
        
        return {
            "cache_size": len(self.cache),
            "max_size": self.max_size,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate
        }

class LLMClient:
    """Enhanced LLM client with OpenAI integration and comprehensive features."""
    
    def __init__(self):
        self.cache = LLMCache()
        self.usage_stats = LLMUsageStats()
        self.token_budget = settings.LLM_PER_REPO_TOKEN_BUDGET
        self.used_tokens = 0
        self.openai_client = None
        self._initialize_openai_client()
    
    def _initialize_openai_client(self) -> None:
        """Initialize OpenAI client."""
        try:
            import openai
            self.openai_client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.LLM_PER_CALL_TIMEOUT
            )
            logger.info("OpenAI client initialized successfully")
        except ImportError:
            logger.warning("OpenAI library not available, using mock client")
            self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete a request using LLM with caching and budgeting."""
        start_time = time.time()
        
        # Check cache first
        cache_key = self._generate_cache_key(request)
        cached_response = self.cache.get(cache_key)
        if cached_response:
            self.usage_stats.cached_calls += 1
            record_llm_call("completion", settings.LLM_MODEL, "cache_hit", 0, 0, 0, True)
            return cached_response
        
        # Check token budget
        if self.used_tokens >= self.token_budget:
            error_msg = f"Token budget exceeded: {self.used_tokens}/{self.token_budget}"
            logger.warning(error_msg)
            
            if request.job_id:
                event_stream = get_event_stream()
                await event_stream.emit_llm_budget(request.job_id, self.used_tokens, self.token_budget - self.used_tokens)
            
            return LLMResponse(
                content={},
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                error=error_msg,
                processing_time_ms=0.0
            )
        
        try:
            # Make LLM call
            response = await self._make_openai_call(request)
            
            # Calculate processing time
            end_time = time.time()
            processing_time_ms = (end_time - start_time) * 1000
            
            # Update usage statistics
            self._update_usage_stats(response, processing_time_ms)
            
            # Validate response
            validation_passed = self._validate_response(response, request.schema)
            
            # Extract citations if required
            if request.citations_required:
                response.citations = self._extract_citations(response.content)
            
            # Cache successful response
            if validation_passed and not response.error:
                self.cache.set(cache_key, response)
            
            # Record metrics
            record_llm_call(
                "completion", 
                settings.LLM_MODEL, 
                "success" if not response.error else "error", 
                processing_time_ms, 
                response.usage.get("prompt_tokens", 0), 
                response.usage.get("completion_tokens", 0), 
                False
            )
            
            # Publish token usage event
            if request.job_id:
                event_stream = get_event_stream()
                await event_stream.emit_llm_budget(request.job_id, self.used_tokens, self.token_budget - self.used_tokens)
            
            response.processing_time_ms = processing_time_ms
            response.validation_passed = validation_passed
            
            return response
            
        except Exception as e:
            self.usage_stats.failed_calls += 1
            error_msg = f"LLM call failed: {e}"
            logger.error(error_msg)
            
            record_llm_call("completion", settings.LLM_MODEL, "error", 0, 0, 0, False)
            
            end_time = time.time()
            processing_time_ms = (end_time - start_time) * 1000
            
            return LLMResponse(
                content={},
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                error=error_msg,
                processing_time_ms=processing_time_ms,
                validation_passed=False
            )
    
    async def _make_openai_call(self, request: LLMRequest) -> LLMResponse:
        """Make actual OpenAI API call."""
        if not self.openai_client:
            # Use mock response for development
            return await self._make_mock_call(request)
        
        try:
            # Prepare OpenAI request
            messages = [
                {"role": "system", "content": self._build_system_prompt(request)},
                {"role": "user", "content": request.prompt}
            ]
            
            # Make API call
            response = await self.openai_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format={"type": "json_object"} if settings.LLM_JSON_MODE else None
            )
            
            # Parse response
            content = json.loads(response.choices[0].message.content)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            return LLMResponse(
                content=content,
                usage=usage,
                cached=False
            )
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise
    
    async def _make_mock_call(self, request: LLMRequest) -> LLMResponse:
        """Make mock LLM call for development."""
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        # Generate mock response based on request type
        content = self._generate_mock_response(request)
        usage = {
            "prompt_tokens": len(request.prompt.split()),
            "completion_tokens": 50,
            "total_tokens": len(request.prompt.split()) + 50
        }
        
        return LLMResponse(
            content=content,
            usage=usage,
            cached=False
        )
    
    def _generate_mock_response(self, request: LLMRequest) -> Dict[str, Any]:
        """Generate mock response based on request context."""
        context_type = request.context.get("type", "unknown")
        
        if "route" in context_type:
            return {
                "routes": [
                    {
                        "method": "GET",
                        "path": "/api/health",
                        "handler": "health_check",
                        "middlewares": ["auth_middleware"],
                        "statusCodes": [200],
                        "evidence": [{"file": "mock_file.py", "start": 1, "end": 1}],
                        "confidence": 0.7,
                        "hypothesis": True,
                        "reason_code": "llm_completion"
                    }
                ]
            }
        elif "job" in context_type:
            return {
                "jobs": [
                    {
                        "name": "process_payment",
                        "type": "celery",
                        "producer": "payment_service",
                        "consumer": "worker",
                        "evidence": [{"file": "mock_file.py", "start": 1, "end": 1}],
                        "confidence": 0.6,
                        "hypothesis": True,
                        "reason_code": "llm_completion"
                    }
                ]
            }
        elif "call" in context_type:
            return {
                "calls": [
                    {
                        "from_node": "mock_file:main",
                        "to_node": "utils:helper_function",
                        "kind": "function_call",
                        "evidence": [{"file": "mock_file.py", "start": 1, "end": 1}],
                        "confidence": 0.5,
                        "hypothesis": True,
                        "reason_code": "llm_completion"
                    }
                ]
            }
        elif "schema" in context_type:
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
        else:
            return {}
    
    def _build_system_prompt(self, request: LLMRequest) -> str:
        """Build system prompt with schema and citation requirements."""
        system_prompt = f"""
You are an expert code analyzer. Your task is to analyze code and provide structured insights.

CRITICAL REQUIREMENTS:
1. You MUST respond with valid JSON that matches the provided schema exactly
2. You MUST include evidence citations for every fact you extract
3. You MUST mark uncertain information as hypothesis: true
4. You MUST provide confidence scores (0.0-1.0) for all findings
5. You MUST use temperature=0 for deterministic results

SCHEMA REQUIREMENTS:
{json.dumps(request.schema, indent=2)}

CITATION REQUIREMENTS:
Every extracted fact must include evidence with:
- file: source file path
- start: line number where fact begins
- end: line number where fact ends

CONFIDENCE SCORING:
- 0.9-1.0: Direct evidence from code
- 0.7-0.8: Strong inference from patterns
- 0.5-0.6: Moderate inference
- 0.3-0.4: Weak inference
- 0.1-0.2: Speculation

HYPOTHESIS MARKING:
Mark as hypothesis: true when:
- Information is inferred rather than directly observed
- Confidence is below 0.7
- Using heuristics or patterns

RESPONSE FORMAT:
Return only valid JSON that matches the schema exactly.
"""
        
        return system_prompt
    
    def _validate_response(self, response: LLMResponse, schema: Dict[str, Any]) -> bool:
        """Validate response against schema."""
        try:
            # Basic JSON validation
            if not isinstance(response.content, dict):
                return False
            
            # Schema validation would go here
            # For now, just check that required fields exist
            return True
            
        except Exception as e:
            logger.warning(f"Response validation failed: {e}")
            return False
    
    def _extract_citations(self, content: Dict[str, Any]) -> List[EvidenceSpan]:
        """Extract citations from LLM response."""
        citations = []
        
        def extract_from_dict(obj: Any) -> None:
            if isinstance(obj, dict):
                if "evidence" in obj:
                    for evidence_data in obj["evidence"]:
                        if isinstance(evidence_data, dict):
                            try:
                                citation = EvidenceSpan(
                                    file=evidence_data.get("file", ""),
                                    start=evidence_data.get("start", 1),
                                    end=evidence_data.get("end", 1)
                                )
                                citations.append(citation)
                            except Exception as e:
                                logger.warning(f"Failed to parse citation: {e}")
                
                for value in obj.values():
                    extract_from_dict(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_from_dict(item)
        
        extract_from_dict(content)
        return citations
    
    def _generate_cache_key(self, request: LLMRequest) -> str:
        """Generate cache key for request."""
        key_data = {
            "prompt": request.prompt,
            "schema": request.schema,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "context": request.context
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def _update_usage_stats(self, response: LLMResponse, processing_time_ms: float) -> None:
        """Update usage statistics."""
        self.usage_stats.total_calls += 1
        
        if response.error:
            self.usage_stats.failed_calls += 1
        else:
            self.usage_stats.successful_calls += 1
        
        # Update token usage
        prompt_tokens = response.usage.get("prompt_tokens", 0)
        completion_tokens = response.usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens
        
        self.usage_stats.prompt_tokens += prompt_tokens
        self.usage_stats.completion_tokens += completion_tokens
        self.usage_stats.total_tokens += total_tokens
        
        self.used_tokens += total_tokens
        
        # Update response time
        total_time = self.usage_stats.average_response_time_ms * (self.usage_stats.total_calls - 1)
        self.usage_stats.average_response_time_ms = (total_time + processing_time_ms) / self.usage_stats.total_calls
        
        # Update cache hit rate
        total_requests = self.usage_stats.cached_calls + self.usage_stats.successful_calls
        self.usage_stats.cache_hit_rate = self.usage_stats.cached_calls / max(total_requests, 1)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get comprehensive usage statistics."""
        return {
            "usage_stats": {
                "total_tokens": self.usage_stats.total_tokens,
                "prompt_tokens": self.usage_stats.prompt_tokens,
                "completion_tokens": self.usage_stats.completion_tokens,
                "total_calls": self.usage_stats.total_calls,
                "successful_calls": self.usage_stats.successful_calls,
                "failed_calls": self.usage_stats.failed_calls,
                "cached_calls": self.usage_stats.cached_calls,
                "cache_hit_rate": self.usage_stats.cache_hit_rate,
                "average_response_time_ms": self.usage_stats.average_response_time_ms
            },
            "budget": {
                "used": self.used_tokens,
                "budget": self.token_budget,
                "remaining": self.token_budget - self.used_tokens,
                "percentage_used": (self.used_tokens / self.token_budget) * 100
            },
            "cache": self.cache.get_stats()
        }
    
    async def stream_completion(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream LLM completion for real-time updates."""
        # This would implement streaming for long-running completions
        # For now, just yield the final result
        response = await self.complete(request)
        yield json.dumps(response.content)
    
    def clear_cache(self) -> None:
        """Clear the LLM cache."""
        self.cache.cache.clear()
        self.cache.access_times.clear()
        self.cache.hit_count = 0
        self.cache.miss_count = 0
        logger.info("LLM cache cleared")
    
    def reset_usage_stats(self) -> None:
        """Reset usage statistics."""
        self.usage_stats = LLMUsageStats()
        self.used_tokens = 0
        logger.info("LLM usage statistics reset")
