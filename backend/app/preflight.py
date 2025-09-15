"""
Pre-flight repository scanning and framework detection.
Detects project structure, frameworks, and configuration before parsing.
"""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass

from .config import settings
from .observability import record_detector_hit

@dataclass
class FrameworkDetection:
    """Framework detection result."""
    name: str
    confidence: float
    evidence: List[Dict[str, Any]]
    version: Optional[str] = None

@dataclass
class WorkspaceInfo:
    """Workspace/monorepo information."""
    type: str  # "single", "pnpm", "yarn", "turbo", "nx", "poetry", "pants"
    root: str
    packages: List[str]
    config_files: List[str]

@dataclass
class PreflightResult:
    """Pre-flight scan result."""
    frameworks: List[FrameworkDetection]
    workspace: WorkspaceInfo
    config_files: Dict[str, Any]
    big_files: List[str]
    binary_files: List[str]
    env_files: List[str]
    tsconfig_paths: Dict[str, Any]
    pyproject_packages: List[str]
    content_hash: str

def detect_frameworks(snapshot_dir: Path) -> List[FrameworkDetection]:
    """Detect frameworks from package.json, requirements.txt, etc."""
    frameworks = []
    
    # Check for package.json (Node.js projects)
    package_json = snapshot_dir / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                data = json.load(f)
            
            # Next.js detection
            if "next" in data.get("dependencies", {}):
                frameworks.append(FrameworkDetection(
                    name="nextjs",
                    confidence=0.9,
                    evidence=[{"file": "package.json", "key": "dependencies.next"}],
                    version=data["dependencies"]["next"]
                ))
                record_detector_hit("nextjs")
            
            # React detection
            if "react" in data.get("dependencies", {}):
                frameworks.append(FrameworkDetection(
                    name="react",
                    confidence=0.8,
                    evidence=[{"file": "package.json", "key": "dependencies.react"}],
                    version=data["dependencies"]["react"]
                ))
                record_detector_hit("react")
            
            # Express detection
            if "express" in data.get("dependencies", {}):
                frameworks.append(FrameworkDetection(
                    name="express",
                    confidence=0.8,
                    evidence=[{"file": "package.json", "key": "dependencies.express"}],
                    version=data["dependencies"]["express"]
                ))
                record_detector_hit("express")
            
            # Koa detection
            if "koa" in data.get("dependencies", {}):
                frameworks.append(FrameworkDetection(
                    name="koa",
                    confidence=0.8,
                    evidence=[{"file": "package.json", "key": "dependencies.koa"}],
                    version=data["dependencies"]["koa"]
                ))
                record_detector_hit("koa")
            
        except Exception as e:
            print(f"Error reading package.json: {e}")
    
    # Check for requirements.txt (Python projects)
    requirements_txt = snapshot_dir / "requirements.txt"
    if requirements_txt.exists():
        try:
            with open(requirements_txt) as f:
                content = f.read()
            
            # FastAPI detection
            if "fastapi" in content.lower():
                frameworks.append(FrameworkDetection(
                    name="fastapi",
                    confidence=0.9,
                    evidence=[{"file": "requirements.txt", "line": "fastapi"}]
                ))
                record_detector_hit("fastapi")
            
            # Flask detection
            if "flask" in content.lower():
                frameworks.append(FrameworkDetection(
                    name="flask",
                    confidence=0.9,
                    evidence=[{"file": "requirements.txt", "line": "flask"}]
                ))
                record_detector_hit("flask")
            
            # Django detection
            if "django" in content.lower():
                frameworks.append(FrameworkDetection(
                    name="django",
                    confidence=0.9,
                    evidence=[{"file": "requirements.txt", "line": "django"}]
                ))
                record_detector_hit("django")
            
        except Exception as e:
            print(f"Error reading requirements.txt: {e}")
    
    # Check for pyproject.toml (Python projects)
    pyproject_toml = snapshot_dir / "pyproject.toml"
    if pyproject_toml.exists():
        try:
            with open(pyproject_toml) as f:
                content = f.read()
            
            if "fastapi" in content.lower():
                frameworks.append(FrameworkDetection(
                    name="fastapi",
                    confidence=0.9,
                    evidence=[{"file": "pyproject.toml", "line": "fastapi"}]
                ))
                record_detector_hit("fastapi")
            
        except Exception as e:
            print(f"Error reading pyproject.toml: {e}")
    
    return frameworks

