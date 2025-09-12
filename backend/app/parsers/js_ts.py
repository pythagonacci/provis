from __future__ import annotations
from pathlib import Path
import re
import json
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

# Fallback regex patterns for when ts-morph fails
RE_IMPORT = re.compile(r'^\s*import\s+(?:[^"\']+from\s+)?[\'"]([^\'"]+)[\'"]', re.MULTILINE)
RE_REQUIRE = re.compile(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)')
RE_EXPORT_DEFAULT = re.compile(r'^\s*export\s+default\b', re.MULTILINE)
RE_EXPORT_ANY = re.compile(r'^\s*export\s+(?:default|const|let|var|function|class)\b', re.MULTILINE)
RE_FUNC = re.compile(r'function\s+([A-Za-z0-9_]+)\s*\(', re.MULTILINE)
RE_CLASS = re.compile(r'^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)\s*', re.MULTILINE)
RE_ARROW_DECL = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*'
    r'(?:\s*:\s*[^=]+)?=\s*(?:async\s*)?\(?[A-Za-z0-9_,\s{}:*=\[\]\.]*\)?\s*=>',
    re.MULTILINE
)
RE_RETURNS_JSX = re.compile(r'return\s*<', re.MULTILINE)
RE_JSX_LITERAL = re.compile(r'<[A-Za-z]', re.MULTILINE)

# Default-exported anonymous function/arrow with JSX
RE_DEFAULT_ANON_FUNC = re.compile(
    r'^\s*export\s+default\s+(?:async\s+)?(?:function\s*\(|\(?[A-Za-z0-9_,\s{}:*=\[\]\.]*\)?\s*=>)',
    re.MULTILINE
)


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.read_text(encoding="latin-1", errors="ignore")


def _is_pascal(name: str) -> bool:
    return bool(name) and name[0].isupper()


def _detect_nextjs_routes(path: str, filename: str, text: str) -> List[Dict[str, str]]:
    """Detect Next.js routes from file path, name, and content."""
    routes = []
    path_parts = path.split("/")
    
    # App Router (Next.js 13+)
    if "app" in path_parts:
        app_idx = path_parts.index("app")
        route_parts = path_parts[app_idx + 1:]
        route_path = "/" + "/".join(route_parts[:-1]) if len(route_parts) > 1 else "/"
        
        if filename == "page.tsx" or filename == "page.jsx":
            routes.append({"method": "GET", "path": route_path, "handler": "default"})
        elif filename == "route.ts" or filename == "route.js":
            # Check for exported HTTP method functions
            exported_methods = _extract_nextjs_route_methods(text)
            if exported_methods:
                for method in exported_methods:
                    routes.append({"method": method, "path": route_path, "handler": method.lower()})
            else:
                routes.append({"method": "ANY", "path": route_path, "handler": "default"})
        elif filename == "layout.tsx" or filename == "layout.jsx":
            return []  # Layout, not a route
    
    # Pages Router (legacy)
    elif "pages" in path_parts:
        pages_idx = path_parts.index("pages")
        route_parts = path_parts[pages_idx + 1:]
        
        if route_parts[0] == "api":
            # API route: /pages/api/users.ts -> GET /api/users
            api_parts = route_parts[1:]
            route_path = "/api/" + "/".join(api_parts[:-1]) if len(api_parts) > 1 else "/api"
            routes.append({"method": "ANY", "path": route_path, "handler": "default"})
        else:
            # Page route: /pages/users/index.tsx -> GET /users
            route_path = "/" + "/".join(route_parts[:-1]) if len(route_parts) > 1 else "/"
            routes.append({"method": "GET", "path": route_path, "handler": "default"})
    
    return routes


