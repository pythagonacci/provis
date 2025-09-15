"""
Python-specific detectors for routes, queues, stores, and policies with messy fallbacks.
Handles FastAPI, Flask, Django, Celery, and other Python frameworks.
"""
import re
import ast
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

from .config import settings
from .observability import record_fallback, record_detector_hit
from .models import EvidenceSpan, RouteModel

logger = logging.getLogger(__name__)

@dataclass
class DetectorResult:
    """Result of a detector operation."""
    items: List[Dict[str, Any]]
    confidence: float
    hypothesis: bool
    reason_code: Optional[str]
    evidence: List[EvidenceSpan]

class FastAPIDetector:
    """Detects FastAPI routes and dependencies."""
    
    def __init__(self):
        self.name = "fastapi"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect FastAPI routes."""
        routes = []
        evidence = []
        
        try:
            # Parse AST for precise decorator detection
            tree = ast.parse(content)
            
            # Detect route decorators
            ast_routes = self._detect_ast_routes(tree, file_path)
            routes.extend(ast_routes)
            
            # Messy fallback: regex detection
            if not routes and settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_routes = self._detect_regex_routes(content, file_path)
                routes.extend(regex_routes)
            
            if routes:
                record_detector_hit("fastapi_routes")
                return DetectorResult(
                    items=routes,
                    confidence=0.9 if not any(r.get("hypothesis", False) for r in routes) else 0.6,
                    hypothesis=any(r.get("hypothesis", False) for r in routes),
                    reason_code="factory-decorator" if any(r.get("hypothesis", False) for r in routes) else None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"FastAPI detection failed for {file_path}: {e}")
            # Fallback to regex
            if settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_routes = self._detect_regex_routes(content, file_path)
                if regex_routes:
                    return DetectorResult(
                        items=regex_routes,
                        confidence=0.3,
                        hypothesis=True,
                        reason_code="factory-decorator",
                        evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                    )
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_ast_routes(self, tree: ast.AST, file_path: Path) -> List[Dict[str, Any]]:
        """Detect routes using AST parsing."""
        routes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    route_info = self._extract_route_from_decorator(decorator, node, file_path)
                    if route_info:
                        routes.append(route_info)
        
        return routes
    
    def _extract_route_from_decorator(self, decorator: ast.expr, func_node: ast.FunctionDef, file_path: Path) -> Optional[Dict[str, Any]]:
        """Extract route information from a decorator."""
        # Handle @app.get("/path")
        if isinstance(decorator, ast.Attribute):
            if decorator.attr in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                method = decorator.attr.upper()
                
                # Try to get path from decorator arguments
                path = "/"
                if hasattr(decorator, 'parent') and isinstance(decorator.parent, ast.Call):
                    call_node = decorator.parent
                    if call_node.args and isinstance(call_node.args[0], ast.Constant):
                        path = call_node.args[0].value
                
                return {
                    "method": method,
                    "path": path,
                    "handler": func_node.name,
                    "middlewares": self._extract_dependencies(func_node),
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                    "confidence": 0.95,
                    "hypothesis": False,
                    "reason_code": None
                }
        
        # Handle @app.route("/path", methods=["GET"])
        elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if decorator.func.attr == 'route':
                # Extract path and methods
                path = "/"
                methods = ["GET"]
                
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    path = decorator.args[0].value
                
                # Look for methods keyword argument
                for keyword in decorator.keywords:
                    if keyword.arg == 'methods' and isinstance(keyword.value, ast.List):
                        methods = [elt.value.upper() if isinstance(elt, ast.Constant) else "GET" for elt in keyword.value.elts]
                
                # Create a route for each method
                return {
                    "method": methods[0] if methods else "GET",
                    "path": path,
                    "handler": func_node.name,
                    "middlewares": self._extract_dependencies(func_node),
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                    "confidence": 0.9,
                    "hypothesis": False,
                    "reason_code": None
                }
        
        return None
    
    def _extract_dependencies(self, func_node: ast.FunctionDef) -> List[str]:
        """Extract FastAPI dependencies from function."""
        dependencies = []
        
        # Look for Depends() calls in function arguments
        for arg in func_node.args.args:
            if arg.annotation:
                # This would need more sophisticated type analysis
                pass
        
        # Look for dependency injection in function body
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == 'Depends':
                    dependencies.append("Depends")
        
        return dependencies
    
    def _detect_regex_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Messy fallback: detect routes using regex."""
        routes = []
        
        # Pattern: @app.METHOD("/path")
        pattern = r"@\\w+\\.(get|post|put|delete|patch|options|head)\\s*\\(\\s*['\"]([^'\"]+)['\"]"
        for match in re.finditer(pattern, content, re.IGNORECASE):
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
        
        return routes

