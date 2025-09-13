"""
Structured LLM prompts for different analysis tasks.
Provides consistent, schema-enforced prompts with citation requirements.
"""
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .models import EvidenceSpan, RouteModel, GraphEdge

@dataclass
class PromptTemplate:
    """Template for LLM prompts."""
    system_prompt: str
    user_prompt_template: str
    expected_schema: Dict[str, Any]
    max_tokens: int = 1000
    temperature: float = 0.0
    citations_required: bool = True

class LLMPrompts:
    """Collection of structured LLM prompts for code analysis."""
    
    def __init__(self):
        self.templates = self._initialize_templates()
    
    def _initialize_templates(self) -> Dict[str, PromptTemplate]:
        """Initialize all prompt templates."""
        return {
            "route_completion": self._create_route_completion_template(),
            "job_completion": self._create_job_completion_template(),
            "call_completion": self._create_call_completion_template(),
            "schema_inference": self._create_schema_inference_template(),
            "framework_classification": self._create_framework_classification_template(),
            "external_client_classification": self._create_external_client_classification_template(),
            "capability_title_generation": self._create_capability_title_template(),
            "capability_narrative": self._create_capability_narrative_template(),
            "file_summary": self._create_file_summary_template(),
            "capability_summary": self._create_capability_summary_template(),
        }
    
    def get_prompt(self, template_name: str, **kwargs) -> PromptTemplate:
        """Get a prompt template with variables filled."""
        if template_name not in self.templates:
            raise ValueError(f"Unknown prompt template: {template_name}")
        
        template = self.templates[template_name]
        user_prompt = template.user_prompt_template.format(**kwargs)
        
        return PromptTemplate(
            system_prompt=template.system_prompt,
            user_prompt_template=user_prompt,
            expected_schema=template.expected_schema,
            max_tokens=template.max_tokens,
            temperature=template.temperature,
            citations_required=template.citations_required
        )
    
    def _create_route_completion_template(self) -> PromptTemplate:
        """Create route completion prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert web framework analyzer. Your task is to identify and complete missing route information from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and identify ALL possible routes
2. Include HTTP methods, paths, handlers, middleware, and status codes
3. Mark uncertain routes as hypothesis: true with lower confidence
4. Provide evidence citations for every route you identify
5. Focus on both explicit and implicit route patterns

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and identify all routes:

FILE: {file_path}
CONTENT: {content}
EXISTING ROUTES: {existing_routes}

Identify additional routes that might exist in this file, including:
- API endpoints
- Web pages
- Route handlers
- Middleware usage
- HTTP methods and paths

For each route, provide:
- HTTP method (GET, POST, PUT, DELETE, etc.)
- Path pattern
- Handler function name
- Middleware list
- Expected status codes
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "routes": [
                    {
                        "method": "string",
                        "path": "string",
                        "handler": "string",
                        "middlewares": ["string"],
                        "statusCodes": ["number"],
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean",
                        "reason_code": "string"
                    }
                ]
            },
            max_tokens=1500,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_job_completion_template(self) -> PromptTemplate:
        """Create job completion prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert job queue analyzer. Your task is to identify and complete missing job/queue information from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and identify ALL possible jobs, tasks, and workers
2. Include job names, types, producers, consumers, and queue information
3. Mark uncertain jobs as hypothesis: true with lower confidence
4. Provide evidence citations for every job you identify
5. Focus on both explicit job definitions and implicit job patterns

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and identify all jobs/tasks:

FILE: {file_path}
CONTENT: {content}
EXISTING JOBS: {existing_jobs}

Identify additional jobs that might exist in this file, including:
- Background tasks
- Queue workers
- Scheduled jobs
- Async processing
- Job producers and consumers

