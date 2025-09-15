"""
Tree-sitter utilities for precise code parsing.
Provides high-accuracy parsing for JavaScript/TypeScript and Python files.
"""

from typing import Dict, Any, List, Optional
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional Tree-sitter import with graceful fallback
try:
    from tree_sitter import Language, Parser
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not available, falling back to regex/AST parsing")

# Global parser instances (cached for performance)
_JS_PARSER = None
_TS_PARSER = None
_PY_PARSER = None
_JS_LANGUAGE = None
_TS_LANGUAGE = None
_PY_LANGUAGE = None

def _init_parsers():
    """Initialize Tree-sitter parsers with compiled grammars."""
    global _JS_PARSER, _TS_PARSER, _PY_PARSER
    global _JS_LANGUAGE, _TS_LANGUAGE, _PY_LANGUAGE
    
    if not _TREE_SITTER_AVAILABLE:
        return False
    
    # Check if already initialized
    if any([_JS_PARSER, _TS_PARSER, _PY_PARSER]):
        return True
    
    try:
        # Get the directory containing this file
        parsers_dir = Path(__file__).parent
        
        # Determine the correct file extension based on platform
        import platform
        system = platform.system().lower()
        if system == "darwin":  # macOS
            grammar_ext = ".dylib"
        else:  # Linux
            grammar_ext = ".so"
        
        # Load JavaScript grammar
        js_grammar = parsers_dir / f"javascript{grammar_ext}"
        if js_grammar.exists():
            try:
                import ctypes
                lib = ctypes.CDLL(str(js_grammar))
                language_func = getattr(lib, 'tree_sitter_javascript')
                language_func.restype = ctypes.c_void_p
                lang_ptr = language_func()
                _JS_LANGUAGE = Language(lang_ptr)
                _JS_PARSER = Parser()
                _JS_PARSER.language = _JS_LANGUAGE
                logger.debug("JavaScript parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize JavaScript parser: {e}")
        
        # Load TypeScript grammar (use JavaScript grammar for TypeScript files)
        ts_grammar = parsers_dir / f"typescript{grammar_ext}"
        if ts_grammar.exists():
            try:
                import ctypes
                lib = ctypes.CDLL(str(ts_grammar))
                language_func = getattr(lib, 'tree_sitter_typescript')
                language_func.restype = ctypes.c_void_p
                lang_ptr = language_func()
                _TS_LANGUAGE = Language(lang_ptr)
                _TS_PARSER = Parser()
                _TS_PARSER.language = _TS_LANGUAGE
                logger.debug("TypeScript parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize TypeScript parser: {e}")
        else:
            # Use JavaScript parser for TypeScript files if no TypeScript grammar
            if _JS_LANGUAGE:
                _TS_LANGUAGE = _JS_LANGUAGE
                _TS_PARSER = Parser()
                _TS_PARSER.language = _TS_LANGUAGE
                logger.debug("Using JavaScript parser for TypeScript files")
        
        # Load Python grammar
        py_grammar = parsers_dir / f"python{grammar_ext}"
        if py_grammar.exists():
            try:
                import ctypes
                lib = ctypes.CDLL(str(py_grammar))
                language_func = getattr(lib, 'tree_sitter_python')
                language_func.restype = ctypes.c_void_p
                lang_ptr = language_func()
                _PY_LANGUAGE = Language(lang_ptr)
                _PY_PARSER = Parser()
                _PY_PARSER.language = _PY_LANGUAGE
                logger.debug("Python parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Python parser: {e}")
        
        # Check if at least one parser was initialized
        if any([_JS_PARSER, _TS_PARSER, _PY_PARSER]):
            logger.info("Tree-sitter parsers initialized successfully")
            return True
        else:
            logger.warning("No Tree-sitter grammars found - using fallback parsing")
            return False
            
    except Exception as e:
        logger.warning(f"Tree-sitter initialization failed: {e}")
        return False

@lru_cache(maxsize=10)
def _get_query(language, query_str: str):
    """Cache compiled queries for performance."""
    try:
        from tree_sitter import Query
        return Query(language, query_str)
    except Exception as e:
        logger.debug(f"Query compilation failed: {e}")
        return None

