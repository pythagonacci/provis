from __future__ import annotations
from pathlib import Path
import ast
import re
from typing import Dict, Any, List, Optional

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.read_text(encoding="latin-1", errors="ignore")


def _extract_decorator_name(decorator: ast.expr) -> str:
    """Extract decorator name from AST node."""
    if isinstance(decorator, ast.Name):
        return decorator.id
    elif isinstance(decorator, ast.Attribute):
        return f"{decorator.attr}"
    elif isinstance(decorator, ast.Call):
        if isinstance(decorator.func, ast.Name):
            return decorator.func.id
        elif isinstance(decorator.func, ast.Attribute):
            return decorator.func.attr
    return "unknown"


def _extract_route_from_decorator(decorator: ast.Call) -> Optional[Dict[str, str]]:
    """Extract route information from FastAPI/Flask decorator."""
    if not isinstance(decorator.func, ast.Attribute):
        return None
    
    method = decorator.func.attr.lower()
    if method not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
        return None
    
    # Extract path from decorator arguments
    if decorator.args and isinstance(decorator.args[0], ast.Constant):
        path = decorator.args[0].value
        return {
            "method": method.upper(),
            "path": path,
            "handler": "unknown"  # Will be filled by the calling function
        }
    
    return None


def _extract_route_from_flask_decorator(decorator: ast.Call) -> Optional[Dict[str, str]]:
    """Extract route information from Flask @app.route decorator."""
    if not isinstance(decorator.func, ast.Attribute):
        return None
    
    if decorator.func.attr != 'route':
        return None
    
    # Extract path from decorator arguments
    if decorator.args and isinstance(decorator.args[0], ast.Constant):
        path = decorator.args[0].value
        
        # Extract method from keywords
        method = "GET"  # default
        for keyword in decorator.keywords:
            if keyword.arg == 'methods' and isinstance(keyword.value, ast.List):
                if keyword.value.elts and isinstance(keyword.value.elts[0], ast.Constant):
                    method = keyword.value.elts[0].value.upper()
        
        return {
            "method": method,
            "path": path,
            "handler": "unknown"  # Will be filled by the calling function
        }
    
    return None


def _detect_django_routes(text: str, file_path: str) -> List[Dict[str, str]]:
    """Detect Django URL patterns including include() chains."""
    routes = []
    
    # Look for urlpatterns
    if "urlpatterns" in text:
        # Extract path() calls
        path_pattern = r'path\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([A-Za-z0-9_.]+)'
        matches = re.findall(path_pattern, text)
        
        for path, view in matches:
            routes.append({
                "method": "GET",  # Django defaults to GET
                "path": path,
                "handler": view
            })
        
        # Extract include() calls for nested URL patterns
        include_pattern = r'path\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*include\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        include_matches = re.findall(include_pattern, text)
        
        for prefix, include_path in include_matches:
            # Note: We can't resolve the include path without file system access
            # This would require a more sophisticated Django URL resolver
            routes.append({
                "method": "GET",
                "path": prefix,
                "handler": f"include({include_path})"
            })
    
    return routes


def _detect_django_models(tree: ast.AST) -> List[str]:
    """Detect Django model classes."""
    models = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if class inherits from models.Model
            for base in node.bases:
                if isinstance(base, ast.Attribute):
                    if (isinstance(base.value, ast.Name) and 
                        base.value.id == "models" and 
                        base.attr == "Model"):
                        models.append(node.name)
                elif isinstance(base, ast.Name) and base.id == "Model":
                    models.append(node.name)
    
    return models


def _detect_django_middleware(tree: ast.AST) -> List[str]:
    """Detect Django middleware classes."""
    middleware = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check for middleware patterns
            class_name = node.name.lower()
            if any(pattern in class_name for pattern in ["middleware", "interceptor", "filter"]):
                middleware.append(node.name)
            
            # Check for __call__ method (common in Django middleware)
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__call__":
                    middleware.append(node.name)
                    break
    
    return middleware


def _detect_fastapi_routes(tree: ast.AST) -> List[Dict[str, str]]:
    """Detect FastAPI routes from decorators."""
    routes = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
            for decorator in node.decorator_list:
                route_info = _extract_route_from_decorator(decorator)
                if route_info:
                    route_info["handler"] = node.name
                    routes.append(route_info)
    
    return routes


def _detect_flask_routes(tree: ast.AST) -> List[Dict[str, str]]:
    """Detect Flask routes from decorators."""
    routes = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    route_info = _extract_route_from_flask_decorator(decorator)
                    if route_info:
                        route_info["handler"] = node.name
                        routes.append(route_info)
    
    return routes