def _extract_nextjs_route_methods(text: str) -> List[str]:
    """Extract exported HTTP method functions from Next.js App Router route.ts files."""
    methods = []
    
    # Look for exported functions like export async function GET, POST, etc.
    method_pattern = r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\('
    matches = re.findall(method_pattern, text, re.IGNORECASE)
    methods.extend([m.upper() for m in matches])
    
    # Also look for const exports: export const GET = async (req) => {}
    const_pattern = r'export\s+const\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*='
    matches = re.findall(const_pattern, text, re.IGNORECASE)
    methods.extend([m.upper() for m in matches])
    
    return list(set(methods))  # Remove duplicates


def find_all_routes(repo_root: Path) -> List[Dict[str, str]]:
    """Find all routes across different JavaScript/TypeScript frameworks."""
    routes = []
    
    for file_path in repo_root.rglob("*"):
        if not file_path.is_file():
            continue
            
        # Skip non-source files
        if file_path.suffix.lower() not in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}:
            continue
            
        # Skip build artifacts and dependencies
        if any(seg in ("node_modules", "dist", "build", ".next", ".nuxt", "out") for seg in file_path.parts):
            continue
        if any(seg.startswith(".") for seg in file_path.parts):
            continue
            
        try:
            text = _read_text(file_path)
            rel_path = str(file_path.relative_to(repo_root))
            
            # Detect Next.js routes
            nextjs_routes = _detect_nextjs_routes(rel_path, file_path.name, text)
            for route in nextjs_routes:
                route["file"] = rel_path
                route["framework"] = "nextjs"
                routes.append(route)
            
            # Detect Express routes
            express_routes = _detect_express_routes(text)
            for route in express_routes:
                route["file"] = rel_path
                route["framework"] = "express"
                routes.append(route)
                
            # Detect Koa routes
            koa_routes = _detect_koa_routes(text)
            for route in koa_routes:
                route["file"] = rel_path
                route["framework"] = "koa"
                routes.append(route)
                
        except Exception:
            continue
    
    return routes

def _detect_express_routes(text: str) -> List[Dict[str, str]]:
    """Detect Express.js routes from app.get/post/put/delete calls with hardened patterns."""
    routes = []
    
    # More specific patterns to avoid false positives
    # Look for actual Express route definitions, not just any .get/.post calls
    
    # Pattern 1: app.METHOD('/path', handler) or router.METHOD('/path', handler)
    # Must have a string path and a comma (indicating a handler function)
    route_pattern = r'(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(?:async\s+)?(?:function\s*\(|\([^)]*\)\s*=>|[\w_]+)'
    matches = re.findall(route_pattern, text, re.MULTILINE)
    
    for method, path in matches:
        # Additional validation: ensure this looks like a real route
        if path and not path.startswith('config') and not path.startswith('getConfig'):
            routes.append({
                "method": method.upper(),
                "path": path,
                "handler": "anonymous"
            })
    
    # Pattern 2: More specific for named handlers
    # app.get('/path', handlerName) where handlerName is a valid identifier
    named_handler_pattern = r'(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([a-zA-Z_$][a-zA-Z0-9_$]*)'
    named_matches = re.findall(named_handler_pattern, text)
    
    for method, path, handler in named_matches:
        if path and not path.startswith('config') and not path.startswith('getConfig'):
            routes.append({
                "method": method.upper(),
                "path": path,
                "handler": handler
            })
    
    # Pattern 3: Express Router usage
    # router.route('/path').get(handler).post(handler)
    router_chain_pattern = r'router\.route\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\.(get|post|put|delete|patch|options|head)\s*\(\s*(?:async\s+)?(?:function\s*\(|\([^)]*\)\s*=>|[\w_]+)'
    router_matches = re.findall(router_chain_pattern, text, re.MULTILINE)
    
    for path, method in router_matches:
        if path and not path.startswith('config') and not path.startswith('getConfig'):
            routes.append({
                "method": method.upper(),
                "path": path,
                "handler": "anonymous"
            })
    
    return routes

def _detect_koa_routes(text: str) -> List[Dict[str, str]]:
    """Detect Koa.js routes from router.get/post/put/delete calls."""
    routes = []
    
    # Koa router patterns: router.get('/path', handler)
    koa_pattern = r'router\.(get|post|put|delete|patch|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(?:async\s+)?(?:function\s*\(|\([^)]*\)\s*=>|[\w_]+)'
    matches = re.findall(koa_pattern, text, re.MULTILINE)
    
    for method, path in matches:
        if path and not path.startswith('config'):
            routes.append({
                "method": method.upper(),
                "path": path,
                "handler": "anonymous"
            })
    
    return routes