def parse_with_tree_sitter(content: str, lang: str, file_path: str) -> Dict[str, Any]:
    """
    Parse code content using Tree-sitter for high accuracy.
    
    Args:
        content: Source code content
        lang: Language name ("javascript", "typescript", "python")
        file_path: File path for logging
        
    Returns:
        Dict with parsed imports, routes, functions, classes, and hints
    """
    if not _TREE_SITTER_AVAILABLE:
        raise ImportError("Tree-sitter not available")
    
    # Initialize parsers if not already done
    if not _init_parsers():
        raise ImportError("Tree-sitter grammars not available")
    
    # Get the appropriate parser and language
    parser_map = {
        "javascript": _JS_PARSER,
        "typescript": _TS_PARSER,
        "python": _PY_PARSER
    }
    language_map = {
        "javascript": _JS_LANGUAGE,
        "typescript": _TS_LANGUAGE,
        "python": _PY_LANGUAGE
    }
    
    parser = parser_map.get(lang)
    language = language_map.get(lang)
    
    if not parser or not language:
        raise ValueError(f"Parser not available for language: {lang}")
    
    try:
        # Parse the content
        tree = parser.parse(bytes(content, 'utf8'))
        
        result = {
            "imports": [],
            "routes": [],
            "functions": [],
            "classes": [],
            "hints": {"parsed_with": "tree-sitter"}
        }
        
        if lang in ("javascript", "typescript"):
            result.update(_parse_js_ts_tree(tree, language, content, file_path))
        elif lang == "python":
            result.update(_parse_python_tree(tree, language, content, file_path))
            
        return result
        
    except Exception as e:
        logger.warning(f"Tree-sitter parse failed for {file_path}: {e}")
        raise

