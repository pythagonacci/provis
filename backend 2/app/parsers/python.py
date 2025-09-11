from __future__ import annotations
from pathlib import Path
import ast
import re
from typing import Dict, Any, List, Optional

try:
    import libcst as cst
    LIBCST_AVAILABLE = True
except ImportError:
    LIBCST_AVAILABLE = False

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


def _detect_django_routes(text: str, file_path: str, snapshot: Path = None, available_files: List[str] = None, visited: set = None) -> List[Dict[str, str]]:
    """Detect Django URL patterns including include() chains with recursive resolution."""
    if visited is None:
        visited = set()
    
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
            # Resolve include() chains recursively
            if snapshot and available_files:
                included_routes = _resolve_django_include(prefix, include_path, snapshot, available_files, visited)
                routes.extend(included_routes)
            else:
                # Fallback when we can't resolve
                routes.append({
                    "method": "GET",
                    "path": prefix,
                    "handler": f"include({include_path})"
                })
    
    return routes


def _resolve_django_include(prefix: str, include_path: str, snapshot: Path, available_files: List[str], visited: set) -> List[Dict[str, str]]:
    """Resolve Django include() chains by reading included URL files."""
    routes = []
    
    # Prevent infinite recursion
    include_key = f"{prefix}:{include_path}"
    if include_key in visited:
        return routes
    visited.add(include_key)
    
    # Convert include path to file path
    # e.g., "app.urls" -> "app/urls.py"
    include_file_path = include_path.replace(".", "/") + ".py"
    
    # Look for the file in available files
    matching_files = [f for f in available_files if f.endswith(include_file_path)]
    
    if matching_files:
        include_file = snapshot / matching_files[0]
        try:
            include_text = _read_text(include_file)
            # Recursively parse the included file
            included_routes = _detect_django_routes(include_text, str(include_file), snapshot, available_files, visited)
            
            # Prepend the prefix to all included routes
            for route in included_routes:
                # Handle path joining properly
                if prefix.endswith("/") and route["path"].startswith("/"):
                    full_path = prefix + route["path"][1:]
                elif prefix.endswith("/") or route["path"].startswith("/"):
                    full_path = prefix + route["path"]
                else:
                    full_path = prefix + "/" + route["path"]
                
                routes.append({
                    "method": route["method"],
                    "path": full_path,
                    "handler": route["handler"]
                })
        except Exception:
            # If we can't read the file, add a placeholder
            routes.append({
                "method": "GET",
                "path": prefix,
                "handler": f"include({include_path})"
            })
    else:
        # File not found, add placeholder
        routes.append({
            "method": "GET",
            "path": prefix,
            "handler": f"include({include_path})"
        })
    
    return routes


def _parse_dependencies(snapshot: Path) -> List[str]:
    """Parse requirements.txt and pyproject.toml to extract external dependencies."""
    dependencies = []
    
    # Parse requirements.txt
    requirements_file = snapshot / "requirements.txt"
    if requirements_file.exists():
        try:
            requirements_text = requirements_file.read_text(encoding="utf-8")
            for line in requirements_text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract package name (before ==, >=, etc.)
                    package = line.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].split("~=")[0]
                    if package:
                        dependencies.append(package)
        except Exception:
            pass
    
    # Parse pyproject.toml
    pyproject_file = snapshot / "pyproject.toml"
    if pyproject_file.exists():
        try:
            pyproject_text = pyproject_file.read_text(encoding="utf-8")
            # Simple regex to extract dependencies from [project.dependencies] or [tool.poetry.dependencies]
            dep_pattern = r'["\']([a-zA-Z0-9_-]+)["\']\s*=\s*["\'][^"\']+["\']'
            matches = re.findall(dep_pattern, pyproject_text)
            dependencies.extend(matches)
        except Exception:
            pass
    
    return list(set(dependencies))  # Remove duplicates


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