def detect_workspace(snapshot_dir: Path) -> WorkspaceInfo:
    """Detect workspace type and structure."""
    
    # Check for pnpm workspace
    pnpm_workspace = snapshot_dir / "pnpm-workspace.yaml"
    if pnpm_workspace.exists():
        return WorkspaceInfo(
            type="pnpm",
            root=str(snapshot_dir),
            packages=[],
            config_files=["pnpm-workspace.yaml"]
        )
    
    # Check for yarn workspace
    package_json = snapshot_dir / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                data = json.load(f)
            if "workspaces" in data:
                return WorkspaceInfo(
                    type="yarn",
                    root=str(snapshot_dir),
                    packages=data["workspaces"],
                    config_files=["package.json"]
                )
        except Exception:
            pass
    
    # Check for turbo
    turbo_json = snapshot_dir / "turbo.json"
    if turbo_json.exists():
        return WorkspaceInfo(
            type="turbo",
            root=str(snapshot_dir),
            packages=[],
            config_files=["turbo.json"]
        )
    
    # Check for nx
    nx_json = snapshot_dir / "nx.json"
    if nx_json.exists():
        return WorkspaceInfo(
            type="nx",
            root=str(snapshot_dir),
            packages=[],
            config_files=["nx.json"]
        )
    
    # Check for Poetry
    pyproject_toml = snapshot_dir / "pyproject.toml"
    if pyproject_toml.exists():
        try:
            content = pyproject_toml.read_text()
            if "[tool.poetry]" in content:
                return WorkspaceInfo(
                    type="poetry",
                    root=str(snapshot_dir),
                    packages=[],
                    config_files=["pyproject.toml"]
                )
        except Exception:
            pass
    
    # Check for Pants
    pants_toml = snapshot_dir / "pants.toml"
    if pants_toml.exists():
        return WorkspaceInfo(
            type="pants",
            root=str(snapshot_dir),
            packages=[],
            config_files=["pants.toml"]
        )
    
    # Default to single package
    return WorkspaceInfo(
        type="single",
        root=str(snapshot_dir),
        packages=[],
        config_files=[]
    )

def find_big_files(snapshot_dir: Path) -> List[str]:
    """Find files that exceed size thresholds."""
    big_files = []
    
    for file_path in snapshot_dir.rglob("*"):
        if file_path.is_file():
            try:
                size = file_path.stat().st_size
                if size > settings.BIG_FILE_SIZE_THRESHOLD:
                    big_files.append(str(file_path.relative_to(snapshot_dir)))
            except OSError:
                continue
    
    return big_files

def find_binary_files(snapshot_dir: Path) -> List[str]:
    """Find binary files that should be skipped."""
    binary_files = []
    binary_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.pdf', '.mp4', '.mp3', '.mov', '.zip', '.tar', '.gz'}
    
    for file_path in snapshot_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in binary_extensions:
            binary_files.append(str(file_path.relative_to(snapshot_dir)))
    
    return binary_files

def find_env_files(snapshot_dir: Path) -> List[str]:
    """Find environment configuration files."""
    env_files = []
    env_patterns = ['.env', '.env.local', '.env.development', '.env.production', '.env.test']
    
    for pattern in env_patterns:
        for file_path in snapshot_dir.rglob(pattern):
            if file_path.is_file():
                env_files.append(str(file_path.relative_to(snapshot_dir)))
    
    return env_files

def parse_tsconfig_paths(snapshot_dir: Path) -> Dict[str, Any]:
    """Parse TypeScript configuration for path mappings."""
    tsconfig_files = list(snapshot_dir.rglob("tsconfig*.json"))
    paths = {}
    
    for tsconfig_file in tsconfig_files:
        try:
            with open(tsconfig_file) as f:
                data = json.load(f)
            
            compiler_options = data.get("compilerOptions", {})
            if "paths" in compiler_options:
                paths[str(tsconfig_file.relative_to(snapshot_dir))] = compiler_options["paths"]
            
        except Exception as e:
            print(f"Error reading {tsconfig_file}: {e}")
    
    return paths

def find_pyproject_packages(snapshot_dir: Path) -> List[str]:
    """Find Python packages from pyproject.toml files."""
    packages = []
    
    for pyproject_file in snapshot_dir.rglob("pyproject.toml"):
        try:
            with open(pyproject_file) as f:
                content = f.read()
            
            # Simple extraction of package names (could be improved with proper TOML parsing)
            if "name =" in content:
                for line in content.split('\n'):
                    if line.strip().startswith('name ='):
                        name = line.split('=')[1].strip().strip('"\'')
                        packages.append(name)
                        break
            
        except Exception as e:
            print(f"Error reading {pyproject_file}: {e}")
    
    return packages

def calculate_content_hash(snapshot_dir: Path) -> str:
    """Calculate a hash of the repository content for caching."""
    hasher = hashlib.sha256()
    
    # Hash all source files
    source_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.toml', '.yaml', '.yml'}
    
    for file_path in sorted(snapshot_dir.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in source_extensions:
            try:
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())
            except OSError:
                continue
    
    return hasher.hexdigest()

def run_preflight_scan(snapshot_dir: Path) -> PreflightResult:
    """Run the complete pre-flight scan."""
    print(f"Running preflight scan on {snapshot_dir}")
    
    frameworks = detect_frameworks(snapshot_dir)
    workspace = detect_workspace(snapshot_dir)
    big_files = find_big_files(snapshot_dir)
    binary_files = find_binary_files(snapshot_dir)
    env_files = find_env_files(snapshot_dir)
    tsconfig_paths = parse_tsconfig_paths(snapshot_dir)
    pyproject_packages = find_pyproject_packages(snapshot_dir)
    content_hash = calculate_content_hash(snapshot_dir)
    
    return PreflightResult(
        frameworks=frameworks,
        workspace=workspace,
        config_files={},  # Could be expanded
        big_files=big_files,
        binary_files=binary_files,
        env_files=env_files,
        tsconfig_paths=tsconfig_paths,
        pyproject_packages=pyproject_packages,
        content_hash=content_hash
    )