def _parse_js_ts_tree(tree, language, content: str, file_path: str) -> Dict[str, Any]:
    """Parse JavaScript/TypeScript syntax tree."""
    result = {
        "imports": [],
        "routes": [],
        "functions": [],
        "classes": []
    }
    
    # Import queries for JS/TS
    import_queries = [
        # ES6 imports: import x from 'path'
        "(import_statement source: (string) @path) @import",
        # CommonJS: require('path')
        "(call_expression function: (identifier) @func arguments: (arguments (string) @path)) @require",
        # Dynamic imports: import('path')
        "(call_expression function: (import) arguments: (arguments (string) @path)) @dynamic_import"
    ]
    
    for query_str in import_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "path":
                    for node in nodes:
                        start_byte = node.start_byte
                        end_byte = node.end_byte
                        import_path = content[start_byte:end_byte].strip('"\'`')
                        
                        # Determine import kind
                        kind = "esm"
                        if "require" in query_str:
                            kind = "commonjs"
                        elif "dynamic" in query_str:
                            kind = "dynamic"
                        
                        result["imports"].append({
                            "raw": import_path,
                            "kind": kind,
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Import query failed for {file_path}: {e}")
    
    # Route detection queries
    route_queries = [
        # Express.js: app.get('/path', ...)
        "(call_expression function: (member_expression object: (identifier) @app property: (property_identifier) @method) args: (arguments (string) @path)) @route",
        # Fastify: fastify.get('/path', ...)
        "(call_expression function: (member_expression object: (identifier) @fastify property: (property_identifier) @method) args: (arguments (string) @path)) @route",
        # Next.js API routes: export async function GET/POST/etc
        "(export_statement declaration: (function_declaration name: (identifier) @handler)) @api_export"
    ]
    
    for query_str in route_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            method = None
            for tag, nodes in captures.items():
                if tag == "method":
                    for node in nodes:
                        method = node.text.decode().upper()
                elif tag == "path" and method:
                    for node in nodes:
                        start_byte = node.start_byte
                        end_byte = node.end_byte
                        path = content[start_byte:end_byte].strip('"\'`')
                        
                        result["routes"].append({
                            "method": method,
                            "path": path,
                            "line": node.start_point[0] + 1
                        })
                        method = None  # Reset for next route
                elif tag == "handler":
                    # Next.js API route - extract HTTP method from function name
                    for node in nodes:
                        function_name = node.text.decode().upper()
                        # Check if it's a valid HTTP method
                        if function_name in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]:
                            result["routes"].append({
                                "method": function_name,
                                "path": "/api/*",
                                "line": node.start_point[0] + 1,
                                "type": "nextjs_api"
                            })
        except Exception as e:
            logger.debug(f"Route query failed for {file_path}: {e}")
    
    # Function detection
    function_queries = [
        # Function declarations: function name() {}
        "(function_declaration name: (identifier) @name) @func",
        # Arrow functions: const name = () => {}
        "(variable_declarator name: (identifier) @name value: (arrow_function)) @arrow_func",
        # Method definitions: method() {}
        "(method_definition name: (property_identifier) @name) @method"
    ]
    
    for query_str in function_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "name":
                    for node in nodes:
                        result["functions"].append({
                            "name": node.text.decode(),
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Function query failed for {file_path}: {e}")
    
    # Class detection
    class_queries = [
        # Class declarations: class Name {}
        "(class_declaration name: (type_identifier) @name) @class"
    ]
    
    for query_str in class_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "name":
                    for node in nodes:
                        result["classes"].append({
                            "name": node.text.decode(),
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Class query failed for {file_path}: {e}")
    
    return result

def _parse_python_tree(tree, language, content: str, file_path: str) -> Dict[str, Any]:
    """Parse Python syntax tree."""
    result = {
        "imports": [],
        "routes": [],
        "functions": [],
        "classes": []
    }
    
    # Import queries for Python
    import_queries = [
        # Standard imports: import module
        "(import_statement name: (dotted_name) @module) @import",
        # From imports: from module import name
        "(import_from_statement module_name: (dotted_name) @module) @from_import",
        # Relative imports: from .module import name
        "(import_from_statement module_name: (relative_import) @module) @relative_import"
    ]
    
    for query_str in import_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "module":
                    for node in nodes:
                        start_byte = node.start_byte
                        end_byte = node.end_byte
                        import_path = content[start_byte:end_byte]
                        
                        result["imports"].append({
                            "raw": import_path,
                            "kind": "python",
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Python import query failed for {file_path}: {e}")
    
    # Route detection for Python web frameworks
    route_queries = [
        # FastAPI: @app.get("/path")
        "(decorator (call function: (attribute object: (identifier) @app attribute: (identifier) @method) arguments: (argument_list (string) @path))) @fastapi_route",
        # Flask: @app.route("/path", methods=["GET"])
        "(decorator (call function: (attribute object: (identifier) @app attribute: (identifier) @route) arguments: (argument_list (string) @path))) @flask_route",
        # Django: path("path/", view)
        "(call function: (identifier) @path_func arguments: (argument_list (string) @path)) @django_route"
    ]
    
    for query_str in route_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            method = None
            for tag, nodes in captures.items():
                if tag == "method":
                    for node in nodes:
                        method = node.text.decode().upper()
                elif tag == "path" and method:
                    for node in nodes:
                        start_byte = node.start_byte
                        end_byte = node.end_byte
                        path = content[start_byte:end_byte].strip('"\'')
                        
                        result["routes"].append({
                            "method": method,
                            "path": path,
                            "line": node.start_point[0] + 1,
                            "framework": "fastapi"
                        })
                        method = None
                elif tag == "path" and not method:
                    # Flask or Django route
                    for node in nodes:
                        start_byte = node.start_byte
                        end_byte = node.end_byte
                        path = content[start_byte:end_byte].strip('"\'')
                        
                        framework = "flask" if "flask" in query_str else "django"
                        result["routes"].append({
                            "method": "ANY",
                            "path": path,
                            "line": node.start_point[0] + 1,
                            "framework": framework
                        })
        except Exception as e:
            logger.debug(f"Python route query failed for {file_path}: {e}")
    
    # Function detection
    function_queries = [
        # Function definitions: def name():
        "(function_definition name: (identifier) @name) @func",
        # Async functions: async def name():
        "(function_definition name: (identifier) @name) @async_func"
    ]
    
    for query_str in function_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "name":
                    for node in nodes:
                        result["functions"].append({
                            "name": node.text.decode(),
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Python function query failed for {file_path}: {e}")
    
    # Class detection
    class_queries = [
        # Class definitions: class Name:
        "(class_definition name: (identifier) @name) @class"
    ]
    
    for query_str in class_queries:
        try:
            query = _get_query(language, query_str)
            if not query:
                continue
                
            from tree_sitter import QueryCursor
            cursor = QueryCursor(query)
            cursor.matches(tree.root_node)
            captures = cursor.captures(tree.root_node)
            
            for tag, nodes in captures.items():
                if tag == "name":
                    for node in nodes:
                        result["classes"].append({
                            "name": node.text.decode(),
                            "line": node.start_point[0] + 1
                        })
        except Exception as e:
            logger.debug(f"Python class query failed for {file_path}: {e}")
    
    return result

def is_tree_sitter_available() -> bool:
    """Check if Tree-sitter is available for parsing."""
    return _TREE_SITTER_AVAILABLE and _init_parsers()