def _parse_with_libcst(text: str, file_path: str) -> Dict[str, Any]:
    """Use libcst for robust Python parsing with decorator and import resolution."""
    if not LIBCST_AVAILABLE:
        return None
        
    try:
        tree = cst.parse_expression(text) if text.strip().startswith('(') else cst.parse_statement(text)
        if not isinstance(tree, cst.Module):
            tree = cst.parse_module(text)
    except cst.ParserSyntaxError:
        # Fallback to ast if libcst fails
        return None
    
    result = {
        "imports": [],
        "exports": [],
        "functions": [],
        "classes": [],
        "routes": []
    }
    
    class ImportCollector(cst.CSTVisitor):
        def visit_Import(self, node: cst.Import) -> None:
            for alias in node.names:
                result["imports"].append({
                    "raw": alias.name.value,
                    "kind": "py"
                })
        
        def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
            module = node.module.value if node.module else ""
            for alias in node.names:
                if alias.name:
                    result["imports"].append({
                        "raw": f"{module}.{alias.name.value}" if module else alias.name.value,
                        "kind": "py"
                    })
    
    class FunctionCollector(cst.CSTVisitor):
        def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
            decorators = [self._extract_decorator_name(d) for d in node.decorators]
            params = [param.name.value for param in node.params.params]
            calls = self._extract_function_calls(node)
            
            result["functions"].append({
                "name": node.name.value,
                "params": params,
                "decorators": decorators,
                "calls": calls,
                "sideEffects": []
            })
        
        def visit_AsyncFunctionDef(self, node: cst.AsyncFunctionDef) -> None:
            decorators = [self._extract_decorator_name(d) for d in node.decorators]
            params = [param.name.value for param in node.params.params]
            calls = self._extract_function_calls(node)
            
            result["functions"].append({
                "name": node.name.value,
                "params": params,
                "decorators": decorators,
                "calls": calls,
                "sideEffects": []
            })
        
        def _extract_decorator_name(self, decorator: cst.Decorator) -> str:
            if isinstance(decorator.decorator, cst.Name):
                return decorator.decorator.value
            elif isinstance(decorator.decorator, cst.Attribute):
                return decorator.decorator.attr.value
            return "unknown"
        
        def _extract_function_calls(self, node: cst.FunctionDef | cst.AsyncFunctionDef) -> List[str]:
            calls = []
            for child in node.visit(lambda n: isinstance(n, cst.Call)):
                if isinstance(child.func, cst.Name):
                    calls.append(child.func.value)
                elif isinstance(child.func, cst.Attribute):
                    calls.append(child.func.attr.value)
            return calls
    
    class ClassCollector(cst.CSTVisitor):
        def visit_ClassDef(self, node: cst.ClassDef) -> None:
            methods = []
            base_classes = []
            
            for base in node.bases:
                if isinstance(base, cst.Name):
                    base_classes.append(base.value)
                elif isinstance(base, cst.Attribute):
                    base_classes.append(base.attr.value)
            
            for item in node.body.body:
                if isinstance(item, (cst.FunctionDef, cst.AsyncFunctionDef)):
                    methods.append(item.name.value)
            
            result["classes"].append({
                "name": node.name.value,
                "methods": methods,
                "baseClasses": base_classes
            })
    
    # Run collectors
    tree.visit(ImportCollector())
    tree.visit(FunctionCollector())
    tree.visit(ClassCollector())
    
    return result


def _parse_with_ast_fallback(text: str, tree: ast.AST) -> Dict[str, Any]:
    """Fallback AST parsing when libcst fails."""
    result = {
        "imports": [],
        "exports": [],
        "functions": [],
        "classes": [],
        "routes": []
    }
    
    # Extract imports
    for node in tree.body:
        if isinstance(node, ast.Import):
            for n in node.names:
                result["imports"].append({"raw": n.name, "kind": "py"})
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            result["imports"].append({"raw": mod, "kind": "py"})
    
    # Extract functions
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [_extract_decorator_name(d) for d in node.decorator_list]
            params = [arg.arg for arg in node.args.args]
            calls = _extract_function_calls(node)
            
            result["functions"].append({
                "name": node.name,
                "params": params,
                "decorators": decorators,
                "calls": calls,
                "sideEffects": []
            })
    
    # Extract classes
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            base_classes = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_classes.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_classes.append(base.attr)
            
            result["classes"].append({
                "name": node.name,
                "methods": methods,
                "baseClasses": base_classes
            })
    
    return result


def extract_pydantic_models(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract Pydantic models from Python code."""
    models = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases]
                if any("BaseModel" in str(b) or "BaseSettings" in str(b) for b in base_names):
                    fields = [n.target.id for n in ast.walk(node) if isinstance(n, ast.AnnAssign) and hasattr(n.target, "id")]
                    models.append({"name": node.name, "fields": fields, "path": path})
    except Exception:
        pass
    return models

def extract_sqlalchemy_models(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract SQLAlchemy models from Python code."""
    models = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases]
                if any("Base" in str(b) or "DeclarativeBase" in str(b) for b in base_names):
                    fields = []
                    for n in ast.walk(node):
                        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                            fn = getattr(n.value.func, "id", getattr(n.value.func, "attr", ""))
                            if str(fn).lower() == "column":
                                for t in n.targets:
                                    if hasattr(t, "id"): 
                                        fields.append(t.id)
                    models.append({"name": node.name, "fields": fields, "path": path})
    except Exception:
        pass
    return models