class FlaskDetector:
    """Detects Flask routes and blueprints."""
    
    def __init__(self):
        self.name = "flask"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Flask routes."""
        routes = []
        evidence = []
        
        try:
            # Parse AST for precise detection
            tree = ast.parse(content)
            
            # Detect route decorators
            ast_routes = self._detect_ast_routes(tree, file_path)
            routes.extend(ast_routes)
            
            # Detect blueprint routes
            blueprint_routes = self._detect_blueprint_routes(tree, file_path)
            routes.extend(blueprint_routes)
            
            # Messy fallback
            if not routes and settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_routes = self._detect_regex_routes(content, file_path)
                routes.extend(regex_routes)
            
            if routes:
                record_detector_hit("flask_routes")
                return DetectorResult(
                    items=routes,
                    confidence=0.9 if not any(r.get("hypothesis", False) for r in routes) else 0.6,
                    hypothesis=any(r.get("hypothesis", False) for r in routes),
                    reason_code="factory-decorator" if any(r.get("hypothesis", False) for r in routes) else None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Flask detection failed for {file_path}: {e}")
            # Fallback to regex
            if settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_routes = self._detect_regex_routes(content, file_path)
                if regex_routes:
                    return DetectorResult(
                        items=regex_routes,
                        confidence=0.3,
                        hypothesis=True,
                        reason_code="factory-decorator",
                        evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                    )
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_ast_routes(self, tree: ast.AST, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Flask routes using AST."""
        routes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    route_info = self._extract_route_from_decorator(decorator, node, file_path)
                    if route_info:
                        routes.append(route_info)
        
        return routes
    
    def _extract_route_from_decorator(self, decorator: ast.expr, func_node: ast.FunctionDef, file_path: Path) -> Optional[Dict[str, Any]]:
        """Extract route from Flask decorator."""
        # Handle @app.route("/path")
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if decorator.func.attr == 'route':
                # Extract path
                path = "/"
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    path = decorator.args[0].value
                
                # Extract methods
                methods = ["GET"]
                for keyword in decorator.keywords:
                    if keyword.arg == 'methods' and isinstance(keyword.value, ast.List):
                        methods = [elt.value.upper() if isinstance(elt, ast.Constant) else "GET" for elt in keyword.value.elts]
                
                return {
                    "method": methods[0] if methods else "GET",
                    "path": path,
                    "handler": func_node.name,
                    "middlewares": [],
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                    "confidence": 0.9,
                    "hypothesis": False,
                    "reason_code": None
                }
        
        return None
    
    def _detect_blueprint_routes(self, tree: ast.AST, file_path: Path) -> List[Dict[str, Any]]:
        """Detect blueprint routes."""
        routes = []
        
        # Look for Blueprint instantiation
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == 'Blueprint':
                    # Extract blueprint name and prefix
                    blueprint_name = "unknown"
                    blueprint_prefix = ""
                    
                    if node.args and isinstance(node.args[0], ast.Constant):
                        blueprint_name = node.args[0].value
                    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                        blueprint_prefix = node.args[1].value
                    
                    # Look for routes in this blueprint
                    blueprint_routes = self._find_blueprint_routes(tree, blueprint_name, blueprint_prefix, file_path)
                    routes.extend(blueprint_routes)
        
        return routes
    
    def _find_blueprint_routes(self, tree: ast.AST, blueprint_name: str, blueprint_prefix: str, file_path: Path) -> List[Dict[str, Any]]:
        """Find routes associated with a blueprint."""
        routes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute) and decorator.attr == 'route':
                        # This is a blueprint route
                        path = f"{blueprint_prefix}/"
                        if hasattr(decorator, 'parent') and isinstance(decorator.parent, ast.Call):
                            call_node = decorator.parent
                            if call_node.args and isinstance(call_node.args[0], ast.Constant):
                                path = f"{blueprint_prefix}{call_node.args[0].value}"
                        
                        routes.append({
                            "method": "GET",
                            "path": path,
                            "handler": node.name,
                            "middlewares": [],
                            "statusCodes": [],
                            "evidence": [EvidenceSpan(file=str(file_path), start=node.lineno, end=node.end_lineno or node.lineno)],
                            "confidence": 0.8,
                            "hypothesis": False,
                            "reason_code": None
                        })
        
        return routes
    
    def _detect_regex_routes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Messy fallback: detect Flask routes using regex."""
        routes = []
        
        # Pattern: @app.route("/path")
        pattern = r'@\w+\.route\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(pattern, content):
            path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": path,
                "handler": "unknown",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.3,
                "hypothesis": True,
                "reason_code": "factory-decorator"
            })
        
        return routes

class DjangoDetector:
    """Detects Django URLs and views."""
    
    def __init__(self):
        self.name = "django"
    
    def detect_routes(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Django URL patterns."""
        routes = []
        evidence = []
        
        try:
            # Detect URL patterns
            url_routes = self._detect_url_patterns(content, file_path)
            routes.extend(url_routes)
            
            # Detect view classes
            view_routes = self._detect_view_classes(content, file_path)
            routes.extend(view_routes)
            
            # Detect DRF routers
            drf_routes = self._detect_drf_routers(content, file_path)
            routes.extend(drf_routes)
            
            if routes:
                record_detector_hit("django_routes")
                return DetectorResult(
                    items=routes,
                    confidence=0.8,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Django detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_url_patterns(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Django URL patterns."""
        routes = []
        
        # Pattern: path('url/', view, name='name')
        pattern = r"path\s*\(\s*[\'\"]([^\'\"]+)[\'\"],\s*(\w+)"
        for match in re.finditer(pattern, content):
            path = match.group(1)
            view_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": path,
                "handler": view_name,
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        # Pattern: url(r'^url/$', view)
        url_pattern = r"url\s*\(\s*r?[\'\"]([^\'\"]+)[\'\"]"
        for match in re.finditer(url_pattern, content):
            path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": path,
                "handler": "unknown",
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.7,
                "hypothesis": False,
                "reason_code": None
            })
        
        return routes
    
    def _detect_view_classes(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Django view classes."""
        routes = []
        
        # Pattern: class ViewName(View)
        pattern = r'class\s+(\w+View)\s*\([^)]*View[^)]*\)'
        for match in re.finditer(pattern, content):
            view_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            routes.append({
                "method": "GET",
                "path": f"/{view_name.lower()}/",
                "handler": view_name,
                "middlewares": [],
                "statusCodes": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.6,
                "hypothesis": True,
                "reason_code": "factory-decorator"
            })
        
        return routes
    
    def _detect_drf_routers(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Django REST Framework routers."""
        routes = []
        
        # Pattern: router.register('resource', ViewSet)
        pattern = r"router\.register\s*\(\s*['\"]([^'\"]+)['\"],\s*(\w+)"
        for match in re.finditer(pattern, content):
            resource = match.group(1)
            viewset = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            # Generate standard REST endpoints
            for method in ['GET', 'POST', 'PUT', 'DELETE']:
                routes.append({
                    "method": method,
                    "path": f"/{resource}/",
                    "handler": viewset,
                    "middlewares": [],
                    "statusCodes": [],
                    "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                    "confidence": 0.8,
                    "hypothesis": False,
                    "reason_code": None
                })
        
        return routes

class CeleryDetector:
    """Detects Celery tasks and queues."""
    
    def __init__(self):
        self.name = "celery"
    
    def detect_jobs(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Celery tasks."""
        jobs = []
        evidence = []
        
        try:
            # Parse AST for precise detection
            tree = ast.parse(content)
            
            # Detect task decorators
            ast_jobs = self._detect_ast_tasks(tree, file_path)
            jobs.extend(ast_jobs)
            
            # Detect task definitions
            task_jobs = self._detect_task_definitions(tree, file_path)
            jobs.extend(task_jobs)
            
            # Messy fallback
            if not jobs and settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_jobs = self._detect_regex_tasks(content, file_path)
                jobs.extend(regex_jobs)
            
            if jobs:
                record_detector_hit("celery_tasks")
                return DetectorResult(
                    items=jobs,
                    confidence=0.9 if not any(j.get("hypothesis", False) for j in jobs) else 0.6,
                    hypothesis=any(j.get("hypothesis", False) for j in jobs),
                    reason_code="factory-decorator" if any(j.get("hypothesis", False) for j in jobs) else None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Celery detection failed for {file_path}: {e}")
            # Fallback to regex
            if settings.ENABLE_TOLERANT_STRING_LITERAL_SCAN:
                regex_jobs = self._detect_regex_tasks(content, file_path)
                if regex_jobs:
                    return DetectorResult(
                        items=regex_jobs,
                        confidence=0.3,
                        hypothesis=True,
                        reason_code="factory-decorator",
                        evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                    )
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_ast_tasks(self, tree: ast.AST, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Celery tasks using AST."""
        jobs = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    task_info = self._extract_task_from_decorator(decorator, node, file_path)
                    if task_info:
                        jobs.append(task_info)
        
        return jobs
    
    def _extract_task_from_decorator(self, decorator: ast.expr, func_node: ast.FunctionDef, file_path: Path) -> Optional[Dict[str, Any]]:
        """Extract task information from decorator."""
        # Handle @task decorator
        if isinstance(decorator, ast.Name) and decorator.id == 'task':
            return {
                "name": func_node.name,
                "type": "celery",
                "producer": "task.delay",
                "consumer": "worker",
                "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            }
        
        # Handle @app.task decorator
        elif isinstance(decorator, ast.Attribute) and decorator.attr == 'task':
            return {
                "name": func_node.name,
                "type": "celery",
                "producer": "task.delay",
                "consumer": "worker",
                "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            }
        
        # Handle @shared_task decorator
        elif isinstance(decorator, ast.Name) and decorator.id == 'shared_task':
            return {
                "name": func_node.name,
                "type": "celery",
                "producer": "shared_task.delay",
                "consumer": "worker",
                "evidence": [EvidenceSpan(file=str(file_path), start=func_node.lineno, end=func_node.end_lineno or func_node.lineno)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            }
        
        return None
    
    def _detect_task_definitions(self, tree: ast.AST, file_path: Path) -> List[Dict[str, Any]]:
        """Detect task definitions in code."""
        jobs = []
        
        # Look for function names that suggest tasks
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if any(keyword in node.name.lower() for keyword in ['task', 'job', 'worker', 'process']):
                    jobs.append({
                        "name": node.name,
                        "type": "celery",
                        "producer": "unknown",
                        "consumer": "worker",
                        "evidence": [EvidenceSpan(file=str(file_path), start=node.lineno, end=node.end_lineno or node.lineno)],
                        "confidence": 0.3,
                        "hypothesis": True,
                        "reason_code": "factory-decorator"
                    })
        
        return jobs
    
    def _detect_regex_tasks(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Messy fallback: detect Celery tasks using regex."""
        jobs = []
        
        # Pattern: @task or @app.task
        pattern = r'@(?:\w+\.)?task\s*\n\s*def\s+(\w+)'
        for match in re.finditer(pattern, content):
            task_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            jobs.append({
                "name": task_name,
                "type": "celery",
                "producer": "task.delay",
                "consumer": "worker",
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.3,
                "hypothesis": True,
                "reason_code": "factory-decorator"
            })
        
        return jobs

class PythonStoreDetector:
    """Detects Python data stores (SQLAlchemy, Django ORM, etc.)."""
    
    def __init__(self):
        self.name = "python_store"
    
    def detect_stores(self, file_path: Path, content: str) -> DetectorResult:
        """Detect Python data stores."""
        stores = []
        evidence = []
        
        try:
            # Detect SQLAlchemy models
            sqlalchemy_stores = self._detect_sqlalchemy_models(content, file_path)
            stores.extend(sqlalchemy_stores)
            
            # Detect Django models
            django_stores = self._detect_django_models(content, file_path)
            stores.extend(django_stores)
            
            # Detect raw SQL
            sql_stores = self._detect_raw_sql(content, file_path)
            stores.extend(sql_stores)
            
            if stores:
                record_detector_hit("python_stores")
                return DetectorResult(
                    items=stores,
                    confidence=0.9,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(file_path), start=1, end=1)]
                )
            
        except Exception as e:
            logger.warning(f"Python store detection failed for {file_path}: {e}")
        
        return DetectorResult([], 0.0, False, None, [])
    
    def _detect_sqlalchemy_models(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect SQLAlchemy models."""
        stores = []
        
        # Pattern: class ModelName(Base)
        pattern = r'class\s+(\w+)\s*\([^)]*Base[^)]*\)'
        for match in re.finditer(pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            stores.append({
                "name": model_name,
                "type": "sqlalchemy",
                "fields": [],
                "evidence": [EvidenceSpan(file=str(file_path), start=line_num, end=line_num)],
                "confidence": 0.9,
                "hypothesis": False,
                "reason_code": None
            })
        
        return stores
    
    def _detect_django_models(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Detect Django models."""
        stores = []
        
        # Pattern: class ModelName(models.Model)
        pattern = r'class\s+(\w+)\s*\([^)]*models\.Model[^)]*\)'
        for match in re.finditer(pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            stores.append({
                "name": model_name,
                "type": "django",
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

class PythonDetectorRegistry:
    """Registry for Python detectors."""
    
    def __init__(self):
        self.detectors = {
            'fastapi': FastAPIDetector(),
            'flask': FlaskDetector(),
            'django': DjangoDetector(),
            'celery': CeleryDetector(),
            'store': PythonStoreDetector(),
        }
    
    def detect_all(self, file_path: Path, content: str) -> Dict[str, DetectorResult]:
        """Run all Python detectors on a file."""
        results = {}
        
        for name, detector in self.detectors.items():
            try:
                if name in ['fastapi', 'flask', 'django']:
                    results[name] = detector.detect_routes(file_path, content)
                elif name == 'celery':
                    results[name] = detector.detect_jobs(file_path, content)
                elif name == 'store':
                    results[name] = detector.detect_stores(file_path, content)
            except Exception as e:
                logger.warning(f"Python detector {name} failed for {file_path}: {e}")
                results[name] = DetectorResult([], 0.0, True, "unknown", [])
        
        return results