For each job, provide:
- Job name
- Job type (celery, bull, agenda, etc.)
- Producer (what triggers the job)
- Consumer (what processes the job)
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "jobs": [
                    {
                        "name": "string",
                        "type": "string",
                        "producer": "string",
                        "consumer": "string",
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean",
                        "reason_code": "string"
                    }
                ]
            },
            max_tokens=1500,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_call_completion_template(self) -> PromptTemplate:
        """Create call completion prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert call graph analyzer. Your task is to identify and complete missing function call information from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and identify ALL possible function calls and relationships
2. Include call relationships, function invocations, and dependency connections
3. Mark uncertain calls as hypothesis: true with lower confidence
4. Provide evidence citations for every call you identify
5. Focus on both explicit calls and implicit dependencies

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and identify all function calls:

FILE: {file_path}
CONTENT: {content}
EXISTING CALLS: {existing_calls}

Identify additional function calls that might exist in this file, including:
- Function invocations
- Method calls
- Import usage
- Dependency relationships
- Call chains and flows

For each call, provide:
- Source node (calling function/file)
- Target node (called function/file)
- Call kind (function_call, method_call, import, etc.)
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "calls": [
                    {
                        "from_node": "string",
                        "to_node": "string",
                        "kind": "string",
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean",
                        "reason_code": "string"
                    }
                ]
            },
            max_tokens=1500,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_schema_inference_template(self) -> PromptTemplate:
        """Create schema inference prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert data schema analyzer. Your task is to infer data schemas from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and infer data models, schemas, and types
2. Include field definitions, types, relationships, and constraints
3. Mark uncertain schemas as hypothesis: true with lower confidence
4. Provide evidence citations for every schema you identify
5. Focus on both explicit schema definitions and implicit type information

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and infer data schemas:

FILE: {file_path}
CONTENT: {content}

Infer data schemas that might exist in this file, including:
- Data models
- API schemas
- Database schemas
- Type definitions
- Request/response schemas

For each schema, provide:
- Schema name
- Schema type (object, array, etc.)
- Field definitions with types
- Relationships and constraints
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "schemas": {
                    "ModelName": {
                        "type": "object",
                        "properties": {
                            "field": {
                                "type": "string",
                                "description": "string"
                            }
                        },
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean"
                    }
                }
            },
            max_tokens=2000,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_framework_classification_template(self) -> PromptTemplate:
        """Create framework classification prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert framework classifier. Your task is to identify web frameworks and technologies from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and identify frameworks, libraries, and technologies
2. Include framework names, versions, and usage patterns
3. Mark uncertain classifications as hypothesis: true with lower confidence
4. Provide evidence citations for every framework you identify
5. Focus on both explicit imports and implicit framework patterns

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and identify frameworks:

FILE: {file_path}
CONTENT: {content}

Identify frameworks and technologies used in this file, including:
- Web frameworks (FastAPI, Flask, Express, Next.js, etc.)
- Database ORMs (SQLAlchemy, Prisma, TypeORM, etc.)
- Job queues (Celery, Bull, Agenda, etc.)
- Testing frameworks
- Build tools and utilities

For each framework, provide:
- Framework name
- Framework type
- Usage pattern or purpose
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "frameworks": [
                    {
                        "name": "string",
                        "type": "string",
                        "usage": "string",
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean"
                    }
                ]
            },
            max_tokens=1000,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_external_client_classification_template(self) -> PromptTemplate:
        """Create external client classification prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert external service analyzer. Your task is to identify external service integrations from code analysis.

CRITICAL REQUIREMENTS:
1. Analyze the provided code and identify external services, APIs, and integrations
2. Include service names, types, and usage patterns
3. Mark uncertain integrations as hypothesis: true with lower confidence
4. Provide evidence citations for every external service you identify
5. Focus on both explicit SDK usage and implicit service patterns

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Analyze this code file and identify external services:

FILE: {file_path}
CONTENT: {content}

Identify external services and integrations used in this file, including:
- Cloud services (AWS, GCP, Azure)
- Payment processors (Stripe, PayPal)
- Communication services (Twilio, SendGrid)
- Databases (MongoDB, Redis, PostgreSQL)
- APIs and webhooks
- Third-party libraries and SDKs

For each external service, provide:
- Service name
- Service type
- Integration purpose
- Evidence citations (file:line spans)
- Confidence score (0.0-1.0)
- Whether this is a hypothesis or direct observation
""",
            expected_schema={
                "external_services": [
                    {
                        "name": "string",
                        "type": "string",
                        "purpose": "string",
                        "evidence": [
                            {
                                "file": "string",
                                "start": "number",
                                "end": "number"
                            }
                        ],
                        "confidence": "number",
                        "hypothesis": "boolean"
                    }
                ]
            },
            max_tokens=1000,
            temperature=0.0,
            citations_required=True
        )
    
    def _create_capability_title_template(self) -> PromptTemplate:
        """Create capability title generation prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert capability analyzer. Your task is to generate concise, descriptive titles for software capabilities.