def _detect_framework_hints(imports: List[Dict[str, Any]], text: str, file_path: str) -> Dict[str, Any]:
    """Detect framework and route hints."""
    hints = {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False}
    
    import_names = [imp["raw"] for imp in imports]
    
    # FastAPI detection
    if any("fastapi" in name for name in import_names):
        hints["framework"] = "fastapi"
        hints["isAPI"] = True
        hints["isRoute"] = True
    
    # Flask detection
    elif any("flask" in name for name in import_names):
        hints["framework"] = "flask"
        hints["isAPI"] = True
        hints["isRoute"] = True
    
    # Django detection
    elif any("django" in name for name in import_names):
        hints["framework"] = "django"
        hints["isRoute"] = True
        if "urls.py" in file_path:
            hints["isAPI"] = True
    
    # Check for route decorators in text
    if "@app." in text or "@router." in text or "urlpatterns" in text:
        hints["isRoute"] = True
        hints["isAPI"] = True
    
    return hints


def _extract_function_calls(tree: ast.AST) -> List[str]:
    """Extract function calls from AST."""
    calls = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    
    return list(set(calls))


def _detect_side_effects(text: str) -> List[str]:
    """Detect side effects in Python code."""
    tags = []
    lower = text.lower()
    
    # Network calls
    if re.search(r"\b(requests|urllib|httpx|aiohttp)\b", lower):
        tags.append("net")
    
    # File I/O
    if re.search(r"\b(open|read|write|os\.|pathlib)\b", lower):
        tags.append("io")
    
    # Database
    if re.search(r"\b(sqlalchemy|django\.db|psycopg|pymongo|redis)\b", lower):
        tags.append("db")
    
    # Async operations
    if re.search(r"\b(async|await)\b", lower):
        tags.append("async")
    
    return list(dict.fromkeys(tags))


def parse_python_file(p: Path, snapshot: Path = None, available_files: List[str] = None) -> Dict[str, Any]:
    """Parse Python file with robust AST parsing and framework awareness."""
    text = _read_text(p)
    file_path = str(p).replace("\\", "/")
    
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Return minimal structure for syntax errors
        return {
            "imports": [],
            "exports": [],
            "functions": [],
            "classes": [],
            "routes": [],
            "symbols": {},
            "hints": {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False}
        }
    
    # Extract imports
    imports: List[Dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append({"raw": n.name, "kind": "py"})
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append({"raw": mod, "kind": "py"})
    
    # Extract functions with detailed information
    functions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [_extract_decorator_name(d) for d in node.decorator_list]
            params = [arg.arg for arg in node.args.args]
            calls = _extract_function_calls(node)
            
            functions.append({
                "name": node.name,
                "params": params,
                "decorators": decorators,
                "calls": calls,
                "sideEffects": _detect_side_effects(ast.unparse(node) if hasattr(ast, 'unparse') else text)
            })
    
    # Extract classes with detailed information
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            base_classes = [base.id if isinstance(base, ast.Name) else "unknown" for base in node.bases]
            
            classes.append({
                "name": node.name,
                "methods": methods,
                "baseClasses": base_classes
            })
    
    # Detect routes based on framework
    routes = []
    hints = _detect_framework_hints(imports, text, file_path)
    
    if hints["framework"] == "fastapi":
        routes = _detect_fastapi_routes(tree)
    elif hints["framework"] == "flask":
        routes = _detect_flask_routes(tree)
    elif hints["framework"] == "django":
        routes = _detect_django_routes(text, file_path)
    
    # Update hints based on detected routes
    if routes:
        hints["isRoute"] = True
        hints["isAPI"] = True
    
    # Resolve imports if we have the necessary context
    resolved_imports = []
    if snapshot and available_files:
        from app.parsers.base import resolve_import
        for imp in imports:
            resolved_path, is_external = resolve_import(imp["raw"], file_path, snapshot, available_files)
            resolved_imports.append({
                "raw": imp["raw"],
                "resolved": resolved_path,
                "external": is_external,
                "kind": imp["kind"]
            })
    else:
        # Fallback to original imports without resolution
        resolved_imports = imports
    
    # Detect database models and middleware
    db_models = []
    middleware = []
    
    # Always detect Django models if present (regardless of framework detection)
    django_models = _detect_django_models(tree)
    if django_models:
        db_models.extend(django_models)
        hints["framework"] = "django"  # Update framework hint if Django models found
    
    # Also check generic ORM patterns
    for cls in classes:
        # Check if class inherits from common ORM base classes
        if any(base in ["Model", "BaseModel", "models.Model"] for base in cls.get("baseClasses", [])):
            if cls["name"] not in db_models:  # Avoid duplicates
                db_models.append(cls["name"])
    
    # Detect middleware
    if hints["framework"] == "django":
        # Use Django-specific middleware detection
        middleware = _detect_django_middleware(tree)
    else:
        # Generic middleware detection
        for func in functions:
            # Check for common middleware patterns
            if any(pattern in func["name"].lower() for pattern in ["middleware", "interceptor", "filter"]):
                middleware.append(func["name"])

    return {
        "imports": resolved_imports,
        "exports": [],  # Python doesn't use explicit exports
        "functions": functions,
        "classes": classes,
        "routes": routes,
        "symbols": {
            "constants": [],  # Could be extracted from AST
            "hooks": [],      # Not applicable to Python
            "dbModels": db_models,
            "middleware": middleware,
            "components": [], # Not applicable to Python
            "utilities": []   # Could be detected
        },
        "hints": hints
    }