def extract_env_keys(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract environment variable keys from Python code."""
    keys = set()
    # Pattern for os.getenv() and os.environ[]
    patterns = [
        r'os\.getenv\(\s*[\'"]([A-Z0-9_]+)[\'"]\s*\)',
        r'environ\[\s*[\'"]([A-Z0-9_]+)[\'"]\s*\]',
        r'os\.environ\[\s*[\'"]([A-Z0-9_]+)[\'"]\s*\]'
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            keys.add(match.group(1))
    
    # Also extract from Pydantic Settings class attributes (uppercase field names)
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases]
                if any("BaseSettings" in str(b) for b in base_names):
                    for n in ast.walk(node):
                        if isinstance(n, ast.AnnAssign) and hasattr(n.target, "id"):
                            field_name = n.target.id
                            if field_name.isupper() and field_name.isidentifier():
                                keys.add(field_name)
    except Exception:
        pass
    
    return [{"type": "env", "key": k, "path": path} for k in sorted(keys)]

def extract_externals(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract external services from imports."""
    externals = []
    try:
        tree = ast.parse(text)
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("openai"): 
                        externals.append({"type": "api", "name": "OpenAI", "client": path})
                    if a.name in ("smtplib", "sendgrid"): 
                        externals.append({"type": "smtp", "name": "SMTP", "client": path})
            if isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                if mod.startswith("openai"): 
                    externals.append({"type": "api", "name": "OpenAI", "client": path})
                if mod in ("smtplib", "sendgrid"): 
                    externals.append({"type": "smtp", "name": "SMTP", "client": path})
    except Exception:
        pass
    return externals

def extract_fastapi_policies(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract FastAPI policies from Python code."""
    items = []
    if "add_middleware(" in text:
        items.append({"type": "middleware", "name": "add_middleware", "path": path})
    if "dependencies=[" in text and "Depends(" in text:
        items.append({"type": "middleware", "name": "dependencies(Depends)", "path": path})
    return items

def parse_python_file(p: Path, snapshot: Path = None, available_files: List[str] = None) -> Dict[str, Any]:
    """Parse Python file with robust libcst parsing and framework awareness."""
    text = _read_text(p)
    file_path = str(p).replace("\\", "/")
    
    # Try libcst first, fallback to ast
    parsed = _parse_with_libcst(text, file_path)
    if not parsed:
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
        
        # Fallback to ast parsing
        parsed = _parse_with_ast_fallback(text, tree)
    
    # Use parsed results from libcst or ast fallback
    imports = parsed.get("imports", [])
    functions = parsed.get("functions", [])
    classes = parsed.get("classes", [])
    
    # Add side effects to functions
    for func in functions:
        func["sideEffects"] = _detect_side_effects(text)
    
    # Detect routes based on framework
    routes = []
    hints = _detect_framework_hints(imports, text, file_path)
    
    if hints["framework"] == "fastapi":
        routes = _detect_fastapi_routes(tree)
    elif hints["framework"] == "flask":
        routes = _detect_flask_routes(tree)
    elif hints["framework"] == "django":
        routes = _detect_django_routes(text, file_path, snapshot, available_files)
    
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
    
    # Parse external dependencies
    external_dependencies = []
    if snapshot:
        external_dependencies = _parse_dependencies(snapshot)

    # Extract new structured data
    pydantic_models = extract_pydantic_models(text, file_path)
    sqlalchemy_models = extract_sqlalchemy_models(text, file_path)
    env_vars = extract_env_keys(text, file_path)
    externals = extract_externals(text, file_path)
    fastapi_policies = extract_fastapi_policies(text, file_path)

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
            "utilities": external_dependencies,  # External dependencies from requirements.txt/pyproject.toml
            # New structured data for capabilities
            "pydanticModels": pydantic_models,
            "sqlalchemyModels": sqlalchemy_models,
            "envVars": env_vars,
            "externals": externals,
            "fastapiPolicies": fastapi_policies
        },
        "hints": hints
    }