CRITICAL REQUIREMENTS:
1. Generate clear, concise titles that describe the capability's purpose
2. Use standard naming conventions and avoid jargon
3. Focus on the primary function and value proposition
4. Keep titles under 60 characters
5. Use title case formatting

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Generate a title for this capability:

ENTRYPOINT: {entrypoint}
LANE: {lane}
DATA_FLOW: {data_flow}
CONTROL_FLOW: {control_flow}

Generate a concise title that describes:
- Primary function
- Target audience (web, api, worker, etc.)
- Key value proposition

Examples:
- "User Authentication API"
- "Payment Processing Worker"
- "Admin Dashboard Interface"
- "Email Notification Scheduler"
""",
            expected_schema={
                "title": "string",
                "description": "string",
                "confidence": "number",
                "hypothesis": "boolean"
            },
            max_tokens=200,
            temperature=0.0,
            citations_required=False
        )
    
    def _create_capability_narrative_template(self) -> PromptTemplate:
        """Create capability narrative generation prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert capability analyst. Your task is to generate comprehensive narratives for software capabilities.

CRITICAL REQUIREMENTS:
1. Generate detailed narratives that explain the capability's purpose and operation
2. Include information about inputs, outputs, and processes
3. Use clear, professional language suitable for technical documentation
4. Focus on business value and technical implementation
5. Keep narratives between 100-300 words

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Generate a narrative for this capability:

ENTRYPOINT: {entrypoint}
LANE: {lane}
PURPOSE: {purpose}
DATA_FLOW: {data_flow}
CONTROL_FLOW: {control_flow}
POLICIES: {policies}
CONTRACTS: {contracts}

Generate a comprehensive narrative that explains:
- What this capability does
- How it works
- What inputs it receives
- What outputs it produces
- What external services it integrates with
- What policies and contracts it enforces
""",
            expected_schema={
                "narrative": "string",
                "key_features": ["string"],
                "confidence": "number",
                "hypothesis": "boolean"
            },
            max_tokens=500,
            temperature=0.0,
            citations_required=False
        )
    
    def _create_file_summary_template(self) -> PromptTemplate:
        """Create file summary prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert code summarizer. Your task is to generate concise summaries of code files.

CRITICAL REQUIREMENTS:
1. Generate clear, concise summaries that explain the file's purpose
2. Include information about key functions, classes, and responsibilities
3. Use clear, professional language suitable for documentation
4. Focus on the file's role in the larger system
5. Keep summaries under 100 words

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Generate a summary for this file:

FILE: {file_path}
CONTENT: {content}
FUNCTIONS: {functions}
CLASSES: {classes}
IMPORTS: {imports}

Generate a concise summary that explains:
- File's primary purpose
- Key functions and classes
- Role in the system
- Dependencies and relationships
""",
            expected_schema={
                "summary": "string",
                "key_elements": ["string"],
                "confidence": "number",
                "hypothesis": "boolean"
            },
            max_tokens=300,
            temperature=0.0,
            citations_required=False
        )
    
    def _create_capability_summary_template(self) -> PromptTemplate:
        """Create capability summary prompt template."""
        return PromptTemplate(
            system_prompt="""
You are an expert capability summarizer. Your task is to generate executive summaries of software capabilities.

CRITICAL REQUIREMENTS:
1. Generate high-level summaries suitable for stakeholders
2. Include information about business value and technical implementation
3. Use clear, non-technical language where possible
4. Focus on outcomes and impact
5. Keep summaries under 150 words

RESPONSE FORMAT:
Return valid JSON matching the schema exactly.
""",
            user_prompt_template="""
Generate an executive summary for this capability:

CAPABILITY: {capability_name}
PURPOSE: {purpose}
LANE: {lane}
ENTRYPOINTS: {entrypoints}
ORCHESTRATORS: {orchestrators}
DATA_FLOW: {data_flow}

Generate an executive summary that explains:
- Business purpose and value
- Technical approach
- Key capabilities and features
- Integration points
- Expected outcomes
""",
            expected_schema={
                "executive_summary": "string",
                "business_value": "string",
                "technical_approach": "string",
                "confidence": "number",
                "hypothesis": "boolean"
            },
            max_tokens=400,
            temperature=0.0,
            citations_required=False
        )