def collect_typescript_interfaces(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """Extract TypeScript interfaces and type definitions."""
    interfaces = {}
    
    for file_path in repo_root.rglob("*.ts"):
        if not file_path.is_file():
            continue
            
        # Skip build artifacts
        if any(seg in ("node_modules", "dist", "build", ".next") for seg in file_path.parts):
            continue
        if any(seg.startswith(".") for seg in file_path.parts):
            continue
            
        try:
            text = _read_text(file_path)
            rel_path = str(file_path.relative_to(repo_root))
            
            # Extract interfaces
            interface_pattern = r'interface\s+(\w+)\s*\{([^}]+)\}'
            matches = re.findall(interface_pattern, text, re.DOTALL)
            
            for name, body in matches:
                # Extract field names from interface body
                field_pattern = r'(\w+)(?:\?)?\s*:'
                fields = re.findall(field_pattern, body)
                
                interfaces[name] = {
                    "path": rel_path,
                    "kind": "typescript.Interface",
                    "fields": fields
                }
            
            # Extract type aliases
            type_pattern = r'type\s+(\w+)\s*=\s*\{([^}]+)\}'
            type_matches = re.findall(type_pattern, text, re.DOTALL)
            
            for name, body in type_matches:
                field_pattern = r'(\w+)(?:\?)?\s*:'
                fields = re.findall(field_pattern, body)
                
                interfaces[name] = {
                    "path": rel_path,
                    "kind": "typescript.Type",
                    "fields": fields
                }
                
        except Exception:
            continue
    
    return interfaces

def collect_javascript_schemas(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """Extract JavaScript object schemas and validation patterns."""
    schemas = {}
    
    for file_path in repo_root.rglob("*.js"):
        if not file_path.is_file():
            continue
            
        # Skip build artifacts
        if any(seg in ("node_modules", "dist", "build", ".next") for seg in file_path.parts):
            continue
        if any(seg.startswith(".") for seg in file_path.parts):
            continue
            
        try:
            text = _read_text(file_path)
            rel_path = str(file_path.relative_to(repo_root))
            
            # Extract Joi schemas
            joi_pattern = r'const\s+(\w+)\s*=\s*Joi\.object\(\)\.keys\(\s*\{([^}]+)\}'
            joi_matches = re.findall(joi_pattern, text, re.DOTALL)
            
            for name, body in joi_matches:
                field_pattern = r'(\w+)\s*:'
                fields = re.findall(field_pattern, body)
                
                schemas[name] = {
                    "path": rel_path,
                    "kind": "javascript.JoiSchema",
                    "fields": fields
                }
            
            # Extract Zod schemas
            zod_pattern = r'const\s+(\w+)\s*=\s*z\.object\(\s*\{([^}]+)\}'
            zod_matches = re.findall(zod_pattern, text, re.DOTALL)
            
            for name, body in zod_matches:
                field_pattern = r'(\w+)\s*:'
                fields = re.findall(field_pattern, body)
                
                schemas[name] = {
                    "path": rel_path,
                    "kind": "javascript.ZodSchema",
                    "fields": fields
                }
                
        except Exception:
            continue
    
    return schemas

def _detect_framework_hints(path: str, text: str, ext: str) -> Dict[str, Any]:
    hints = {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False}

    # Next.js detection
    if "/pages/" in path or "/app/" in path:
        hints["framework"] = "nextjs"
        hints["isRoute"] = True
        if "/pages/api/" in path or "/app/" in path and ("route.ts" in path or "route.js" in path):
            hints["isAPI"] = True

    # Express.js detection
    if "express" in text.lower() or "app.get" in text or "router.get" in text:
        hints["framework"] = "express"
        hints["isAPI"] = True
        hints["isRoute"] = True

    # React component detection for TSX/JSX
    if ext in (".tsx", ".jsx"):
        has_jsx = bool(RE_RETURNS_JSX.search(text) or RE_JSX_LITERAL.search(text))
        func_names = RE_FUNC.findall(text)
        class_names = RE_CLASS.findall(text)
        arrow_names = RE_ARROW_DECL.findall(text)
        has_default_export = bool(RE_EXPORT_DEFAULT.search(text))

        if has_jsx and (
            has_default_export
            or any(_is_pascal(n) for n in func_names + class_names + arrow_names)
        ):
            hints["isReactComponent"] = True

    return hints


def _parse_with_ts_morph(text: str, file_path: str, available_files: List[str] = None) -> Optional[Dict[str, Any]]:
    """Use ts-morph via Node.js subprocess for robust parsing with import resolution."""
    try:
        # Create a temporary script that uses ts-morph to parse the file
        # Escape the text content for JavaScript
        escaped_text = text.replace('`', '\\`').replace('$', '\\$')
        available_files_js = json.dumps(available_files or [])
        
        script_content = f"""
const {{ Project }} = require('ts-morph');
const fs = require('fs');
const path = require('path');

try {{
    const project = new Project();
    const sourceFile = project.createSourceFile('temp.ts', `{escaped_text}`);
    const availableFiles = {available_files_js};
    
    const result = {{
        imports: [],
        exports: [],
        functions: [],
        classes: [],
        routes: []
    }};
    
    // Helper function to resolve imports
    function resolveImport(moduleSpecifier) {{
        if (!moduleSpecifier) return {{ resolved: null, external: true }};
        
        // Relative imports
        if (moduleSpecifier.startsWith('.')) {{
            const basePath = path.dirname('{file_path}');
            const resolvedPath = path.resolve(basePath, moduleSpecifier);
            const candidates = [
                resolvedPath,
                resolvedPath + '.ts',
                resolvedPath + '.tsx',
                resolvedPath + '.js',
                resolvedPath + '.jsx',
                path.join(resolvedPath, 'index.ts'),
                path.join(resolvedPath, 'index.tsx'),
                path.join(resolvedPath, 'index.js'),
                path.join(resolvedPath, 'index.jsx')
            ];
            
            for (const candidate of candidates) {{
                const normalized = candidate.replace(/\\\\/g, '/');
                if (availableFiles.includes(normalized)) {{
                    return {{ resolved: normalized, external: false }};
                }}
            }}
            return {{ resolved: null, external: false }};
        }}
        
        // Absolute imports (starting with /)
        if (moduleSpecifier.startsWith('/')) {{
            const candidates = [
                moduleSpecifier,
                moduleSpecifier + '.ts',
                moduleSpecifier + '.tsx',
                moduleSpecifier + '.js',
                moduleSpecifier + '.jsx',
                moduleSpecifier + '/index.ts',
                moduleSpecifier + '/index.tsx',
                moduleSpecifier + '/index.js',
                moduleSpecifier + '/index.jsx'
            ];
            
            for (const candidate of candidates) {{
                if (availableFiles.includes(candidate)) {{
                    return {{ resolved: candidate, external: false }};
                }}
            }}
            return {{ resolved: null, external: false }};
        }}
        
        // TypeScript alias imports (@/)
        if (moduleSpecifier.startsWith('@/')) {{
            const tail = moduleSpecifier.substring(2);
            const candidates = [
                'src/' + tail,
                'app/' + tail,
                'lib/' + tail,
                'components/' + tail
            ];
            
            for (const candidate of candidates) {{
                const fullCandidates = [
                    candidate,
                    candidate + '.ts',
                    candidate + '.tsx',
                    candidate + '.js',
                    candidate + '.jsx',
                    candidate + '/index.ts',
                    candidate + '/index.tsx',
                    candidate + '/index.js',
                    candidate + '/index.jsx'
                ];
                
                for (const fullCandidate of fullCandidates) {{
                    if (availableFiles.includes(fullCandidate)) {{
                        return {{ resolved: fullCandidate, external: false }};
                    }}
                }}
            }}
            return {{ resolved: null, external: false }};
        }}
        
        // Module imports (src/, app/, lib/, etc.)
        const firstSegment = moduleSpecifier.split('/')[0];
        if (['src', 'app', 'lib', 'components', 'utils', 'server', 'client'].includes(firstSegment)) {{
            const candidates = [
                moduleSpecifier,
                moduleSpecifier + '.ts',
                moduleSpecifier + '.tsx',
                moduleSpecifier + '.js',
                moduleSpecifier + '.jsx',
                moduleSpecifier + '/index.ts',
                moduleSpecifier + '/index.tsx',
                moduleSpecifier + '/index.js',
                moduleSpecifier + '/index.jsx'
            ];
            
            for (const candidate of candidates) {{
                if (availableFiles.includes(candidate)) {{
                    return {{ resolved: candidate, external: false }};
                }}
            }}
            return {{ resolved: null, external: false }};
        }}
        
        // Everything else is external
        return {{ resolved: null, external: true }};
    }}
    
    // Extract imports with resolution
    sourceFile.getImportDeclarations().forEach(imp => {{
        const moduleSpecifier = imp.getModuleSpecifierValue();
        if (moduleSpecifier) {{
            const resolution = resolveImport(moduleSpecifier);
            result.imports.push({{
                raw: moduleSpecifier,
                resolved: resolution.resolved,
                external: resolution.external,
                kind: 'esm'
            }});
        }}
    }});
    
    // Extract exports
    sourceFile.getExportDeclarations().forEach(exp => {{
        if (exp.getModuleSpecifier()) {{
            result.exports.push('named');
        }} else {{
            result.exports.push('default');
        }}
    }});
    
    // Extract functions
    sourceFile.getFunctions().forEach(func => {{
        const params = func.getParameters().map(p => p.getName());
        const decorators = func.getDecorators().map(d => d.getName());
        const calls = [];
        
        // Find function calls within this function
        func.getDescendantsOfKind(require('ts-morph').SyntaxKind.CallExpression).forEach(call => {{
            const expr = call.getExpression();
            if (expr.getKind() === require('ts-morph').SyntaxKind.Identifier) {{
                calls.push(expr.getText());
            }}
        }});
        
        result.functions.push({{
            name: func.getName() || 'anonymous',
            params: params,
            decorators: decorators,
            calls: calls
        }});
    }});
    
    // Extract classes
    sourceFile.getClasses().forEach(cls => {{
        const methods = cls.getMethods().map(m => m.getName());
        const baseClasses = cls.getBaseTypes().map(b => b.getText());
        
        result.classes.push({{
            name: cls.getName() || 'anonymous',
            methods: methods,
            baseClasses: baseClasses
        }});
    }});
    
    console.log(JSON.stringify(result));
}} catch (error) {{
    console.error('Parse error:', error.message);
    process.exit(1);
}}
"""
        
        # Write script to temp file and run it
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            result = subprocess.run(['node', script_path], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return json.loads(result.stdout.strip())
        finally:
            Path(script_path).unlink(missing_ok=True)
            
    except Exception:
        pass
    
    return None


def _parse_with_regex_fallback(text: str) -> Dict[str, Any]:
    """Fallback to regex parsing when ts-morph fails."""
    # Imports
    imports = [{"raw": m, "kind": "esm"} for m in RE_IMPORT.findall(text)]
    for m in RE_REQUIRE.findall(text):
        imports.append({"raw": m, "kind": "cjs"})

    # Exports
    exports = []
    if RE_EXPORT_ANY.search(text):
        exports.append("default" if RE_EXPORT_DEFAULT.search(text) else "named")

    # Functions - improved regex patterns
    functions = []
    
    # Regular function declarations (including default exports)
    for name in RE_FUNC.findall(text):
        functions.append({"name": name, "params": [], "decorators": [], "calls": [], "sideEffects": []})
    
    # Arrow function declarations
    for name in RE_ARROW_DECL.findall(text):
        if not any(f["name"] == name for f in functions):
            functions.append({"name": name, "params": [], "decorators": [], "calls": [], "sideEffects": []})
    
    # Default export functions (anonymous) - check if we found any named functions
    if RE_DEFAULT_ANON_FUNC.search(text) and not functions:
        functions.append({"name": "default", "params": [], "decorators": [], "calls": [], "sideEffects": []})

    # Classes
    classes = []
    for name in RE_CLASS.findall(text):
        classes.append({"name": name, "methods": [], "baseClasses": []})

    return {
        "imports": imports,
        "exports": exports,
        "functions": functions,
        "classes": classes,
        "routes": []
    }


def _detect_side_effects(text: str, ext: str) -> List[str]:
    """Detect side effects in the code."""
    tags = []
    lower = text.lower()
    
    # Network calls
    if re.search(r"\b(fetch|axios|http\.request|xmlhttprequest|websocket)\b", lower):
        tags.append("net")
    
    # File I/O
    if re.search(r"\b(fs\.|readfile|writefile|stream|blob)\b", lower):
        tags.append("io")
    
    # Database
    if re.search(r"\b(prisma|mongoose|mongodb|pg\.|knex|sequelize)\b", lower):
        tags.append("db")
    
    # DOM/Rendering
    if ext in (".tsx", ".jsx") and (RE_JSX_LITERAL.search(text) or RE_RETURNS_JSX.search(text)):
        tags.append("render")
    
    return list(dict.fromkeys(tags))


def parse_js_ts_file(p: Path, ext: str, snapshot: Path = None, available_files: List[str] = None) -> Dict[str, Any]:
    """Parse JavaScript/TypeScript file with robust AST parsing and framework awareness."""
    text = _read_text(p)
    file_path = str(p).replace("\\", "/")
    filename = p.name
    
    # Try ts-morph first, fallback to regex
    parsed = _parse_with_ts_morph(text, file_path, available_files)
    if not parsed:
        parsed = _parse_with_regex_fallback(text)
    
    # Detect routes
    routes = []
    
    # Next.js routes (can return multiple routes for App Router)
    nextjs_routes = _detect_nextjs_routes(file_path, filename, text)
    routes.extend(nextjs_routes)
    
    # Express routes
    express_routes = _detect_express_routes(text)
    routes.extend(express_routes)
    
    # Detect framework hints
    hints = _detect_framework_hints(file_path, text, ext)
    
    # Add side effects to functions
    side_effects = _detect_side_effects(text, ext)
    for func in parsed.get("functions", []):
        func["sideEffects"] = side_effects
    
    # Use imports from ts-morph (already resolved) or fallback
    resolved_imports = parsed.get("imports", [])
    
    # Detect React hooks
    hooks = []
    if ext in (".tsx", ".jsx"):
        hook_patterns = [
            r"useState", r"useEffect", r"useContext", r"useReducer", r"useCallback",
            r"useMemo", r"useRef", r"useImperativeHandle", r"useLayoutEffect",
            r"useDebugValue", r"useDeferredValue", r"useId", r"useInsertionEffect",
            r"useSyncExternalStore", r"useTransition"
        ]
        for pattern in hook_patterns:
            if re.search(rf"\b{pattern}\b", text):
                hooks.append(pattern)
    
    # Detect Next.js special exports
    nextjs_special_exports = []
    if hints.get("framework") == "nextjs":
        special_exports = [
            "getServerSideProps", "getStaticProps", "getStaticPaths", 
            "generateStaticParams", "generateMetadata", "generateViewport"
        ]
        for export in special_exports:
            if re.search(rf"export\s+(?:async\s+)?(?:const\s+)?(?:function\s+)?{export}\b", text):
                nextjs_special_exports.append(export)
    
    # Detect "use client" pragma
    is_client_component = False
    if ext in (".tsx", ".jsx") and '"use client"' in text:
        is_client_component = True
        hints["isClientComponent"] = True
    
    # Normalize to unified schema
    return {
        "imports": resolved_imports,
        "exports": parsed.get("exports", []),
        "functions": parsed.get("functions", []),
        "classes": parsed.get("classes", []),
        "routes": routes,
        "symbols": {
            "constants": [],  # Could be extracted from AST
            "hooks": hooks,
            "dbModels": [],   # Database model detection
            "middleware": [], # Middleware detection
            "components": [], # React components
            "utilities": nextjs_special_exports  # Next.js special exports
        },
        "hints": hints
    }
