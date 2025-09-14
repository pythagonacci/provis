"""
Robust import resolution for monorepos and workspaces.
Handles TypeScript path mappings, Python package resolution, and fallbacks.
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
import logging

from .config import settings
from .observability import record_fallback, record_detector_hit
from .models import ImportModel, EvidenceSpan

logger = logging.getLogger(__name__)

@dataclass
class ResolutionResult:
    """Result of import resolution."""
    resolved_path: Optional[str]
    confidence: float
    hypothesis: bool
    reason_code: Optional[str]
    evidence: List[EvidenceSpan]
    
    def __init__(self, resolved_path: Optional[str], confidence: float,
                 hypothesis: bool, reason_code: Optional[str],
                 evidence: List[EvidenceSpan]):
        self.resolved_path = resolved_path
        self.confidence = confidence
        self.hypothesis = hypothesis
        self.reason_code = reason_code
        self.evidence = evidence

class TypeScriptResolver:
    """TypeScript/JavaScript import resolver with path mapping support."""
    
    def __init__(self, repo_root: Path, tsconfig_paths: Dict[str, Any]):
        self.repo_root = repo_root
        self.tsconfig_paths = tsconfig_paths
        self.node_modules_cache: Set[str] = set()
        self._build_resolution_cache()
    
    def _build_resolution_cache(self):
        """Build cache of available modules and paths."""
        # Cache node_modules
        for node_modules in self.repo_root.rglob("node_modules"):
            if node_modules.is_dir():
                self.node_modules_cache.add(str(node_modules))
        
        record_detector_hit("ts_resolver")
    
    def resolve_import(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve an import path to a file."""
        try:
            # Try different resolution strategies
            strategies = [
                self._resolve_relative,
                self._resolve_tsconfig_paths,
                self._resolve_node_modules,
                self._resolve_package_json,
                self._resolve_alias_brute_force
            ]
            
            for strategy in strategies:
                result = strategy(import_path, from_file)
                if result.resolved_path and result.confidence > 0.5:
                    return result
            
            # All strategies failed
            return ResolutionResult(
                resolved_path=None,
                confidence=0.0,
                hypothesis=True,
                reason_code="alias-miss",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
            
        except Exception as e:
            logger.warning(f"Import resolution failed for {import_path} in {from_file}: {e}")
            return ResolutionResult(
                resolved_path=None,
                confidence=0.0,
                hypothesis=True,
                reason_code="unknown",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
    
    def _resolve_relative(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve relative imports."""
        if not import_path.startswith('.'):
            return ResolutionResult(None, 0.0, False, None, [])
        
        # Resolve relative path
        from_dir = from_file.parent
        resolved_path = (from_dir / import_path).resolve()
        
        # Try different extensions
        extensions = ['.ts', '.tsx', '.js', '.jsx', '.json', '']
        for ext in extensions:
            candidate = Path(str(resolved_path) + ext)
            if candidate.exists():
                return ResolutionResult(
                    resolved_path=str(candidate.relative_to(self.repo_root)),
                    confidence=0.95,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_tsconfig_paths(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve using TypeScript path mappings."""
        # Find the closest tsconfig.json
        tsconfig_file = self._find_tsconfig_for_file(from_file)
        if not tsconfig_file:
            return ResolutionResult(None, 0.0, False, None, [])
        
        tsconfig_path = str(tsconfig_file.relative_to(self.repo_root))
        if tsconfig_path not in self.tsconfig_paths:
            return ResolutionResult(None, 0.0, False, None, [])
        
        paths = self.tsconfig_paths[tsconfig_path]
        base_url = self._get_base_url(tsconfig_file)
        
        for pattern, mappings in paths.items():
            if self._matches_pattern(import_path, pattern):
                for mapping in mappings:
                    resolved = mapping.replace('*', import_path[len(pattern.rstrip('*')):])
                    candidate = (tsconfig_file.parent / base_url / resolved).resolve()
                    
                    # Try different extensions
                    extensions = ['.ts', '.tsx', '.js', '.jsx', '.json', '']
                    for ext in extensions:
                        full_candidate = Path(str(candidate) + ext)
                        if full_candidate.exists():
                            return ResolutionResult(
                                resolved_path=str(full_candidate.relative_to(self.repo_root)),
                                confidence=0.9,
                                hypothesis=False,
                                reason_code=None,
                                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                            )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_node_modules(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve from node_modules."""
        # Find the closest node_modules
        current_dir = from_file.parent
        while current_dir != self.repo_root.parent:
            node_modules = current_dir / "node_modules"
            if node_modules.exists():
                candidate = node_modules / import_path
                
                # Try package.json resolution
                package_json = candidate / "package.json"
                if package_json.exists():
                    try:
                        with open(package_json) as f:
                            data = json.load(f)
                        
                        main_file = data.get("main", "index.js")
                        if main_file:
                            main_path = candidate / main_file
                            if main_path.exists():
                                return ResolutionResult(
                                    resolved_path=str(main_path.relative_to(self.repo_root)),
                                    confidence=0.8,
                                    hypothesis=False,
                                    reason_code=None,
                                    evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                                )
                    except Exception:
                        pass
                
                # Try index files
                for index_file in ["index.ts", "index.tsx", "index.js", "index.jsx"]:
                    candidate_file = candidate / index_file
                    if candidate_file.exists():
                        return ResolutionResult(
                            resolved_path=str(candidate_file.relative_to(self.repo_root)),
                            confidence=0.8,
                            hypothesis=False,
                            reason_code=None,
                            evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                        )
            
            current_dir = current_dir.parent
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_package_json(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve using package.json exports field."""
        # This would implement package.json exports resolution
        # For now, return no result
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_alias_brute_force(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Brute force resolution by searching the entire repo."""
        if not settings.ENABLE_ALIAS_BRUTE_FORCE:
            return ResolutionResult(None, 0.0, False, None, [])
        
        # Search for files that might match the import
        candidates = []
        
        # Try exact matches
        for candidate in self.repo_root.rglob(f"{import_path}.*"):
            if candidate.is_file():
                candidates.append(candidate)
        
        # Try directory with index files
        for candidate_dir in self.repo_root.rglob(import_path):
            if candidate_dir.is_dir():
                for index_file in ["index.ts", "index.tsx", "index.js", "index.jsx"]:
                    index_path = candidate_dir / index_file
                    if index_path.exists():
                        candidates.append(index_path)
        
        if candidates:
            # Return the first candidate with low confidence
            best_candidate = candidates[0]
            return ResolutionResult(
                resolved_path=str(best_candidate.relative_to(self.repo_root)),
                confidence=0.3,
                hypothesis=True,
                reason_code="alias-miss",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _find_tsconfig_for_file(self, file_path: Path) -> Optional[Path]:
        """Find the closest tsconfig.json for a file."""
        current_dir = file_path.parent
        while current_dir != self.repo_root.parent:
            tsconfig = current_dir / "tsconfig.json"
            if tsconfig.exists():
                return tsconfig
            current_dir = current_dir.parent
        return None
    
    def _get_base_url(self, tsconfig_file: Path) -> str:
        """Get baseUrl from tsconfig.json."""
        try:
            with open(tsconfig_file) as f:
                data = json.load(f)
            return data.get("compilerOptions", {}).get("baseUrl", ".")
        except Exception:
            return "."
    
    def _matches_pattern(self, import_path: str, pattern: str) -> bool:
        """Check if import path matches a TypeScript path pattern."""
        if pattern.endswith('*'):
            prefix = pattern[:-1]
            return import_path.startswith(prefix)
        else:
            return import_path == pattern

class PythonResolver:
    """Python import resolver with package detection."""
    
    def __init__(self, repo_root: Path, pyproject_packages: List[str]):
        self.repo_root = repo_root
        self.pyproject_packages = pyproject_packages
        self.python_paths: Set[str] = set()
        self._build_python_paths()
    
    def _build_python_paths(self):
        """Build cache of Python package paths."""
        # Find all Python packages
        for py_file in self.repo_root.rglob("*.py"):
            if py_file.name == "__init__.py":
                package_dir = py_file.parent
                self.python_paths.add(str(package_dir.relative_to(self.repo_root)))
        
        record_detector_hit("python_resolver")
    
    def resolve_import(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve a Python import."""
        try:
            # Try different resolution strategies
            strategies = [
                self._resolve_relative,
                self._resolve_absolute,
                self._resolve_package,
                self._resolve_brute_force
            ]
            
            for strategy in strategies:
                result = strategy(import_path, from_file)
                if result.resolved_path and result.confidence > 0.5:
                    return result
            
            # All strategies failed
            return ResolutionResult(
                resolved_path=None,
                confidence=0.0,
                hypothesis=True,
                reason_code="alias-miss",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
            
        except Exception as e:
            logger.warning(f"Python import resolution failed for {import_path} in {from_file}: {e}")
            return ResolutionResult(
                resolved_path=None,
                confidence=0.0,
                hypothesis=True,
                reason_code="unknown",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
    
    def _resolve_relative(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve relative imports."""
        if not import_path.startswith('.'):
            return ResolutionResult(None, 0.0, False, None, [])
        
        # Resolve relative path
        from_dir = from_file.parent
        resolved_path = (from_dir / import_path).resolve()
        
        # Try different Python file extensions
        extensions = ['.py', '']
        for ext in extensions:
            candidate = Path(str(resolved_path) + ext)
            if candidate.exists():
                return ResolutionResult(
                    resolved_path=str(candidate.relative_to(self.repo_root)),
                    confidence=0.95,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                )
            
            # Try package with __init__.py
            init_file = candidate / "__init__.py"
            if init_file.exists():
                return ResolutionResult(
                    resolved_path=str(init_file.relative_to(self.repo_root)),
                    confidence=0.95,
                    hypothesis=False,
                    reason_code=None,
                    evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_absolute(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve absolute imports from repo root."""
        # Try direct file
        candidate = self.repo_root / import_path
        if candidate.exists():
            return ResolutionResult(
                resolved_path=str(candidate.relative_to(self.repo_root)),
                confidence=0.9,
                hypothesis=False,
                reason_code=None,
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
        
        # Try with .py extension
        py_candidate = Path(str(candidate) + ".py")
        if py_candidate.exists():
            return ResolutionResult(
                resolved_path=str(py_candidate.relative_to(self.repo_root)),
                confidence=0.9,
                hypothesis=False,
                reason_code=None,
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_package(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Resolve package imports."""
        # Check if it's a known package
        if import_path in self.pyproject_packages:
            # Find the package directory
            for package_dir in self.python_paths:
                if package_dir.endswith(import_path):
                    init_file = self.repo_root / package_dir / "__init__.py"
                    if init_file.exists():
                        return ResolutionResult(
                            resolved_path=str(init_file.relative_to(self.repo_root)),
                            confidence=0.8,
                            hypothesis=False,
                            reason_code=None,
                            evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
                        )
        
        return ResolutionResult(None, 0.0, False, None, [])
    
    def _resolve_brute_force(self, import_path: str, from_file: Path) -> ResolutionResult:
        """Brute force resolution by searching the repo."""
        # Search for files that might match the import
        candidates = []
        
        # Try exact matches
        for candidate in self.repo_root.rglob(f"{import_path}.py"):
            if candidate.is_file():
                candidates.append(candidate)
        
        # Try package directories
        for candidate_dir in self.repo_root.rglob(import_path):
            if candidate_dir.is_dir():
                init_file = candidate_dir / "__init__.py"
                if init_file.exists():
                    candidates.append(init_file)
        
        if candidates:
            # Return the first candidate with low confidence
            best_candidate = candidates[0]
            return ResolutionResult(
                resolved_path=str(best_candidate.relative_to(self.repo_root)),
                confidence=0.3,
                hypothesis=True,
                reason_code="alias-miss",
                evidence=[EvidenceSpan(file=str(from_file), start=1, end=1)]
            )
        
        return ResolutionResult(None, 0.0, False, None, [])

class ImportResolver:
    """Main import resolver that delegates to language-specific resolvers."""
    
    def __init__(self, repo_root: Path, tsconfig_paths: Dict[str, Any], pyproject_packages: List[str]):
        self.repo_root = repo_root
        self.ts_resolver = TypeScriptResolver(repo_root, tsconfig_paths)
        self.py_resolver = PythonResolver(repo_root, pyproject_packages)
    
    def resolve_import(self, import_model: ImportModel, from_file: Path) -> ImportModel:
        """Resolve an import model."""
        import_path = import_model.raw
        
        # Determine language and delegate
        if from_file.suffix in ['.ts', '.tsx', '.js', '.jsx']:
            result = self.ts_resolver.resolve_import(import_path, from_file)
        elif from_file.suffix == '.py':
            result = self.py_resolver.resolve_import(import_path, from_file)
        else:
            # Unknown language, return as-is
            return import_model
        
        # Update the import model with resolution result
        if result.resolved_path:
            import_model.resolved = result.resolved_path
            import_model.external = False
            import_model.confidence = result.confidence
            import_model.hypothesis = result.hypothesis
            import_model.reason_code = result.reason_code
            import_model.evidence.extend(result.evidence)
        else:
            # Resolution failed
            import_model.external = True
            import_model.confidence = 0.0
            import_model.hypothesis = True
            import_model.reason_code = result.reason_code or "alias-miss"
            import_model.evidence.extend(result.evidence)
        
        return import_model
