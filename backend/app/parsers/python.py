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


def _ast_value_to_py(node):
    """Convert AST node to Python value or readable string."""
    import ast
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str):  # Python < 3.8
        return node.s
    elif isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    elif isinstance(node, ast.NameConstant):  # Python < 3.8
        return node.value
    elif isinstance(node, ast.List):
        return [_ast_value_to_py(elt) for elt in node.elts]
    elif isinstance(node, ast.Dict):
        return {_ast_value_to_py(k): _ast_value_to_py(v) for k, v in zip(node.keys, node.values)}
    elif isinstance(node, ast.Call):
        # Special case for Field(default_factory=list)
        fn = getattr(node.func, "id", None)
        if fn == "Field":
            for kw in node.keywords or []:
                if kw.arg == "default_factory":
                    factory_name = getattr(kw.value, "id", "list")
                    return f"Field(default_factory={factory_name})"
        # Try to unparse if available (Python 3.9+)
        if hasattr(ast, "unparse"):
            try:
                return ast.unparse(node)
            except:
                pass
        return "call(...)"
    elif isinstance(node, ast.Name):
        return node.id
    else:
        return str(type(node).__name__)

def is_pydantic_model(t) -> bool:
    """Check if type annotation is a Pydantic model."""
    if t is None:
        return False
    try:
        # Check for BaseModel in MRO
        if hasattr(t, '__mro__'):
            for base in t.__mro__:
                if hasattr(base, '__module__') and 'pydantic' in base.__module__:
                    if hasattr(base, '__name__') and 'BaseModel' in base.__name__:
                        return True
        # Check for model_fields attribute (Pydantic v2)
        if hasattr(t, 'model_fields'):
            return True
        # Check for __fields__ attribute (Pydantic v1)
        if hasattr(t, '__fields__'):
            return True
    except:
        pass
    return False

def example_for_type(t) -> Any:
    """Generate sensible example values for type annotations."""
    if t is None:
        return None
    
    type_str = str(t).lower()
    
    # String types
    if 'str' in type_str or 'string' in type_str:
        if 'email' in type_str:
            return "user@example.com"
        elif 'url' in type_str:
            return "https://example.com"
        elif 'uuid' in type_str:
            return "123e4567-e89b-12d3-a456-426614174000"
        else:
            return "example_string"
    
    # Numeric types
    elif 'int' in type_str:
        return 42
    elif 'float' in type_str:
        return 3.14
    elif 'bool' in type_str:
        return True
    
    # Collection types
    elif 'list' in type_str or 'array' in type_str:
        return ["item1", "item2"]
    elif 'dict' in type_str or 'mapping' in type_str:
        return {"key": "value"}
    elif 'set' in type_str:
        return ["item1", "item2"]
    
    # Date/time types
    elif 'datetime' in type_str:
        return "2025-01-01T12:00:00Z"
    elif 'date' in type_str:
        return "2025-01-01"
    elif 'time' in type_str:
        return "12:00:00"
    
    # Default fallback
    else:
        return "example_value"

def example_for_sqla_type(sqla_type_str: str) -> Any:
    """Generate examples for SQLAlchemy column types."""
    type_str = str(sqla_type_str).lower()
    
    if 'integer' in type_str or 'int' in type_str:
        return 1
    elif 'string' in type_str or 'text' in type_str or 'varchar' in type_str:
        return "example_text"
    elif 'boolean' in type_str or 'bool' in type_str:
        return True
    elif 'datetime' in type_str:
        return "2025-01-01T12:00:00Z"
    elif 'float' in type_str or 'numeric' in type_str:
        return 1.0
    elif 'json' in type_str:
        return {"key": "value"}
    else:
        return "example_value"

