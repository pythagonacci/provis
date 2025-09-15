
"""
Robust detectors for routes, jobs, stores, and externals with messy fallbacks.
Handles dynamic patterns, factory decorators, and string literal scanning.
Enhanced with parallel execution and Tree-sitter integration for precise span detection.
"""
import re
import json
import ast
import concurrent.futures
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
import logging

from .config import settings
from .observability import record_fallback, record_detector_hit, record_phase_timing
from .models import EvidenceSpan, RouteModel, ImportModel
from .detector_tree_sitter import get_tree_sitter_detector
from .detector_reranker import get_reranker

logger = logging.getLogger(__name__)

@dataclass
class DetectorResult:
    """Result of a detector operation."""
    items: List[Dict[str, Any]]
    confidence: float
    hypothesis: bool
    reason_code: Optional[str]
    evidence: List[EvidenceSpan]
    
    def __init__(self, items: List[Dict[str, Any]], confidence: float, 
                 hypothesis: bool, reason_code: Optional[str], 
                 evidence: List[EvidenceSpan]):
        self.items = items
        self.confidence = confidence
        self.hypothesis = hypothesis
        self.reason_code = reason_code
        self.evidence = evidence

class NextJSDetector:
    """Detects Next.js routes and API endpoints."""
    
    def __init__(self):
        self.name = "nextjs"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Next.js routes from file path and content."""
        routes = []
        evidence = []
        
        try:
            # App Router detection
            if "app" in str(file_path):
                app_routes = self._detect_app_routes(file_path, content)
                routes.extend(app_routes)
                evidence.extend([EvidenceSpan(file=str(file_path), start=1, end=1)])
            
            # Pages Router detection
            elif "pages" in str(file_path):
                pages_routes = self._detect_pages_routes(file_path, content)
                routes.extend(pages_routes)
                evidence.extend([EvidenceSpan(file=str(file_path), start=1, end=1)])
            
            # API Routes detection
            if "api" in str(file_path) or file_path.name in ["route.ts", "route.js"]:
                api_routes = self._detect_api_routes(file_path, content)
                routes.extend(api_routes)
                evidence.extend([EvidenceSpan(file=str(file_path), start=1, end=1)])
            
            if routes:
                record_detector_hit("nextjs_routes", str(file_path))
                return DetectorResult(
                    items=routes,
                    confidence=0.9,
                    hypothesis=False,
                    reason_code=None,
                    evidence=evidence
                )
            
        except Exception as e:
            logger.warning(f"Next.js detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_app_routes(self, file_path: Path, content: str) -> List[Dict[str, Any]]:
        """Detect App Router routes."""
        routes = []
        
        # Extract route from file path
        path_parts = file_path.parts
        if "app" in path_parts:
            app_idx = path_parts.index("app")
            route_parts = path_parts[app_idx + 1:]
            
            # Remove file extensions and handle dynamic segments
            route_path = "/"
            for part in route_parts:
                if part.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    part = part.rsplit('.', 1)[0]
                
                if part == "page":
                    continue
                elif part.startswith("["):
                    # Dynamic segment
                    route_path += f"[{part[1:-1]}]/"
                else:
                    route_path += f"{part}/"
            
            route_path = route_path.rstrip("/") or "/"
            
            # Detect HTTP methods from content
            methods = self._extract_http_methods(content)
            for method in methods:
                routes.append({
                    "method": method,
                    "path": route_path,
                    "handler": "page",
                    "middlewares": [],
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=1, end=1)],
                    "confidence": 0.9,
                    "hypothesis": False,
                    "reason_code": None
                })
        
        return routes
    
    def _detect_pages_routes(self, file_path: Path, content: str) -> List[Dict[str, Any]]:
        """Detect Pages Router routes."""
        routes = []
        
        # Extract route from file path
        path_parts = file_path.parts
        if "pages" in path_parts:
            pages_idx = path_parts.index("pages")
            route_parts = path_parts[pages_idx + 1:]
            
            # Build route path
            route_path = "/"
            for part in route_parts:
                if part.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    part = part.rsplit('.', 1)[0]
                
                if part == "index":
                    continue
                elif part.startswith("["):
                    # Dynamic segment
                    route_path += f"[{part[1:-1]}]/"
                else:
                    route_path += f"{part}/"
            
            route_path = route_path.rstrip("/") or "/"
            
            # Default to GET for pages
            routes.append({
                "method": "GET",
                "path": route_path,
                "handler": "page",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=1, end=1)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_api_routes(self, file_path: Path, content: str) -> List[Dict[str, Any]]:
        """Detect API routes."""
        routes = []
        
        # Extract route from file path
        path_parts = file_path.parts
        if "api" in path_parts:
            api_idx = path_parts.index("api")
            route_parts = path_parts[api_idx + 1:]
            
            # Build API route path
            route_path = "/api/"
            for part in route_parts:
                if part.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    part = part.rsplit('.', 1)[0]
                
                if part.startswith("["):
                    # Dynamic segment
                    route_path += f"[{part[1:-1]}]/"
                else:
                    route_path += f"{part}/"
            
            route_path = route_path.rstrip("/")
            
            # Detect HTTP methods from content
            methods = self._extract_http_methods(content)
            for method in methods:
                routes.append({
                    "method": method,
                    "path": route_path,
                    "handler": "handler",
                    "middlewares": [],
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=1, end=1)],
                    "confidence": 0.9,
                    "hypothesis": False,
                    "reason_code": None
                })
        
        return routes
    
    def _extract_http_methods(self, content: str) -> List[str]:
        """Extract HTTP methods from content."""
        methods = set()
        
        # Look for named exports
        method_pattern = r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)'
        for match in re.finditer(method_pattern, content, re.IGNORECASE):
            methods.add(match.group(1).upper())
        
        # Look for method handlers
        handler_pattern = r'(?:const|let|var)\s+(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*='
        for match in re.finditer(handler_pattern, content, re.IGNORECASE):
            methods.add(match.group(1).upper())
        
        return list(methods) if methods else ["GET"]

class ExpressDetector:
    """Detects Express.js routes and middleware."""
    
    def __init__(self):
        self.name = "express"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Express routes with Tree-sitter precision and regex fallbacks."""
        routes = []
        evidence = []
        
        try:
            # Try Tree-sitter first for precise detection
            tree_sitter_detector = get_tree_sitter_detector()
            if tree_sitter_detector.available:
                # Determine language based on file extension
                lang = "javascript" if file_path.suffix in ['.js', '.jsx'] else "typescript"
                tree_sitter_routes = tree_sitter_detector.detect_route_patterns(content, file_path, lang)
                routes.extend(tree_sitter_routes)
                
                if tree_sitter_routes:
                    logger.debug(f"Tree-sitter detected {len(tree_sitter_routes)} Express routes in {file_path}")
            
            # Fallback to regex patterns if Tree-sitter didn't find routes
            if not routes:
                # Detect app.METHOD() calls
                app_routes = self._detect_app_routes(content, file_path)
                routes.extend(app_routes)
                
                # Detect router.METHOD() calls
                router_routes = self._detect_router_routes(content, file_path)
                routes.extend(router_routes)
                
                # Detect chained routes
                chained_routes = self._detect_chained_routes(content, file_path)
                routes.extend(chained_routes)
                
                # Messy fallback: string literal scanning with re-ranking
                if not routes and settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                    messy_routes = self._detect_string_literal_routes(content, file_path)
                    
                    # Re-rank messy candidates using semantic similarity
                    if messy_routes:
                        reranker = get_reranker()
                        messy_routes = reranker.rerank_route_candidates(messy_routes, content, str(file_path))
                        record_fallback("express_routes", str(file_path), "string-literal-fallback")
                    
                    routes.extend(messy_routes)
            
            if routes:
                record_detector_hit("express_routes", str(file_path))
                return DetectorResult(
                    items=routes,
                    confidence=0.8 if any(r.get("hypothesis", False) for r in routes) else 0.9,
                    hypothesis=any(r.get("hypothesis", False) for r in routes),
                    reason_code="factory-decorator" if any(r.get("hypothesis", False) for r in routes) else None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Express detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_app_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect app.METHOD() routes."""
        routes = []
        
        # Pattern: app.METHOD('/path', handler)
        pattern = r'(?:app|express)\.(get|post|put|delete|patch|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            method = match.group(1).upper()
            path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": method,
                "path": path,
                "handler": "handler",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_router_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect router.METHOD() routes."""
        routes = []
        
        # Pattern: router.METHOD('/path', handler)
        pattern = r'router\.(get|post|put|delete|patch|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            method = match.group(1).upper()
            path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": method,
                "path": path,
                "handler": "handler",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_chained_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect chained route definitions."""
        routes = []
        
        # Pattern: app.route('/path').METHOD(handler)
        pattern = r'(?:app|router)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\.(get|post|put|delete|patch|options|head)'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            path = match.group(1)
            method = match.group(2).upper()
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": method,
                "path": path,
                "handler": "handler",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_string_literal_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """
        Messy fallback: detect routes from string literals.
        
        Note: Evidence spans are coarse (line-level) for fallback patterns.
        Consider widening spans around matched regions for richer UI evidence.
        """
        routes = []
        
        # Look for HTTP verbs followed by path-like strings
        verb_pattern = r'\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b\s*[:\s]*[\'"](/[^\'"]*)[\'"]'
        for match in re.finditer(verb_pattern, content, re.IGNORECASE):
            method = match.group(1).upper()
            path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": method,
                "path": path,
                "handler": "unknown",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.3,
                "hypothesis": True,
                "reason_code": "factory-decorator"
            })
        
        if routes:
            record_fallback("express_routes", str(file_path), "regex-fallback")
        
        return routes

class ReactRouterDetector:
    """Detects React Router configurations."""
    
    def __init__(self):
        self.name = "react_router"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect React Router routes."""
        routes = []
        evidence = []
        
        try:
            # Detect createBrowserRouter
            browser_routes = self._detect_browser_router(content, file_path)
            routes.extend(browser_routes)
            
            # Detect JSX Routes
            jsx_routes = self._detect_jsx_routes(content, file_path)
            routes.extend(jsx_routes)
            
            if routes:
                record_detector_hit("react_router", str(file_path))
                return DetectorResult(
                    items=routes,
                    confidence=0.8,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"React Router detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_browser_router(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect createBrowserRouter configurations."""
        routes = []
        
        # Look for route objects
        route_pattern = r'{\s*path:\s*[\'"]([^\'"]+)[\'"],\s*element:'
        for match in re.finditer(route_pattern, content):
            path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": path,
                "handler": "component",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.8,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_jsx_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect JSX Route components."""
        routes = []
        
        # Look for <Route path="..." /> components
        route_pattern = r'<Route\s+path=[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(route_pattern, content):
            path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": path,
                "handler": "component",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.8,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes

class QueueDetector:
    """Detects job queues (Bull, BullMQ, Agenda, etc.)."""
    
    def __init__(self):
        self.name = "queue"
    
    def detect_jobs(self, file_path: Path, content: str) -> DetectorResult:
        """Detect job queue definitions."""
        jobs = []
        evidence = []
        
        try:
            # Bull/BullMQ detection
            bull_jobs = self._detect_bull_jobs(content, file_path)
            jobs.extend(bull_jobs)
            
            # Agenda detection
            agenda_jobs = self._detect_agenda_jobs(content, file_path)
            jobs.extend(agenda_jobs)
            
            # Generic job patterns
            generic_jobs = self._detect_generic_jobs(content, file_path)
            jobs.extend(generic_jobs)
            
            if jobs:
                record_detector_hit("queue_jobs", str(file_path))
                return DetectorResult(
                    items=jobs,
                    confidence=0.8,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Queue detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_bull_jobs(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Bull/BullMQ jobs."""
        jobs = []
        
        # Pattern: queue.add('jobName', data)
        pattern = r'queue\.add\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content):
            job_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            jobs.append({
                "name": job_name,
                "type": "bull",
                "producer": "queue.add",
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        # Pattern: queue.process('jobName', handler)
        process_pattern = r'queue\.process\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(process_pattern, content):
            job_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            jobs.append({
                "name": job_name,
                "type": "bull",
                "consumer": "queue.process",
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return jobs
    
    def _detect_agenda_jobs(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Agenda jobs."""
        jobs = []
        
        # Pattern: agenda.define('jobName', handler)
        pattern = r'agenda\.define\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content):
            job_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            jobs.append({
                "name": job_name,
                "type": "agenda",
                "consumer": "agenda.define",
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return jobs
    
    def _detect_generic_jobs(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect generic job patterns."""
        jobs = []
        
        # Look for job-related function names
        job_patterns = [
            r'function\s+(\w*[Jj]ob\w*)\s*\(',
            r'const\s+(\w*[Jj]ob\w*)\s*=',
            r'async\s+function\s+(\w*[Jj]ob\w*)\s*\('
        ]
        
        for pattern in job_patterns:
            for match in re.finditer(pattern, content):
                job_name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                
                jobs.append({
                    "name": job_name,
                    "type": "generic",
                    "producer": "unknown",
                    "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                    "confidence": 0.3,
                    "hypothesis": True,
                    "reason_code": "factory-decorator"
                })
        
        if jobs:
            record_fallback("queue_jobs", str(file_path), "regex-fallback")
        
        return jobs

class StoreDetector:
    """Detects data stores (Prisma, TypeORM, Sequelize, etc.)."""
    
    def __init__(self):
        self.name = "store"
    
    def detect_stores(self, file_path: Path, content: str) -> DetectorResult:
        """Detect data store definitions with Tree-sitter precision and regex fallbacks."""
        stores = []
        evidence = []
        
        try:
            # Try Tree-sitter first for precise model detection
            tree_sitter_detector = get_tree_sitter_detector()
            if tree_sitter_detector.available:
                # Determine language based on file extension
                lang = "python" if file_path.suffix == '.py' else "typescript"
                tree_sitter_models = tree_sitter_detector.detect_model_definitions(content, file_path, lang)
                stores.extend(tree_sitter_models)
                
                if tree_sitter_models:
                    logger.debug(f"Tree-sitter detected {len(tree_sitter_models)} models in {file_path}")
            
            # Fallback to regex patterns if Tree-sitter didn't find models
            if not stores:
                # Prisma detection
                prisma_stores = self._detect_prisma_models(content, file_path)
                stores.extend(prisma_stores)
                
                # TypeORM detection
                typeorm_stores = self._detect_typeorm_models(content, file_path)
                stores.extend(typeorm_stores)
                
                # Sequelize detection
                sequelize_stores = self._detect_sequelize_models(content, file_path)
                stores.extend(sequelize_stores)
                
                # Raw SQL detection
                sql_stores = self._detect_raw_sql(content, file_path)
                stores.extend(sql_stores)
            
            if stores:
                record_detector_hit("data_stores", str(file_path))
                return DetectorResult(
                    items=stores,
                    confidence=0.8,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Store detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_prisma_models(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Prisma models."""
        stores = []
        
        # Pattern: model ModelName { ... }
        pattern = r'model\s+(\w+)\s*{'
        for match in re.finditer(pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            stores.append({
                "name": model_name,
                "type": "prisma",
                "fields": [],  # Would extract fields
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.95,
                "hypothesis": False,
                "reason_code": None
            })
        
        return stores
    
    def _detect_typeorm_models(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect TypeORM models."""
        stores = []
        
        # Pattern: @Entity() class ModelName
        pattern = r'@Entity\s*\(\s*\)\s*class\s+(\w+)'
        for match in re.finditer(pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            stores.append({
                "name": model_name,
                "type": "typeorm",
                "fields": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return stores
    
    def _detect_sequelize_models(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Sequelize models."""
        stores = []
        
        # Pattern: sequelize.define('ModelName', ...)
        pattern = r'sequelize\.define\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            stores.append({
                "name": model_name,
                "type": "sequelize",
                "fields": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return stores
    
    def _detect_raw_sql(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect raw SQL patterns."""
        stores = []
        
        # Look for SQL table references
        sql_patterns = [
            r'CREATE\s+TABLE\s+(\w+)',
            r'INSERT\s+INTO\s+(\w+)',
            r'UPDATE\s+(\w+)\s+SET',
            r'DELETE\s+FROM\s+(\w+)',
            r'SELECT\s+.*\s+FROM\s+(\w+)'
        ]
        
        for pattern in sql_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                table_name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                
                stores.append({
                    "name": table_name,
                    "type": "sql",
                    "fields": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                    "confidence": 0.7,
                    "hypothesis": False,
                    "reason_code": None
                })
        
        return stores

class ExternalDetector:
    """Detects external service integrations."""
    
    def __init__(self):
        self.name = "external"
        self.known_sdks = {
            'stripe': ['stripe'],
            'aws': ['aws-sdk', '@aws-sdk'],
            'sendgrid': ['@sendgrid/mail'],
            'twilio': ['twilio'],
            'firebase': ['firebase'],
            'mongodb': ['mongodb'],
            'redis': ['redis', 'ioredis'],
            'elasticsearch': ['@elastic/elasticsearch'],
            'postgres': ['pg', 'postgres'],
            'mysql': ['mysql2'],
        }
    
    def detect_externals(self, file_path: Path, content: str) -> DetectorResult:
        """Detect external service integrations."""
        externals = []
        evidence = []
        
        try:
            # Detect known SDKs
            sdk_externals = self._detect_known_sdks(content, file_path)
            externals.extend(sdk_externals)
            
            # Detect custom wrappers
            wrapper_externals = self._detect_custom_wrappers(content, file_path)
            externals.extend(wrapper_externals)
            
            # Detect environment key usage
            env_externals = self._detect_env_usage(content, file_path)
            externals.extend(env_externals)
            
            if externals:
                record_detector_hit("external_services", str(file_path))
                return DetectorResult(
                    items=externals,
                    confidence=0.8,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"External detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_known_sdks(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect known SDK imports (ES6 and CommonJS)."""
        externals = []
        
        # Check for SDK imports
        for service, packages in self.known_sdks.items():
            for package in packages:
                # ES6 import: import ... from 'package'
                es6_pattern = rf'import.*from\s+[\'"]{re.escape(package)}[\'"]'
                # CommonJS require: require('package')
                commonjs_pattern = rf'require\s*\(\s*[\'"]{re.escape(package)}[\'"]\s*\)'
                
                if re.search(es6_pattern, content) or re.search(commonjs_pattern, content):
                    line_num = content.find(package)
                    line_num = content[:line_num].count('\n') + 1 if line_num >= 0 else 1
                    
                    externals.append({
                        "name": service,
                        "type": "sdk",
                        "package": package,
                        "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                        "confidence": 0.9,
                        "hypothesis": False,
                        "reason_code": None
                    })
        
        return externals
    
    def _detect_custom_wrappers(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect custom service wrappers."""
        externals = []
        
        # Look for service-like class names
        service_pattern = r'class\s+(\w*Service\w*)\s*{'
        for match in re.finditer(service_pattern, content):
            service_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            externals.append({
                "name": service_name,
                "type": "custom",
                "package": "unknown",
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.5,
                "hypothesis": True,
                "reason_code": "factory-decorator"
            })
        
        return externals
    
    def _detect_env_usage(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect environment variable usage."""
        externals = []
        
        # Look for process.env usage
        env_pattern = r'process\.env\.(\w+)'
        for match in re.finditer(env_pattern, content):
            env_key = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            # Skip common environment variables
            if env_key.lower() not in ['node_env', 'port', 'host', 'path']:
                externals.append({
                    "name": env_key,
                    "type": "env",
                    "package": "process.env",
                    "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                    "confidence": 0.3,
                    "hypothesis": True,
                    "reason_code": "factory-decorator"
                })
        
        return externals

class DetectorRegistry:
    """Registry for all detectors."""
    
    def __init__(self):
        self.detectors = {
            'nextjs': NextJSDetector(),
            'express': ExpressDetector(),
            'react_router': ReactRouterDetector(),
            'queue': QueueDetector(),
            'store': StoreDetector(),
            'external': ExternalDetector(),
        }
    
    def detect_all(self, file_path: Path, content: str) -> Dict[str, DetectorResult]:
        """Run all detectors on a file in parallel for 4x speedup."""
        start_time = time.time()
        results = {}
        
        # Define detector methods mapping
        detector_methods = {
            'nextjs': lambda d: d.detect_routes(file_path, content),
            'express': lambda d: d.detect_routes(file_path, content),
            'react_router': lambda d: d.detect_routes(file_path, content),
            'queue': lambda d: d.detect_jobs(file_path, content),
            'store': lambda d: d.detect_stores(file_path, content),
            'external': lambda d: d.detect_externals(file_path, content),
        }
        
        # Run detectors in parallel with ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all detector tasks
            futures = {
                executor.submit(detector_methods[name], detector): name 
                for name, detector in self.detectors.items()
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    logger.warning(f"Detector {name} failed for {file_path}: {e}")
                    results[name] = DetectorResult([], 0.0, True, "unknown", [])
        
        # Record timing metrics
        detection_time = time.time() - start_time
        record_phase_timing(f"detector_parallel_{len(self.detectors)}", detection_time)
        logger.debug(f"Parallel detector execution completed in {detection_time:.3f}s for {file_path}")
        
        return results