def extract_request_schema(text: str, path: str, route_info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract request schema from FastAPI route function."""
    import ast
    import typing
    
    try:
        tree = ast.parse(text)
        
        # Find the route function
        func_name = route_info.get("handler")
        if not func_name:
            return {}
        
        # Find function definition
        func_def = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                func_def = node
                break
        
        if not func_def:
            return {}
        
        # Extract type hints
        fields = []
        example = {}
        model_name = None
        path_params = []
        query_params = []
        
        # Parse function parameters
        for arg in func_def.args.args:
            if arg.arg == "self":  # Skip self parameter
                continue
                
            # Try to get type annotation
            ann = None
            if arg.annotation:
                try:
                    # Simple type resolution
                    ann_str = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else str(arg.annotation)
                    ann = ann_str
                except:
                    ann = str(arg.annotation)
            
            # Check if it's a Pydantic model
            if ann and ("BaseModel" in ann or "Request" in ann):
                model_name = ann
                # This would be a request body model
                fields.append({
                    "name": arg.arg,
                    "type": ann,
                    "required": True
                })
                example[arg.arg] = example_for_type(ann)
            else:
                # Regular parameter
                param_info = {
                    "name": arg.arg,
                    "type": ann or "str",
                    "required": True
                }
                
                # Determine if it's path or query param based on route pattern
                route_path = route_info.get("route", "")
                if f"{{{arg.arg}}}" in route_path:
                    path_params.append(param_info)
                else:
                    query_params.append(param_info)
                
                example[arg.arg] = example_for_type(ann)
        
        return {
            "name": model_name,
            "fields": fields,
            "example": example,
            "pathParams": path_params,
            "queryParams": query_params
        }
        
    except Exception as e:
        return {"error": str(e)}

def extract_response_schema(text: str, path: str, route_info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract response schema from FastAPI route."""
    import ast
    
    try:
        tree = ast.parse(text)
        
        # Find the route function
        func_name = route_info.get("handler")
        if not func_name:
            return {}
        
        # Find function definition
        func_def = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                func_def = node
                break
        
        if not func_def:
            return {}
        
        # Check for FileResponse or StreamingResponse in return type
        if func_def.returns:
            return_type = ast.unparse(func_def.returns) if hasattr(ast, "unparse") else str(func_def.returns)
            if "FileResponse" in return_type:
                return {
                    "type": "file",
                    "mime": "application/pdf",  # Default for this app
                    "example": {"filename": "deck.pdf"}
                }
            elif "StreamingResponse" in return_type:
                return {
                    "type": "stream",
                    "mime": "application/octet-stream",
                    "example": {"stream": "binary_data"}
                }
        
        # Look for response_model in decorator
        for decorator in func_def.decorator_list:
            if isinstance(decorator, ast.Call):
                # Check for response_model keyword argument
                for kw in decorator.keywords or []:
                    if kw.arg == "response_model":
                        model_name = ast.unparse(kw.value) if hasattr(ast, "unparse") else str(kw.value)
                        return {
                            "type": "json",
                            "schema": {
                                "name": model_name,
                                "fields": []  # Would need to extract from model definition
                            },
                            "example": {"id": 1, "status": "success"}
                        }
        
        # Default JSON response
        return {
            "type": "json",
            "schema": {"name": "Response", "fields": []},
            "example": {"status": "success"}
        }
        
    except Exception as e:
        return {"type": "json", "schema": {"name": "Response", "fields": []}, "example": {"status": "success"}}

def extract_store_model(text: str, path: str, model_name: str) -> Dict[str, Any]:
    """Extract SQLAlchemy model details."""
    import ast
    
    try:
        tree = ast.parse(text)
        
        # Find the model class
        model_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == model_name:
                model_class = node
                break
        
        if not model_class:
            return {}
        
        # Extract columns
        fields = []
        example = {}
        
        for item in model_class.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        col_name = target.id
                        
                        # Skip relationship attributes
                        if col_name in ["decks", "emails", "prospect"]:
                            continue
                            
                        # Get column type
                        col_type = "str"  # default
                        if isinstance(item.value, ast.Call):
                            if hasattr(item.value.func, "id"):
                                col_type = item.value.func.id
                        
                        nullable = True  # default
                        example[col_name] = example_for_sqla_type(col_type)
                        
                        fields.append({
                            "name": col_name,
                            "type": col_type,
                            "nullable": nullable
                        })
        
        return {
            "dbModel": model_name,
            "table": model_name.lower() + "s",  # Simple pluralization
            "fields": fields,
            "example": example
        }
        
    except Exception as e:
        return {"error": str(e)}

def detect_externals(text: str, path: str) -> List[Dict[str, Any]]:
    """Detect external service calls in Python code."""
    import ast
    
    externals = []
    
    try:
        tree = ast.parse(text)
        
        # Check imports for external libraries
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "openai":
                        externals.append({
                            "service": "openai",
                            "actor": path,
                            "sends": {"prompt": "string", "params": "dict"},
                            "returns": {"type": "json", "shape": "ChatCompletion"},
                            "usedFor": "LLM content generation"
                        })
            elif isinstance(node, ast.ImportFrom):
                if node.module == "openai":
                    externals.append({
                        "service": "openai", 
                        "actor": path,
                        "sends": {"prompt": "string", "params": "dict"},
                        "returns": {"type": "json", "shape": "ChatCompletion"},
                        "usedFor": "LLM content generation"
                    })
                elif "smtp" in (node.module or ""):
                    externals.append({
                        "service": "smtp",
                        "actor": path,
                        "sends": {"to": "email", "subject": "string", "body": "string"},
                        "returns": {"type": "status", "shape": "bool"},
                        "usedFor": "Email delivery"
                    })
        
    except Exception as e:
        pass
    
    return externals

def build_module_index(repo_root: str) -> Dict[str, str]:
    """Build bidirectional module ↔ path mapping."""
    import os
    from pathlib import Path
    
    module_index = {}
    repo_path = Path(repo_root)
    
    # Walk through Python files and build module paths
    for py_file in repo_path.rglob("*.py"):
        if "node_modules" in str(py_file) or "__pycache__" in str(py_file):
            continue
            
        # Convert file path to module path
        rel_path = py_file.relative_to(repo_path)
        module_parts = list(rel_path.parts)
        module_parts[-1] = module_parts[-1][:-3]  # Remove .py
        
        # Handle __init__.py files
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        
        if module_parts:
            module_name = ".".join(module_parts)
            module_index[module_name] = str(rel_path)
            module_index[str(rel_path)] = module_name
    
    return module_index

def example_for_model(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate example payload from model fields."""
    SAMPLE = {
        'str': 'example',
        'int': 1,
        'EmailStr': 'user@example.com',
        'UUID': '00000000-0000-0000-0000-000000000000',
        'bool': True,
        'float': 3.14,
        'datetime': '2025-01-01T12:00:00Z',
        'list': ['item1', 'item2'],
        'dict': {'key': 'value'}
    }
    
    example = {}
    for field in fields:
        field_type = field.get('type', 'str').lower()
        field_name = field.get('name', 'field')
        
        # Find best match in SAMPLE
        sample_value = None
        for sample_type, sample_val in SAMPLE.items():
            if sample_type.lower() in field_type:
                sample_value = sample_val
                break
        
        if sample_value is None:
            sample_value = SAMPLE.get('str', 'example')
        
        example[field_name] = sample_value
    
    return example

def find_touches(item_path: str, control_flow: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find control flow edges that touch this data item."""
    touches = []
    for edge in control_flow:
        if edge.get("from") == item_path or edge.get("to") == item_path:
            touches.append({
                "edge": edge,
                "via": edge.get("kind", "call"),
                "actor": edge.get("from") if edge.get("to") == item_path else edge.get("to"),
                "action": "reads/writes" if edge.get("to") == item_path else "provides"
            })
    return touches

def build_module_index(repo_root: str) -> Dict[str, str]:
    """Build bidirectional module ↔ path mapping."""
    import os
    from pathlib import Path
    
    module_index = {}
    repo_path = Path(repo_root)
    
    # Walk through Python files and build module paths
    for py_file in repo_path.rglob("*.py"):
        if "node_modules" in str(py_file) or "__pycache__" in str(py_file):
            continue
            
        # Convert file path to module path
        rel_path = py_file.relative_to(repo_path)
        module_parts = list(rel_path.parts)
        module_parts[-1] = module_parts[-1][:-3]  # Remove .py
        
        # Handle __init__.py files
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        
        if module_parts:
            module_name = ".".join(module_parts)
            module_index[module_name] = str(rel_path)
            module_index[str(rel_path)] = module_name
    
    return module_index

def build_module_index_v2(repo_root: Path) -> tuple[Dict[str, str], Dict[str, str]]:
    """Build bidirectional module ↔ path mapping with proper package handling."""
    file_to_mod, mod_to_file = {}, {}
    repo_path = Path(repo_root)
    
    # Walk through Python files and build module paths
    for py_file in repo_path.rglob("*.py"):
        if "node_modules" in str(py_file) or "__pycache__" in str(py_file):
            continue
            
        # Convert file path to module path
        rel_path = py_file.relative_to(repo_path)
        
        # Build package parts by walking up __init__.py parents
        pkg_parts = []
        p = py_file.parent
        while (p / "__init__.py").exists() and p != repo_path:
            pkg_parts.insert(0, p.name)
            p = p.parent
        
        # Add the file name (without .py)
        module_name = ".".join(pkg_parts + [py_file.stem])
        
        # Skip __init__.py files (they're represented by their package)
        if py_file.name != "__init__.py":
            file_to_mod[str(rel_path)] = module_name
            mod_to_file[module_name] = str(rel_path)
    
    return file_to_mod, mod_to_file

def resolve_any(ref: str, file_to_mod: Dict[str, str], mod_to_file: Dict[str, str]) -> str:
    """Resolve either module name or file path to canonical file path."""
    # If it's already a module name, convert to file path
    if ref in mod_to_file:
        return mod_to_file[ref]
    
    # If it's already a file path, return as-is
    if ref in file_to_mod:
        return ref
    
    # Handle dotted imports (e.g., "models.prospect" -> "backend/app/models/prospect.py")
    if "." in ref and ":" not in ref:
        return mod_to_file.get(ref, ref)
    
    # Handle imports with line numbers (e.g., "config.py:42")
    if ":" in ref:
        base_ref = ref.split(":")[0]
        if base_ref in mod_to_file:
            return mod_to_file[base_ref]
        return base_ref
    
    return ref

def extract_file_summary(text: str, path: str) -> str:
    """Extract file summary from docstrings and comments."""
    import ast
    
    try:
        tree = ast.parse(text)
        
        # Get module docstring
        if (tree.body and isinstance(tree.body[0], ast.Expr) and 
            isinstance(tree.body[0].value, ast.Constant) and 
            isinstance(tree.body[0].value.value, str)):
            return tree.body[0].value.value.strip()
        
        # Get first class/function docstring
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                    return node.body[0].value.value.strip()
        
        # Infer from file path and content
        if "/routers/" in path:
            return "FastAPI router with API endpoints for the application."
        elif "/models/" in path:
            return "SQLAlchemy database models defining data structures."
        elif "/schemas/" in path:
            return "Pydantic schemas for request/response validation."
        elif "/services/" in path:
            return "Business logic and external service integrations."
        elif "/config" in path:
            return "Application configuration and environment settings."
        else:
            return "Supporting module for the application."
            
    except Exception as e:
        return f"Module at {path}"

def iter_py_files(repo_root: Path):
    """Iterate over Python files, skipping virtualenvs and hidden directories."""
    for p in repo_root.rglob("*.py"):
        # skip virtualenvs, hidden, tests, and runs by common patterns
        if any(seg.startswith((".", "__pycache__", "venv", "env")) for seg in p.parts):
            continue
        if "runs/" in str(p.relative_to(repo_root)):
            continue
        yield p

def collect_pydantic_models(repo_root: Path):
    """
    Returns dict[name] = {
        "path": str, "kind": "pydantic.Model",
        "fields": [field_names]
    }
    """
    import ast
    out = {}
    for f in iter_py_files(repo_root):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            # detect `class X(BaseModel):` and gather annotated Assign targets
            base_model_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and "pydantic" in node.module:
                    for n in node.names:
                        if n.name == "BaseModel":
                            base_model_names.add("BaseModel")
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.bases:
                    if any(getattr(b, "id", None) == "BaseModel" or getattr(getattr(b, "attr", None), "lower", lambda: "" )() == "basemodel" for b in node.bases):
                        fields = []
                        for stmt in node.body:
                            if isinstance(stmt, ast.AnnAssign) and hasattr(stmt.target, "id"):
                                fields.append(stmt.target.id)
                        out[node.name] = {
                            "path": str(f.relative_to(repo_root)),
                            "kind": "pydantic.Model",
                            "fields": fields
                        }
        except Exception:
            continue
    return out

def collect_sqlalchemy_models(repo_root: Path):
    """
    Returns list of {
      "type": "dbModel", "name": <ModelName>, "path": <file>,
      "fields": [col_names]
    }
    """
    import ast
    results = []
    for f in iter_py_files(repo_root):
        try:
            src = f.read_text(encoding="utf-8")
            if "sqlalchemy" not in src or "Base" not in src:
                continue
            tree = ast.parse(src, filename=str(f))
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
                # Check if class inherits from Base (SQLAlchemy model)
                is_sqlalchemy = False
                for base in cls.bases:
                    if isinstance(base, ast.Name) and base.id == "Base":
                        is_sqlalchemy = True
                        break
                    elif isinstance(base, ast.Attribute) and base.attr == "Base":
                        is_sqlalchemy = True
                        break
                
                if is_sqlalchemy:
                    # Extract column names with types
                    cols = []
                    for stmt in cls.body:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Name):
                                    # Check if the assignment is a Column
                                    if isinstance(stmt.value, ast.Call):
                                        if isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "Column":
                                            # Extract type from Column arguments
                                            col_type = "String"
                                            if stmt.value.args:
                                                if isinstance(stmt.value.args[0], ast.Name):
                                                    col_type = stmt.value.args[0].id
                                                elif isinstance(stmt.value.args[0], ast.Attribute):
                                                    col_type = stmt.value.args[0].attr
                                            cols.append({"name": target.id, "type": col_type, "nullable": True, "primary_key": False})
                                        elif isinstance(stmt.value.func, ast.Attribute) and stmt.value.func.attr == "Column":
                                            # Extract type from Column arguments
                                            col_type = "String"
                                            if stmt.value.args:
                                                if isinstance(stmt.value.args[0], ast.Name):
                                                    col_type = stmt.value.args[0].id
                                                elif isinstance(stmt.value.args[0], ast.Attribute):
                                                    col_type = stmt.value.args[0].attr
                                            cols.append({"name": target.id, "type": col_type, "nullable": True, "primary_key": False})
                    if cols:
                        results.append({
                            "type": "dbModel",
                            "name": cls.name,
                            "path": str(f.relative_to(repo_root)),
                            "fields": cols
                        })
        except Exception:
            continue
    return results

def find_fastapi_routes(repo_root: Path):
    """
    Returns list of {
      "file": <path>,
      "method": <get|post|put|...>,
      "route": <string>,
      "func": <function name>,
      "params": [{"name": ..., "annotation": "ModelName" or None}],
      "response_model": "ModelName" or None,
      "decorator_lineno": int
    }
    """
    import ast
    routes = []
    for f in iter_py_files(repo_root):
        try:
            src = f.read_text(encoding="utf-8")
            if "APIRouter(" not in src and ".route(" not in src and ".get(" not in src:
                continue
            t = ast.parse(src, filename=str(f))
            for node in t.body:
                if isinstance(node, ast.FunctionDef) and node.decorator_list:
                    for dec in node.decorator_list:
                        # match @router.post("/path", response_model=Model)
                        method = None
                        route = None
                        response_model = None
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                            if dec.func.attr in {"get","post","put","delete","patch"}:
                                method = dec.func.attr
                                # first arg is route
                                if dec.args and isinstance(dec.args[0], (ast.Str, ast.Constant)):
                                    route = getattr(dec.args[0], "s", None) or getattr(dec.args[0], "value", None)
                                for kw in dec.keywords or []:
                                    if kw.arg == "response_model":
                                        # response_model can be Name or Attribute
                                        if isinstance(kw.value, ast.Name):
                                            response_model = kw.value.id
                                        elif isinstance(kw.value, ast.Attribute):
                                            response_model = kw.value.attr
                        if method and route:
                            params = []
                            for a in node.args.args:
                                ann = None
                                if a.annotation:
                                    if isinstance(a.annotation, ast.Name):
                                        ann = a.annotation.id
                                    elif isinstance(a.annotation, ast.Subscript) and isinstance(a.annotation.value, ast.Name):
                                        ann = a.annotation.value.id
                                    elif isinstance(a.annotation, ast.Attribute):
                                        ann = a.annotation.attr
                                params.append({"name": a.arg, "annotation": ann})
                            routes.append({
                                "file": str(f.relative_to(repo_root)),
                                "method": method,
                                "route": route,
                                "func": node.name,
                                "params": params,
                                "response_model": response_model,
                                "decorator_lineno": getattr(dec, "lineno", node.lineno)
                            })
        except Exception:
            continue
    return routes

def link_request_models(routes, model_index):
    """Link FastAPI routes to Pydantic request models."""
    items = []
    for r in routes:
        for p in r["params"]:
            mname = p["annotation"]
            if not mname: 
                continue
            if mname in model_index:
                m = model_index[mname]
                items.append({
                    "type": "requestSchema",
                    "name": mname,
                    "path": m["path"],
                    "fields": m["fields"],
                    "referencedAt": f'{r["file"]}:{r["decorator_lineno"]}',
                    "route": r["route"]
                })
    # de-dupe by (name, path, route)
    seen = set()
    uniq = []
    for it in items:
        key = (it["name"], it["path"], it["route"])
        if key in seen: 
            continue
        seen.add(key)
        uniq.append(it)
    return uniq

def detect_response_models(routes, model_index):
    """Detect FastAPI response models."""
    out = []
    for r in routes:
        rm = r.get("response_model")
        if rm and rm in model_index:
            m = model_index[rm]
            out.append({
                "type": "responseSchema",
                "name": rm,
                "path": m["path"],
                "fields": m["fields"],
                "route": r["route"]
            })
    return out

def detect_artifact_outputs(repo_root: Path):
    """Detect artifact outputs (PDFs, slides, emails)."""
    items = []
    for f in iter_py_files(repo_root):
        try:
            p = f.as_posix().lower()
            src = f.read_text(encoding="utf-8", errors="ignore").lower()
            if "pdf" in p or "services/pdf" in p or "render" in src and "pdf" in src:
                items.append({"type":"artifact","name":"pdf","path": str(f.relative_to(repo_root)), "usedFor":"Generated deck PDF"})
            if "slides" in p or "pptx" in src:
                items.append({"type":"artifact","name":"slides","path": str(f.relative_to(repo_root)), "usedFor":"Generated slides"})
            if "email" in p or "sendgrid" in src or "smtplib" in src:
                items.append({"type":"email","name":"transactional_email","path": str(f.relative_to(repo_root)), "usedFor":"Sends confirmation email"})
        except Exception:
            continue
    # de-dupe by (type,name,path)
    seen, uniq = set(), []
    for it in items:
        key = (it["type"], it["name"], it["path"])
        if key in seen: 
            continue
        seen.add(key)
        uniq.append(it)
    return uniq

def extract_cors_policies(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract CORS middleware configuration."""
    policies = []
    try:
        if 'CORSMiddleware' in text or 'cors' in text.lower():
            # Extract CORS configuration
            origins = []
            methods = []
            
            # Look for allowed_origins
            origins_match = re.search(r'allowed_origins\s*=\s*\[([^\]]+)\]', text)
            if origins_match:
                origins = [o.strip().strip('"\'') for o in origins_match.group(1).split(',')]
            
            # Look for allowed_methods
            methods_match = re.search(r'allowed_methods\s*=\s*\[([^\]]+)\]', text)
            if methods_match:
                methods = [m.strip().strip('"\'') for m in methods_match.group(1).split(',')]
            
            policies.append({
                "type": "middleware",
                "name": "CORSMiddleware",
                "appliedAt": path,
                "config": {
                    "allowed_origins": origins,
                    "allowed_methods": methods
                }
            })
    except Exception as e:
        print(f"Error extracting CORS policies from {path}: {e}")
    
    return policies

def extract_dependencies(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract FastAPI dependencies (Depends)."""
    dependencies = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'Depends':
                    if node.args:
                        dep_name = "Unknown"
                        if isinstance(node.args[0], ast.Name):
                            dep_name = node.args[0].id
                        elif isinstance(node.args[0], ast.Attribute):
                            dep_name = f"{node.args[0].value.id}.{node.args[0].attr}"
                        
                        dependencies.append({
                            "type": "dependency",
                            "name": dep_name,
                            "appliedAt": path
                        })
    except Exception as e:
        print(f"Error extracting dependencies from {path}: {e}")
    
    return dependencies

def extract_pydantic_models(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract Pydantic models from Python code."""
    models = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = [getattr(b, "id", getattr(b, "attr", "")) for b in node.bases]
                if any("BaseModel" in str(b) or "BaseSettings" in str(b) for b in base_names):
                    fields = []
                    
                    for n in ast.walk(node):
                        if isinstance(n, ast.AnnAssign) and hasattr(n.target, "id"):
                            field_info = {
                                "name": n.target.id,
                                "type": "Any",
                                "required": True,
                                "default": None
                            }
                            
                            # Extract type annotation
                            if n.annotation:
                                if hasattr(n.annotation, "id"):
                                    field_info["type"] = n.annotation.id
                                elif hasattr(n.annotation, "slice"):  # Optional[Type]
                                    if hasattr(n.annotation.value, "id") and n.annotation.value.id == "Optional":
                                        field_info["required"] = False
                                        if hasattr(n.annotation.slice, "id"):
                                            field_info["type"] = n.annotation.slice.id
                                elif hasattr(n.annotation, "elts"):  # Union types
                                    field_info["type"] = "Union"
                            
                            # Extract default value
                            if n.value:
                                field_info["default"] = _ast_value_to_py(n.value)
                            
                            fields.append(field_info)
                    
                    models.append({
                        "name": node.name,
                        "fields": fields,
                        "path": path
                    })
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
                # Exclude Pydantic Settings models
                if any("BaseSettings" in str(b) for b in base_names):
                    continue
                
                # Check for SQLAlchemy inheritance - be more flexible
                is_sqlalchemy = False
                has_tablename = False
                
                # Check for __tablename__ assignment
                for n in node.body:
                    if isinstance(n, ast.Assign):
                        for target in n.targets:
                            if hasattr(target, "id") and target.id == "__tablename__":
                                has_tablename = True
                                break
                
                # Check base classes - be more flexible with naming
                for base_name in base_names:
                    base_str = str(base_name).lower()
                    if any(keyword in base_str for keyword in ["base", "declarativebase", "model", "db"]):
                        is_sqlalchemy = True
                        break
                
                # Also check for common SQLAlchemy patterns in class body
                if not is_sqlalchemy:
                    for n in node.body:
                        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                            # Look for Column, String, Integer, etc.
                            fn = getattr(n.value.func, "id", getattr(n.value.func, "attr", ""))
                            if str(fn).lower() in ["column", "string", "integer", "boolean", "datetime", "text"]:
                                is_sqlalchemy = True
                                break
                
                if is_sqlalchemy or has_tablename:
                    # Extract table name
                    table_name = None
                    columns = []
                    
                    for n in node.body:
                        # Look for __tablename__ assignment
                        if isinstance(n, ast.Assign):
                            for target in n.targets:
                                if hasattr(target, "id") and target.id == "__tablename__":
                                    if isinstance(n.value, ast.Constant):
                                        table_name = n.value.value
                                    elif isinstance(n.value, ast.Str):  # Python < 3.8
                                        table_name = n.value.s
                        
                        # Look for Column assignments
                        elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                            fn = getattr(n.value.func, "id", getattr(n.value.func, "attr", ""))
                            if str(fn).lower() in ["column", "string", "integer", "boolean", "datetime", "text", "float"]:
                                column_info = {"name": None, "type": "Unknown", "pk": False, "nullable": True}
                                
                                # Extract column name from target
                                for t in n.targets:
                                    if hasattr(t, "id"):
                                        column_info["name"] = t.id
                                
                                # Extract column type
                                if str(fn).lower() == "column":
                                    # Column() with type as first arg
                                    if n.value.args:
                                        arg = n.value.args[0]
                                        if hasattr(arg, "id"):
                                            column_info["type"] = arg.id
                                        elif isinstance(arg, ast.Constant):
                                            column_info["type"] = str(arg.value)
                                        elif isinstance(arg, ast.Str):  # Python < 3.8
                                            column_info["type"] = arg.s
                                    
                                    # Check for primary_key, nullable in keywords
                                    for kw in n.value.keywords:
                                        if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                                            column_info["pk"] = kw.value.value
                                        elif kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                                            column_info["nullable"] = kw.value.value
                                else:
                                    # Direct type assignment (String(), Integer(), etc.)
                                    column_info["type"] = str(fn)
                                
                                if column_info["name"]:
                                    columns.append(column_info)
                    
                    # Use class name as table name if __tablename__ not found
                    if not table_name:
                        table_name = node.name.lower() + "s"
                    
                    models.append({
                        "name": node.name,
                        "table": table_name,
                        "columns": columns,
                        "path": path
                    })
    except Exception as e:
        # Debug: print the error to understand what's failing
        print(f"SQLAlchemy extraction error in {path}: {e}")
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
    try:
        tree = ast.parse(text)
        lines = text.split('\n')
        
        # Look for middleware additions
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, "attr") and node.func.attr == "add_middleware":
                    # Extract middleware name from first argument
                    middleware_name = "Unknown"
                    if node.args:
                        if hasattr(node.args[0], "id"):
                            middleware_name = node.args[0].id
                        elif isinstance(node.args[0], ast.Constant):
                            middleware_name = str(node.args[0].value)
                    
                    # Get line number for appliedAt
                    line_no = getattr(node, 'lineno', 0)
                    applied_at = f"{path}:{line_no}" if line_no > 0 else path
                    
                    items.append({
                        "type": "middleware", 
                        "name": middleware_name, 
                        "path": path,
                        "appliedAt": applied_at
                    })
        
        # Look for dependencies in APIRouter or route decorators
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                line_no = getattr(node, 'lineno', 0)
                applied_at = f"{path}:{line_no}" if line_no > 0 else path
                
                # APIRouter(dependencies=[...])
                if hasattr(node.func, "id") and node.func.id == "APIRouter":
                    for kw in node.keywords:
                        if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                            items.append({
                                "type": "dependency", 
                                "name": "APIRouter dependencies", 
                                "path": path,
                                "appliedAt": applied_at
                            })
                
                # Route decorators with dependencies
                elif hasattr(node.func, "attr") and node.func.attr in ["get", "post", "put", "delete", "patch"]:
                    for kw in node.keywords:
                        if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                            items.append({
                                "type": "dependency", 
                                "name": f"{node.func.attr} dependencies", 
                                "path": path,
                                "appliedAt": applied_at
                            })
                
                # Look for Depends() calls in function parameters
                elif hasattr(node.func, "id") and node.func.id == "Depends":
                    items.append({
                        "type": "dependency",
                        "name": "Depends",
                        "path": path,
                        "appliedAt": applied_at
                    })
        
        # Look for security/authentication patterns
        if "HTTPBearer" in text or "HTTPAuthorizationCredentials" in text:
            items.append({
                "type": "security",
                "name": "HTTP Bearer Authentication",
                "path": path,
                "appliedAt": path
            })
            
        if "CORSMiddleware" in text:
            items.append({
                "type": "middleware",
                "name": "CORSMiddleware",
                "path": path,
                "appliedAt": path
            })
            
    except Exception:
        pass
    return items

def extract_fastapi_routes(text: str, path: str) -> List[Dict[str, Any]]:
    """Extract FastAPI routes with request/response schemas."""
    routes = []
    try:
        tree = ast.parse(text)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for route decorators
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and hasattr(decorator.func, "attr"):
                        if decorator.func.attr in ["get", "post", "put", "delete", "patch"]:
                            route_info = {
                                "method": decorator.func.attr.upper(),
                                "path": "/",
                                "handler": node.name,
                                "request_schema": None,
                                "response_schema": None,
                                "file_path": path
                            }
                            
                            # Extract path from decorator args
                            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                route_info["path"] = decorator.args[0].value
                            elif decorator.args and isinstance(decorator.args[0], ast.Str):  # Python < 3.8
                                route_info["path"] = decorator.args[0].s
                            
                            # Extract request schema from function parameters
                            for arg in node.args.args:
                                if arg.annotation:
                                    if hasattr(arg.annotation, "id"):
                                        route_info["request_schema"] = arg.annotation.id
                                    elif hasattr(arg.annotation, "slice"):  # Optional[Type]
                                        if hasattr(arg.annotation.slice, "id"):
                                            route_info["request_schema"] = arg.annotation.slice.id
                            
                            # Extract response schema from decorator keywords
                            for kw in decorator.keywords:
                                if kw.arg == "response_model" and hasattr(kw.value, "id"):
                                    route_info["response_schema"] = kw.value.id
                            
                            routes.append(route_info)
    except Exception:
        pass
    return routes

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
    fastapi_routes = extract_fastapi_routes(text, file_path)

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
            "fastapiPolicies": fastapi_policies,
            "fastapiRoutes": fastapi_routes
        },
        "hints": hints
    }
