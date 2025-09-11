from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
import itertools

logger = logging.getLogger(__name__)

from .llm.client import LLMClient
from .llm.prompts import sanitize_for_llm
from .utils.io import write_json_atomic
from .config import settings
from .observability import get_metrics_collector

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---- Capability Defaults & Fallbacks ----
REQUIRED_KEYS = {
    "id": "",
    "name": "",
    "purpose": "",
    "entryPoints": [],
    "controlFlow": [],
    "swimlanes": {"web": [], "api": [], "workers": [], "other": []},
    "nodeIndex": {},
    "steps": [],
    "dataFlow": {"inputs": [], "stores": [], "externals": []},
    "contracts": [],
    "policies": [],
    "suspectRank": [],
    "recentChanges": []
}

def ensure_capability_defaults(cap: dict) -> dict:
    """Fill in missing keys with safe defaults."""
    fixed = cap.copy()
    for key, default in REQUIRED_KEYS.items():
        if key not in fixed:
            fixed[key] = default
    return fixed

def norm(path: str, repo_root: str) -> str:
    """Normalize paths to repo-relative format, handling both absolute and relative paths."""
    if not path:
        return path
    
    try:
        # For non-repo modules ("fastapi", "json", etc.), return just the module id
        if not path.startswith(("backend/", "apps/", "src/", "/")) and "/" not in path:
            return path.split("/")[-1]
        
        # If path is already relative and starts with backend/, apps/, or src/, return as-is
        if path.startswith(("backend/", "apps/", "src/")):
            return path
        
        # For absolute paths, normalize using Path.resolve()
        if path.startswith("/"):
            path_obj = Path(path).resolve()
            repo_obj = Path(repo_root).resolve()
            
            # If path is under repo_root, use relative_to for clean relative path
            if path_obj.is_relative_to(repo_obj):
                return path_obj.relative_to(repo_obj).as_posix()
            
            # If path contains /snapshot/, extract the part after it
            path_str = path_obj.as_posix()
            if "/snapshot/" in path_str:
                return path_str.split("/snapshot/", 1)[1]
        
        # For other paths, return as POSIX string
        return str(path).replace("\\", "/")
        
    except (ValueError, OSError):
        # Fallback for malformed paths - ensure POSIX format
        return str(path).replace("\\", "/")

def to_repo_relative(path: str, repo_root: Path) -> str:
    """Legacy wrapper for norm() function."""
    return norm(path, str(repo_root))

def anchors_to_entrypoints(anchors: List[dict], repo_root: str) -> List[dict]:
    """Convert anchors to entrypoints with framework/kind detection."""
    out = []
    for a in anchors or []:
        p = norm(a["path"], repo_root)
        fw = "fastapi" if p.endswith(".py") else "unknown"
        k = a.get("kind") or ("api" if "routers/" in p or "main.py" in p else "other")
        out.append({"path": p, "framework": fw, "kind": k, "route": a.get("route")})
    return out

def lane_for_path(p: str) -> str:
    """Determine swimlane for a file path."""
    p = p.lower()
    if "/routers/" in p or "/services/" in p or "/models/" in p or "/schemas/" in p or p.endswith("/main.py"):
        return "api"
    if "/workers/" in p or "/jobs/" in p or "/queue/" in p:
        return "workers"
    if "/app/" in p and (p.endswith(".tsx") or p.endswith(".ts") or p.endswith(".jsx")):
        return "web"
    return "api"  # default for this backend repo

def build_swimlanes(all_files: List[str]) -> dict:
    """Build swimlanes from file paths."""
    lanes = {"web": [], "api": [], "workers": [], "other": []}
    for f in all_files:
        lanes[lane_for_path(f)].append(f)
    return lanes

def filter_edges(edges: List[dict], repo_root: str) -> List[dict]:
    """Filter edges to only include repo-to-repo connections."""
    def is_repo_file(x): 
        return norm(x, repo_root).startswith(("backend/", "apps/", "src/"))
    
    out = []
    for e in edges or []:
        src, dst = norm(e["from"], repo_root), norm(e["to"], repo_root)
        if not (is_repo_file(src) and is_repo_file(dst)):
            continue  # drop edges to 'fastapi', 'pydantic', etc.
        k = e.get("kind") or "call"
        out.append({"from": src, "to": dst, "kind": k})
    return out

def _derive_repo_to_repo_edges(files_list: List[dict], repo_root: str) -> List[dict]:
    """Derive repo-to-repo edges from import relationships."""
    edges = []
    
    for f in files_list:
        src_path = norm(f["path"], repo_root)
        if not src_path.startswith(("backend/", "apps/", "src/")):
            continue
            
        imports = f.get("imports", [])
        for imp in imports:
            # Check if import resolves to a repo file
            resolved = imp.get("resolved", "")
            if resolved and norm(resolved, repo_root).startswith(("backend/", "apps/", "src/")):
                dst_path = norm(resolved, repo_root)
                if src_path != dst_path:  # Avoid self-loops
                    edges.append({
                        "from": src_path,
                        "to": dst_path,
                        "kind": "import"
                    })
    
    return edges

def normalize_capability_paths(cap: dict, repo_root: Path) -> dict:
    """Normalize all paths in capability to repo-relative format."""
    # Normalize entryPoints (legacy format)
    cap["entryPoints"] = [to_repo_relative(p, repo_root) for p in cap.get("entryPoints", [])]
    
    # Normalize entrypoints (new format)
    for ep in cap.get("entrypoints", []):
        if "path" in ep:
            ep["path"] = to_repo_relative(ep["path"], repo_root)
    
    # Normalize controlFlow edges
    for edge in cap.get("controlFlow", []):
        if "from" in edge:
            edge["from"] = to_repo_relative(edge["from"], repo_root)
        if "to" in edge:
            edge["to"] = to_repo_relative(edge["to"], repo_root)
    
    # Normalize swimlanes
    for lane, paths in cap.get("swimlanes", {}).items():
        cap["swimlanes"][lane] = [to_repo_relative(p, repo_root) for p in paths]
    
    # Normalize dataFlow externals
    for ext in cap.get("dataFlow", {}).get("externals", []):
        if "client" in ext:
            ext["client"] = to_repo_relative(ext["client"], repo_root)
        if "path" in ext:
            ext["path"] = to_repo_relative(ext["path"], repo_root)
    
    # Normalize policies and contracts paths
    for policy in cap.get("policies", []):
        if "path" in policy:
            policy["path"] = to_repo_relative(policy["path"], repo_root)
        if "appliedAt" in policy:
            policy["appliedAt"] = to_repo_relative(policy["appliedAt"], repo_root)
    
    for contract in cap.get("contracts", []):
        if "path" in contract:
            contract["path"] = to_repo_relative(contract["path"], repo_root)
    
    return cap

def provide_trivial_fallbacks(cap: dict) -> dict:
    """Provide minimal fallbacks for sparse repos."""
    # Ensure purpose exists
    if not cap.get("purpose"):
        cap["purpose"] = "Capability auto-generated for sparse repo"
    
    # Ensure at least one step exists
    if not cap.get("steps") and cap.get("entryPoints"):
        cap["steps"] = [{
            "title": "Entry point",
            "description": "Starts here",
            "fileId": cap["entryPoints"][0]
        }]
    
    # Build basic nodeIndex
    node_index = cap.get("nodeIndex", {})
    for ep in cap.get("entryPoints", []):
        node_index[ep] = {"role": "entrypoint", "lane": "web"}
    
    for edge in cap.get("controlFlow", []):
        if "from" in edge:
            node_index.setdefault(edge["from"], {"role": "handler", "lane": "api"})
        if "to" in edge:
            node_index.setdefault(edge["to"], {"role": "sink", "lane": "other"})
    
    cap["nodeIndex"] = node_index
    
    return cap

def add_camelcase_mirrors(cap: dict) -> dict:
    """Add snake_case mirrors for backward compatibility."""
    cap["entrypoints"] = cap.get("entryPoints", [])
    cap["control_flow"] = cap.get("controlFlow", [])
    cap["data_flow"] = cap.get("dataFlow", {})
    return cap

def _write_capability_with_defaults(repo_dir: Path, cap: dict, cap_id: str):
    """Write capability with comprehensive defaults and path normalization."""
    # Apply all post-processing steps
    cap = ensure_capability_defaults(cap)
    cap = normalize_capability_paths(cap, repo_dir)
    cap = provide_trivial_fallbacks(cap)
    cap = add_camelcase_mirrors(cap)
    
    # Ensure directory exists
    cap_path = repo_dir / "capabilities" / cap_id / "capability.json"
    cap_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write with proper formatting atomically
    write_json_atomic(cap_path, cap)


# ---- Types (minimal, runtime-validated) ----
Lane = Literal["web", "api", "workers", "other"]
EdgeKind = Literal["import", "call", "http", "queue", "webhook"]


@dataclass
class Anchor:
    path: str
    kind: Literal["ui", "api", "webhook"]
    route: str


# ---- UI-aligned helpers (pure, framework-agnostic) ----
def _infer_framework_from_path(path: str) -> str:
    p = (path or "").lower()
    # Next.js App Router
    if "/src/app/" in p or p.endswith("/page.tsx") or p.endswith("/layout.tsx"):
        return "nextjs"
    # Express/Koa/Fastify style
    if "/routes/" in p or "/middleware/" in p:
        return "express"
    # Generic React
    if p.endswith(".tsx") or p.endswith(".jsx"):
        return "react"
    # Python FastAPI
    if p.endswith(".py") and ("fastapi" in p or "/api/" in p or "/routes/" in p):
        return "fastapi"
    # Fallback
    return "unknown"


def _build_swimlanes(nodes: List[Dict[str, Any]]) -> Dict[Lane, List[str]]:
    lanes: Dict[Lane, List[str]] = {"web": [], "api": [], "workers": [], "other": []}
    for n in nodes or []:
        lane = n.get("lane", "other")
        path = n.get("path")
        if path:
            lanes.setdefault(lane, []).append(path)
    return lanes


def _to_repo_relative(p: str, base: Path) -> str:
    if not p:
        return p
    s = str(p)
    snap = str((base / "snapshot").resolve())
    if s.startswith(snap):
        rel = s[len(snap):].lstrip("/")
        return rel
    b = str(base.resolve())
    if s.startswith(b):
        rel = s[len(b):].lstrip("/")
        return rel
    return s


def _classify_policy_type(policy: Dict[str, Any]) -> str:
    name = (policy.get("name") or "").lower()
    path = (policy.get("path") or "").lower()
    if "auth" in name or "auth" in path or "middleware" in path:
        return "middleware"
    if "zod" in name or "schema" in name or "validate" in name:
        return "schemaGuard"
    if "cors" in name or "cors" in path:
        return "cors"
    return "unknown"


def _infer_lane_from_path(path: str) -> Lane:
    p = (path or "").lower()
    if "/src/app/" in p and (p.endswith(".tsx") or p.endswith(".jsx")):
        return "web"
    if "/api/" in p or "/routes/" in p or p.endswith("/route.ts") or p.endswith("/route.js"):
        return "api"
    if "/workers/" in p or "worker" in p or "queue" in p:
        return "workers"
    return "other"


def _resolve_anchor_paths_to_index(anchors: List[Anchor], files_idx: Dict[str, Dict[str, Any]]) -> List[str]:
    paths_in_index = set(files_idx.keys())
    resolved: List[str] = []
    for a in anchors:
        p = a.path
        if p in paths_in_index:
            resolved.append(p)
            continue
        # Try suffix match to unify absolute/relative duplicates
        matches = [fp for fp in paths_in_index if fp.endswith(p)]
        if matches:
            resolved.append(matches[0])
            continue
        # Try the other way around
        matches = [fp for fp in paths_in_index if p.endswith(fp)]
        if matches:
            resolved.append(matches[0])
            continue
    return list(dict.fromkeys(resolved))


def _collect_neighbor_paths(graph: Dict[str, Any], start_paths: List[str], hops: int = 2) -> List[str]:
    # Build adjacency from graph edges
    edges = graph.get("edges", []) or []
    neighbors: Dict[str, List[str]] = {}
    for e in edges:
        src = e.get("from")
        dst = e.get("resolved") or e.get("to")
        if not src or not dst:
            continue
        neighbors.setdefault(src, []).append(dst)
        neighbors.setdefault(dst, []).append(src)

    frontier = list(start_paths)
    seen: Dict[str, int] = {p: 0 for p in start_paths}
    for _ in range(hops):
        new_frontier: List[str] = []
        for p in frontier:
            for q in neighbors.get(p, [])[:200]:  # limit fanout
                if q not in seen:
                    seen[q] = seen[p] + 1
                    new_frontier.append(q)
        frontier = new_frontier
        if not frontier:
            break
    return list(seen.keys())


def _edge_subset_within(paths: List[str], graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    allowed = set(paths)
    out: List[Dict[str, Any]] = []
    for e in graph.get("edges", []) or []:
        src = e.get("from")
        dst = e.get("resolved") or e.get("to")
        if src in allowed and dst in allowed:
            out.append({"from": src, "to": dst, "kind": "import" if not e.get("external") else "call"})
    return out[:2000]


def _enhance_control_flow(edges: List[Dict[str, Any]], lane_for: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in edges or []:
        k = e.get("kind")
        src = e.get("from")
        dst = e.get("to")
        src_lane = lane_for.get(src, "other")
        dst_lane = lane_for.get(dst, "other")
        kind = k
        # Promote UI component relationships
        if k == "import" and src_lane == "web" and dst_lane == "web":
            kind = "component"
        # HTTP edges: web -> api
        if src_lane == "web" and dst_lane == "api" and k in ("call", "import"):
            kind = "http"
        # Webhook edges: payment/webhook related
        if ("webhook" in (dst or "").lower()) or ("webhook" in (src or "").lower()):
            kind = "webhook"
        # Queue/worker heuristics
        if any(s in (dst or "").lower() for s in ["enqueue", "queue"]) or any(s in (src or "").lower() for s in ["enqueue", "queue"]):
            kind = "queue"
        if k == "call" and (src_lane == "workers" or dst_lane == "workers"):
            kind = "worker"
        out.append({"from": src, "to": dst, "kind": kind})
    return out


def _synthesize_example(item: Dict[str, Any]) -> Dict[str, Any]:
    t = (item.get("type") or "").lower()
    name = (item.get("name") or item.get("client") or item.get("path") or "").lower()
    if t == "dbmodel":
        if "order" in name:
            return {"id": "ord_123", "email": "user@example.com", "amount": 4999, "status": "PAID", "createdAt": "2025-01-01T00:00:00Z"}
        if "inventory" in name:
            return {"sku": "SKU-1", "reserved": 1, "available": 42}
        return {"id": "row_1", "createdAt": "2025-01-01T00:00:00Z"}
    if t == "queue":
        return {"queue": item.get("name") or "jobs", "job": {"id": "job_1"}}
    if t == "api":
        if "stripe" in name:
            return {"amount": 4999, "currency": "usd", "customer_email": "user@example.com"}
        return {"request": {"example": True}, "response": {"ok": True}}
    if t == "smtp":
        return {"to": "user@example.com", "template": "example", "variables": {}}
    if t == "requestschema":
        return {"example": True}
    if t == "env":
        return {item.get("key") or "ENV": "***"}
    return {"example": True}


def _compute_status() -> str:
    # Placeholder heuristic until runtime signals are integrated
    return "healthy"

def _normalize_edges(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize edges: dedupe, prune self-loops, sort deterministically."""
    # Remove self-loops (unless explicitly allowed)
    filtered_edges = []
    for edge in edges:
        if edge.get("from") != edge.get("to"):
            filtered_edges.append(edge)
    
    # Deduplicate by (from, to, kind)
    seen = set()
    unique_edges = []
    for edge in filtered_edges:
        key = (edge.get("from"), edge.get("to"), edge.get("kind"))
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)
    
    # Sort deterministically
    unique_edges.sort(key=lambda e: (e.get("from", ""), e.get("to", ""), e.get("kind", "")))
    return unique_edges

def _normalize_paths(paths: List[str]) -> List[str]:
    """Normalize path arrays: deduplicate and sort."""
    return sorted(list(set(paths)))

def _normalize_swimlanes(swimlanes: Dict[str, List[str]], files_idx: Dict[str, Any]) -> Dict[str, List[str]]:
    """Normalize swimlanes: ensure all lanes exist, sort paths, drop missing files."""
    normalized = {}
    for lane in ["web", "api", "workers", "other"]:
        paths = swimlanes.get(lane, [])
        # Filter to only existing files and normalize
        valid_paths = [p for p in paths if p in files_idx]
        normalized[lane] = _normalize_paths(valid_paths)
    return normalized

def _normalize_anchors(anchors: List[Anchor], files_idx: Dict[str, Any]) -> Tuple[List[Anchor], List[str]]:
    """Normalize anchors: resolve to canonical paths, drop unresolved, collect warnings."""
    valid_anchors = []
    warnings = []
    
    for anchor in anchors:
        if anchor.path in files_idx:
            valid_anchors.append(anchor)
        else:
            warnings.append(f"Anchor path not found in files: {anchor.path}")
    
    return valid_anchors, warnings

def _validate_references(cap: Dict[str, Any], files_idx: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that all referenced paths exist in files_idx, mark missing ones."""
    warnings = []
    
    # Validate entryPoints
    valid_entrypoints = []
    for ep in cap.get("entryPoints", []):
        if ep in files_idx:
            valid_entrypoints.append(ep)
        else:
            warnings.append(f"Missing entrypoint: {ep}")
    cap["entryPoints"] = valid_entrypoints
    
    # Validate swimlanes
    for lane, paths in cap.get("swimlanes", {}).items():
        valid_paths = []
        for path in paths:
            if path in files_idx:
                valid_paths.append(path)
            else:
                warnings.append(f"Missing swimlane path in {lane}: {path}")
        cap["swimlanes"][lane] = valid_paths
    
    # Validate control flow edges
    valid_edges = []
    for edge in cap.get("controlFlow", []):
        from_path = edge.get("from")
        to_path = edge.get("to")
        if from_path in files_idx and to_path in files_idx:
            valid_edges.append(edge)
        else:
            if from_path not in files_idx:
                warnings.append(f"Missing control flow source: {from_path}")
            if to_path not in files_idx:
                warnings.append(f"Missing control flow target: {to_path}")
    cap["controlFlow"] = valid_edges
    
    # Add warnings to capability if any
    if warnings:
        cap["warnings"] = cap.get("warnings", []) + warnings
    
    return cap


# ---- IO Helpers ----
def _repo_paths(base: Path) -> Dict[str, Path]:
    caps_dir = base / "capabilities"
    return {
        "files": base / "files.json",
        "graph": base / "graph.json",
        "routes": base / "routes.json",
        "caps_dir": caps_dir,
        "index": caps_dir / "index.json",
    }


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: Any) -> None:
    """Write JSON atomically using the same utility as summarizer."""
    write_json_atomic(p, obj)


# ---- Route grouping ----
def _normalize_param(segment: str) -> str:
    """Normalize route parameter segments to a common format."""
    # Express/Next.js dynamic routes
    if segment.startswith("[") and segment.endswith("]"):
        return "{" + segment[1:-1] + "}"
    # Express/FastAPI params
    if segment.startswith(":"):
        return "{" + segment[1:] + "}"
    # FastAPI path params
    if segment.startswith("{") and segment.endswith("}"):
        return segment
    return segment


def _normalize_route(route: str, strip_method: bool = True) -> str:
    """Normalize route paths to a canonical form."""
    if not route:
        return "/"
    
    # Extract HTTP method if present (e.g., "GET /users" -> "/users")
    r = route.strip()
    method = ""
    if strip_method and " " in r:
        method, r = r.split(" ", 1)
        r = r.strip()
    
    # Ensure leading slash, trim trailing slash
    if not r.startswith("/"):
        r = "/" + r
    if len(r) > 1 and r.endswith("/"):
        r = r[:-1]
    
    # Normalize path parameters
    segments = r.split("/")
    normalized = "/".join(_normalize_param(s) for s in segments if s)
    
    return f"{method} /{normalized}".strip() if method and not strip_method else f"/{normalized}"


def _route_key(route: str, kind: str) -> str:
    """Generate grouping key for a route."""
    r = _normalize_route(route)
    
    # Strip /api prefix for API routes to pair with UI
    if kind == "api" and r.startswith("/api/"):
        r = r[4:]
    
    # Extract meaningful path segments
    segments = [s for s in r.split("/") if s and not s.startswith("{")]
    if not segments:
        return "root"
    
    # Use first two non-param segments as key
    key = "/".join(segments[:2])
    return key


def _group_routes(routes: List[Dict[str, Any]]) -> List[List[Anchor]]:
    """Group routes by semantic similarity."""
    buckets: Dict[str, List[Anchor]] = {}
    
    # First pass: group by semantic key
    for r in routes:
        route = r.get("route", "")
        kind = r.get("kind", "ui")
        path = r.get("path", "")
        
        # Create anchor with normalized route
        norm_route = _normalize_route(route)
        a = Anchor(path=path, kind=kind, route=norm_route)
        
        # Group by semantic key
        key = _route_key(route, kind)
        buckets.setdefault(key, []).append(a)
    
    # Second pass: ensure each group has consistent route prefix
    groups: List[List[Anchor]] = []
    for anchors in buckets.values():
        if len(anchors) == 1:
            groups.append(anchors)
            continue
            
        # For multi-anchor groups, try to find a common prefix
        routes = [a.route for a in anchors]
        prefix = routes[0]
        for r in routes[1:]:
            while not r.startswith(prefix) and "/" in prefix:
                prefix = "/".join(prefix.split("/")[:-1])
            if not prefix:
                prefix = "/"
                break
        
        # Update routes to use common prefix
        normalized = [Anchor(path=a.path, kind=a.kind, route=prefix) for a in anchors]
        groups.append(normalized)
    
    return groups


# ---- LLM prompts (schemas) ----
EXPANSION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "lane": {"type": "string", "enum": ["web", "api", "workers", "other"]}},
                "required": ["path", "lane"],
                "additionalProperties": True,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "kind": {"type": "string", "enum": ["import", "call", "http", "queue", "webhook"]},
                },
                "required": ["from", "to", "kind"],
                "additionalProperties": False,
            },
        },
        "omissions": {
            "type": "array",
            "items": {"type": "object", "properties": {"path": {"type": "string"}, "reason": {"type": "string"}}, "required": ["path", "reason"]},
        },
    },
    "required": ["nodes", "edges"],
    "additionalProperties": True,
}

DATA_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "inputs": {"type": "array"},
        "stores": {"type": "array"},
        "externals": {"type": "array"},
        "contracts": {"type": "array"},
        "policies": {"type": "array"},
    },
    "required": ["inputs", "stores", "externals", "contracts", "policies"],
}

NARRATIVE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"steps": {"type": "array"}},
    "required": ["steps"],
}

TOUCHES_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"dataItem": {"type": "string"}, "touches": {"type": "array"}},
    "required": ["dataItem", "touches"],
}

SUSPECTS_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "items": {"type": "object", "properties": {"path": {"type": "string"}, "score": {"type": "number"}, "reason": {"type": "string"}}, "required": ["path", "score", "reason"]},
}


# ---- LLM wrappers ----
async def _llm_expand(llm: LLMClient, anchors: List[Anchor], files: Dict[str, Any], graph: Dict[str, Any], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    # Build focused neighbor context around anchors (up to 2 hops)
    files_idx = {f["path"]: f for f in files.get("files", [])}
    resolved_anchors = _resolve_anchor_paths_to_index(anchors, files_idx)
    if not resolved_anchors:
        resolved_anchors = [a.path for a in anchors]
    context_paths = _collect_neighbor_paths(graph, resolved_anchors, hops=2)
    # Ensure anchors are present
    for p in resolved_anchors:
        if p not in context_paths:
            context_paths.append(p)
    # Prepare context metadata and edge subset
    subset = [{
        "path": p,
        "lang": (files_idx.get(p, {}) or {}).get("language"),
        "frameworkHints": (files_idx.get(p, {}) or {}).get("hints", {}),
        "size": (files_idx.get(p, {}) or {}).get("size"),
        "symbols": (files_idx.get(p, {}) or {}).get("symbols", {}),
    } for p in context_paths][:400]
    raw_edges = _edge_subset_within(context_paths, graph)
    route = anchors[0].route if anchors else "/"
    # Sanitize context to prevent secret leakage
    sanitized_anchors = sanitize_for_llm(str([a.__dict__ for a in anchors]))
    sanitized_subset = sanitize_for_llm(str(subset))
    sanitized_edges = sanitize_for_llm(str(raw_edges))
    
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Be precise, conservative, and avoid hallucinations. respond with json only. always return strict json that matches the provided schema."},
        {"role": "user", "content": f"ANCHORS:\n{sanitized_anchors}\n\nCONTEXT NODES (focused):\n{sanitized_subset}\n\nRAW EDGES WITHIN CONTEXT (may be incomplete):\n{sanitized_edges}\n\nTASK:\nInfer the minimal end-to-end set of files for the capability serving route {route}. Assign lanes (web|api|workers|other) and propose edges (import|call|http|queue|webhook). Exclude shared infra. return json only per schema."},
    ]
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            res = await llm.acomplete_json(messages, EXPANSION_SCHEMA)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_expand", settings.LLM_MODEL, "success", duration_ms)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_expand", settings.LLM_MODEL, "error", duration_ms)
            res = {"nodes": [], "edges": []}

    # Fallback: if model returns empty, synthesize from context
    if not res.get("nodes"):
        limit = getattr(settings, "LLM_FILE_SUMMARY_BUDGET", 50)
        nodes = [{"path": p, "lane": _infer_lane_from_path(p)} for p in context_paths[:limit]]
        edges = raw_edges[:1000]
        
        # Add warning if truncation occurred
        if len(context_paths) > limit:
            logger.warning(f"Trimmed context files from {len(context_paths)} to {limit} due to budget limit")
        
        return {"nodes": nodes, "edges": edges}
    return res


async def _llm_extract_data(llm: LLMClient, nodes: List[Dict[str, Any]], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    # Sanitize context to prevent secret leakage
    sanitized_nodes = sanitize_for_llm(str(nodes))
    
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. be precise, conservative. respond with json only. always return strict json that matches the provided schema."},
        {"role": "user", "content": f"NODES:\n{sanitized_nodes}\n\nTASK:\nIdentify inputs, stores, externals, contracts, policies across these nodes. Include concise 'why' citing which file suggests it. return json only per schema."},
    ]
    
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            result = await llm.acomplete_json(messages, DATA_SCHEMA)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_data_extract", settings.LLM_MODEL, "success", duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_data_extract", settings.LLM_MODEL, "error", duration_ms)
            raise


async def _llm_summarize_file(llm: LLMClient, path: str, lane: Lane, neighbors_in: List[str], neighbors_out: List[str], symbols: Dict[str, Any], semaphore: asyncio.Semaphore) -> str:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Return one or two concise sentences, present tense, no speculation."},
        {"role": "user", "content": f"FILE: {path}\nLANE: {lane}\nNEIGHBORS IN: {neighbors_in}\nNEIGHBORS OUT: {neighbors_out}\nSYMBOLS: {symbols}\nCONSTRAINTS: ≤2 sentences, present tense, no speculation, mention role. RETURN: plain text (≤200 chars)."},
    ]
    # Use JSON mode wrapper to keep caching uniform; wrap text
    schema = {"type": "object", "properties": {"t": {"type": "string"}}, "required": ["t"]}
    
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            res = await llm.acomplete_json(messages, schema)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_file_summary", settings.LLM_MODEL, "success", duration_ms)
            return str(res.get("t", ""))[:400]
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_file_summary", settings.LLM_MODEL, "error", duration_ms)
            raise


async def _llm_narrative(llm: LLMClient, name: str, anchors: List[str], lanes: Dict[Lane, List[str]], edges: List[Dict[str, Any]], data: Dict[str, Any], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. respond with json only. always return strict json that matches the provided schema."},
        {"role": "user", "content": f"CAPABILITY: {name}\nANCHORS: {anchors}\nLANES: {lanes}\nEDGES: {edges}\nDATA: {data}\n\nTASK:\nWrite 6–10 ordered steps (happy path). Add 2–3 edge/failure cases. return json only per schema as {{steps:[{{label, detail, scenario}}]}}."},
    ]
    
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            result = await llm.acomplete_json(messages, NARRATIVE_SCHEMA)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_narrative", settings.LLM_MODEL, "success", duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_narrative", settings.LLM_MODEL, "error", duration_ms)
            raise


async def _llm_touches(llm: LLMClient, data_item: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. respond with json only. always return strict json that matches the provided schema."},
        {"role": "user", "content": f"DATA ITEM: {data_item}\nNODES: {nodes}\nEDGES: {edges}\n\nTASK:\nList files that likely READ vs WRITE (or enqueue/consume/call) this item within this capability only. For each, provide {{actorPath, action, via, reason}}. return json only per schema."},
    ]
    
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            result = await llm.acomplete_json(messages, TOUCHES_SCHEMA)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_touches", settings.LLM_MODEL, "success", duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_touches", settings.LLM_MODEL, "error", duration_ms)
            raise


async def _llm_suspects(llm: LLMClient, context: Dict[str, Any], semaphore: asyncio.Semaphore) -> List[Dict[str, Any]]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"CONTEXT: {context}\n\nTASK:\nRank top 5 likely-problem files (0..1 score), with brief reason, prioritizing central writers and external callers on critical path. RETURN array of SuspectOut."},
    ]
    
    metrics = get_metrics_collector()
    start_time = time.time()
    
    async with semaphore:
        try:
            result = await llm.acomplete_json(messages, SUSPECTS_SCHEMA)
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_suspects", settings.LLM_MODEL, "success", duration_ms)
            return result  # type: ignore
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_llm_call("capability_suspects", settings.LLM_MODEL, "error", duration_ms)
            raise


def _derive_control_flow_from_graph(nodes: List[Dict[str, Any]], graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive control flow edges from the graph if LLM returned empty edges."""
    node_paths = {n.get("path") for n in nodes}
    graph_edges = graph.get("edges", [])
    
    # Filter graph edges to only include those between capability nodes
    control_edges = []
    for edge in graph_edges:
        from_path = edge.get("from", "")
        to_path = edge.get("to", "") or edge.get("resolved", "")
        
        if from_path in node_paths and to_path in node_paths:
            kind = edge.get("kind", "import")
            # Map graph edge kinds to capability edge kinds
            if kind == "import":
                kind = "import"
            elif kind == "call":
                kind = "call"
            elif kind in ("http", "fetch"):
                kind = "http"
            else:
                kind = "call"  # default
            
            control_edges.append({
                "from": from_path,
                "to": to_path,
                "kind": kind
            })
    
    return control_edges[:100]  # limit to prevent explosion


def _backfill_dataflow_heuristics(data: Dict[str, Any], nodes: List[Dict[str, Any]], files_idx: Dict[str, Any]) -> Dict[str, Any]:
    """Add heuristic candidates for inputs, stores, externals if LLM results are sparse."""
    result = dict(data)
    
    # If inputs are sparse, scan for common patterns
    if len(result.get("inputs", [])) < 2:
        heuristic_inputs = []
        for node in nodes:
            path = node.get("path", "")
            if "schema" in path.lower() or "types" in path.lower():
                heuristic_inputs.append({
                    "type": "requestSchema",
                    "name": path.split("/")[-1].replace(".ts", "").replace(".js", ""),
                    "path": path,
                    "why": "Schema/types file suggests request structure"
                })
            elif ".env" in path:
                heuristic_inputs.append({
                    "type": "env",
                    "key": "CONFIG_KEY",
                    "path": path,
                    "why": "Environment file suggests configuration"
                })
        result["inputs"] = (result.get("inputs", []) + heuristic_inputs)[:10]
    
    # If stores are sparse, scan for database/model patterns
    if len(result.get("stores", [])) < 1:
        heuristic_stores = []
        for node in nodes:
            path = node.get("path", "")
            if any(x in path.lower() for x in ["model", "repo", "database", "prisma", "schema"]):
                heuristic_stores.append({
                    "type": "dbModel",
                    "name": path.split("/")[-1].replace(".ts", "").replace(".js", ""),
                    "path": path,
                    "why": "Database/model file suggests data store"
                })
            elif "queue" in path.lower() or "job" in path.lower():
                heuristic_stores.append({
                    "type": "queue",
                    "name": "jobs",
                    "path": path,
                    "why": "Queue/job file suggests async processing"
                })
        result["stores"] = (result.get("stores", []) + heuristic_stores)[:5]
    
    # If externals are sparse, scan for client patterns
    if len(result.get("externals", [])) < 1:
        heuristic_externals = []
        for node in nodes:
            path = node.get("path", "")
            if "client" in path.lower():
                if "stripe" in path.lower():
                    heuristic_externals.append({
                        "type": "api",
                        "name": "Stripe",
                        "client": path,
                        "why": "Stripe client file suggests payment processing"
                    })
                elif "email" in path.lower() or "mail" in path.lower():
                    heuristic_externals.append({
                        "type": "smtp",
                        "name": "Email",
                        "client": path,
                        "why": "Email client suggests notification service"
                    })
                else:
                    heuristic_externals.append({
                        "type": "api",
                        "name": "External API",
                        "client": path,
                        "why": "Client file suggests external service integration"
                    })
        result["externals"] = (result.get("externals", []) + heuristic_externals)[:5]
    
    return result


def _enrich_policies_contracts_heuristics(policies: List[Dict[str, Any]], contracts: List[Dict[str, Any]], nodes: List[Dict[str, Any]], files_idx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Add heuristic policies and contracts if sparse."""
    enriched_policies = list(policies)
    enriched_contracts = list(contracts)
    
    # Scan nodes for common policy patterns
    if len(enriched_policies) < 2:
        for node in nodes:
            path = node.get("path", "")
            symbols = files_idx.get(path, {}).get("symbols", {})
            functions = symbols.get("functions", [])
            
            # Look for auth/middleware patterns
            if any("auth" in f.lower() for f in functions) or "middleware" in path.lower():
                enriched_policies.append({
                    "name": "authentication",
                    "path": path,
                    "type": "middleware",
                    "appliedAt": path
                })
            
            # Look for validation patterns
            if any("validate" in f.lower() or "schema" in f.lower() for f in functions):
                enriched_policies.append({
                    "name": "inputValidation",
                    "path": path,
                    "type": "schemaGuard",
                    "appliedAt": path
                })
    
    # Scan nodes for contract patterns
    if len(enriched_contracts) < 2:
        for node in nodes:
            path = node.get("path", "")
            symbols = files_idx.get(path, {}).get("symbols", {})
            
            # TypeScript interfaces/types
            if path.endswith((".ts", ".tsx")) and any(x in symbols for x in ["interfaces", "types"]):
                enriched_contracts.append({
                    "name": path.split("/")[-1].replace(".ts", "").replace(".tsx", ""),
                    "kind": "ts.Interface",
                    "path": path,
                    "fields": list(symbols.get("interfaces", {}).keys())[:5]
                })
            
            # Prisma models
            if "prisma" in path.lower() or "schema.prisma" in path:
                enriched_contracts.append({
                    "name": "DatabaseSchema",
                    "kind": "prisma.Model",
                    "path": path,
                    "fields": []
                })
    
    return enriched_policies[:5], enriched_contracts[:5]


# ---- Core build ----
async def _build_capability(files_payload: Dict[str, Any], graph_payload: Dict[str, Any], repo_dir: Path, anchors: List[Anchor], semaphore: asyncio.Semaphore) -> Tuple[str, Dict[str, Any]]:
    files_list = files_payload.get("files", [])
    graph = graph_payload

    llm = LLMClient(cache_dir=repo_dir / "cache_llm")
    # Pass full payload so helper can access payload["files"]
    expansion = await _llm_expand(llm, anchors, files_payload, graph, semaphore)

    # Validate graph integrity basics
    node_paths = {n.get("path") for n in expansion.get("nodes", [])}
    edges = [e for e in expansion.get("edges", []) if e.get("from") in node_paths and e.get("to") in node_paths]
    
    # Fallback: derive control flow from graph if LLM edges are empty
    if not edges:
        edges = _derive_control_flow_from_graph(expansion.get("nodes", []), graph)

    data = await _llm_extract_data(llm, expansion.get("nodes", []), semaphore)

    # Build files index once (list of files)
    files_idx = {f["path"]: f for f in files_list}

    # Heuristic backfill for data flow if LLM returned sparse results
    data = _backfill_dataflow_heuristics(data, expansion.get("nodes", []), files_idx)

    # File summaries (per node)
    summaries_file: Dict[str, str] = {}
    for n in expansion.get("nodes", []):
        p = n.get("path")
        neighbors_in = [e.get("from") for e in edges if e.get("to") == p]
        neighbors_out = [e.get("to") for e in edges if e.get("from") == p]
        text = await _llm_summarize_file(llm, p, n.get("lane", "other"), neighbors_in, neighbors_out, files_idx.get(p, {}).get("symbols", {}), semaphore)
        summaries_file[p] = text

    # Folder rollups: simple heuristic grouping by top folder
    folder_rollup: Dict[str, str] = {}
    for p, s in summaries_file.items():
        parts = p.split("/")
        if len(parts) > 2:
            key = "/".join(parts[:2])
            if key not in folder_rollup:
                folder_rollup[key] = s

    # Narrative & lanes mapping - use the new build_swimlanes function
    # lanes_map is already set above by build_swimlanes(all_files)
    # Ensure lanes_map is properly defined for narrative generation
    if 'lanes_map' not in locals():
        # Rebuild all_files if not defined
        if 'all_files' not in locals():
            all_files = sorted(set([norm(p, str(repo_dir)) for p in files_idx.keys() if norm(p, str(repo_dir)).startswith(("backend/", "apps/", "src/"))]))
        lanes_map = build_swimlanes(all_files)
    
    valid_anchors, anchor_warnings = _normalize_anchors(anchors, files_idx)
    narrative = await _llm_narrative(
        llm,
        name=valid_anchors[0].route if valid_anchors else "Capability",
        anchors=[a.path for a in valid_anchors],
        lanes=lanes_map,
        edges=edges,
        data=data,
        semaphore=semaphore,
    )

    # Touches
    touches: Dict[str, Any] = {}
    for st in data.get("stores", []):
        di = st.get("name") or st.get("path") or "store"
        touches[di] = await _llm_touches(llm, di, expansion.get("nodes", []), edges, semaphore)
    for ex in data.get("externals", []):
        di = ex.get("name") or ex.get("path") or "external"
        touches[di] = await _llm_touches(llm, di, expansion.get("nodes", []), edges, semaphore)

    # Build UI-aligned fields using new helper functions
    repo_root = str(repo_dir)
    
    # 1) Promote anchors → entrypoints (and infer framework/kind)
    entrypoints = anchors_to_entrypoints([{"path": a.path, "kind": a.kind, "route": a.route} for a in anchors], repo_root)
    entry_points = [e["path"] for e in entrypoints]
    
    # 2) Fill swimlanes properly
    all_files = sorted(set([norm(p, repo_root) for p in files_idx.keys() if norm(p, repo_root).startswith(("backend/", "apps/", "src/"))]))
    lanes_map = build_swimlanes(all_files)
    
    # 3) Move flow → control_flow and filter out libraries
    control_flow = filter_edges(edges, repo_root)
    
    # If no repo-to-repo edges found, derive them from import relationships
    if not control_flow:
        control_flow = _derive_repo_to_repo_edges(files_list, repo_root)
    
    # Build lane mapping for nodeIndex
    lane_for_path: Dict[str, str] = {}
    for lane, paths in lanes_map.items():
        for p in paths:
            lane_for_path[p] = lane

    # Embed touches/examples in data_flow
    def _embed_touches(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in items or []:
            key_candidates = [it.get("name"), it.get("path"), it.get("client")]
            tchs: List[Dict[str, Any]] = []
            for k in key_candidates:
                if not k:
                    continue
                v = touches.get(k) or touches.get(str(k))
                if isinstance(v, dict):
                    tchs = v.get("touches") or []
                    break
            out.append({**it, "touches": tchs, "example": _synthesize_example(it)})
        return out

    def _rel_item(it: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(it)
        if out.get("path"):
            out["path"] = _to_repo_relative(out["path"], repo_dir)
        if out.get("client"):
            out["client"] = _to_repo_relative(out["client"], repo_dir)
        return out

    # 4) Extract proper data flow from parsed files
    inputs = []
    stores = []
    externals = []
    contracts = []
    
    # Extract from parsed files
    for f in files_list:
        path = norm(f["path"], repo_root)
        symbols = f.get("symbols", {})
        
        # Extract Pydantic models (request schemas + contracts)
        for model in symbols.get("pydanticModels", []):
            model_name = model.get("name", "")
            model_fields = model.get("fields", [])
            
            # Treat request-like models as inputs
            if "/schemas/" in path or model_name.lower().endswith("request"):
                inputs.append({
                    "type": "requestSchema",
                    "name": model_name,
                    "path": path,
                    "fields": model_fields
                })
            
            # All models are contracts
            contracts.append({
                "name": model_name,
                "kind": "pydantic.Model",
                "path": path,
                "fields": model_fields
            })
        
        # Extract SQLAlchemy models (stores + contracts)
        for model in symbols.get("sqlalchemyModels", []):
            model_name = model.get("name", "")
            model_fields = model.get("fields", [])
            
            stores.append({
                "type": "dbModel",
                "name": model_name,
                "path": path,
                "fields": model_fields
            })
            
            contracts.append({
                "name": model_name,
                "kind": "sqlalchemy.Model",
                "path": path,
                "fields": model_fields
            })
        
        # Extract environment variables
        for env_var in symbols.get("envVars", []):
            inputs.append({
                "type": "env",
                "key": env_var,
                "path": path
            })
        
        # Extract external services from imports
        imports = f.get("imports", [])
        for imp in imports:
            module = imp.get("module", "")
            if "openai" in module:
                externals.append({"type": "api", "name": "OpenAI", "client": path})
            elif "smtplib" in module or "sendgrid" in module:
                externals.append({"type": "smtp", "name": "SMTP", "client": path})
            elif "boto3" in module:
                externals.append({"type": "api", "name": "AWS", "client": path})

    data_flow = {
        "inputs": [_rel_item(x) for x in _embed_touches(inputs)],
        "stores": [_rel_item(x) for x in _embed_touches(stores)],
        "externals": [_rel_item(x) for x in _embed_touches(externals)],
    }

    # 7) Extract policies with appliedAt
    policies_typed = []
    for f in files_list:
        path = norm(f["path"], repo_root)
        symbols = f.get("symbols", {})
        
        # Extract FastAPI policies
        for policy in symbols.get("fastapiPolicies", []):
            # Try to resolve appliedAt: if file is a router, appliedAt is the same file
            applied_at = path if "/routers/" in path or "main.py" in path else None
            policies_typed.append({**policy, "appliedAt": applied_at})
    
    # Add LLM-generated policies as fallback
    policies_typed.extend([{**p, "type": _classify_policy_type(p)} for p in data.get("policies", [])])
    
    # Use extracted contracts instead of LLM-generated ones
    contracts = contracts
    
    # Heuristic enrichment for policies and contracts if sparse
    policies_typed, contracts = _enrich_policies_contracts_heuristics(policies_typed, contracts, expansion.get("nodes", []), files_idx)

    # Derive additional fields for UI list
    def _derive_summary_purpose(narr_steps: List[Dict[str, Any]]) -> str:
        if narr_steps:
            return (narr_steps[0].get("label") or narr_steps[0].get("detail") or "").strip()[:160]
        return anchors[0].route if anchors else "Capability"

    def _derive_key_files() -> List[str]:
        # pick top degree nodes from edges within this capability
        deg: Dict[str, int] = {}
        for ed in edges:
            deg[ed["from"]] = deg.get(ed["from"], 0) + 1
            deg[ed["to"]] = deg.get(ed["to"], 0) + 1
        ordered = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)
        return _normalize_paths([p for p, _ in ordered[:6]])

    def _derive_data_flow_fields() -> Dict[str, List[str]]:
        """Extract dataIn, dataOut, orchestrators, sources, sinks from capability data."""
        data_in = []
        data_out = []
        orchestrators = []
        sources = []
        sinks = []
        
        # Data inputs from data_flow
        for inp in data_flow.get("inputs", []):
            if inp.get("type") == "requestSchema":
                data_in.append(inp.get("name", ""))
            elif inp.get("type") == "env":
                data_in.append(inp.get("key", ""))
        
        # Data outputs from data_flow
        for store in data_flow.get("stores", []):
            data_out.append(store.get("name", ""))
        for ext in data_flow.get("externals", []):
            data_out.append(ext.get("name", ""))
        
        # Orchestrators: files with high out-degree in control_flow
        out_degree = {}
        for edge in control_flow:
            out_degree[edge["from"]] = out_degree.get(edge["from"], 0) + 1
        top_orchestrators = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[:3]
        orchestrators = [path for path, _ in top_orchestrators]
        
        # Sources: files that are entrypoints or have no incoming edges
        in_degree = {}
        for edge in control_flow:
            in_degree[edge["to"]] = in_degree.get(edge["to"], 0) + 1
        sources = [ep["path"] for ep in entrypoints]
        sources.extend([path for path, degree in in_degree.items() if degree == 0 and path not in sources])
        
        # Sinks: files with no outgoing edges or terminal operations
        sinks = [path for path in out_degree.keys() if out_degree[path] == 0]
        
        return {
            "dataIn": data_in,
            "dataOut": data_out,
            "orchestrators": orchestrators,
            "sources": sources,
            "sinks": sinks
        }

    narr_steps = narrative.get("steps", [])
    purpose_cap = _derive_summary_purpose(narr_steps)
    key_files = _derive_key_files()
    data_fields = _derive_data_flow_fields()

    # Assemble
    cap_id = f"cap_{anchors[0].route.strip('/').replace('/', '_') or 'root'}"
    capability = {
        "id": cap_id,
        "name": anchors[0].route.strip("/") or "/",
        "purpose": purpose_cap,
        "title": anchors[0].route.strip("/") or "/",
        "status": _compute_status(),
        "anchors": [{"path": _to_repo_relative(a.path, repo_dir), "kind": a.kind, "route": a.route} for a in anchors],
        # Back-compat fields
        "lanes": {k: [{"path": p} for p in v] for k, v in lanes_map.items()},
        "flow": edges,
        "data": {k: v for k, v in data.items() if k in ("inputs", "stores", "externals")},
        # UI-aligned fields
        "entrypoints": entrypoints,
        "entryPoints": entry_points,
        "swimlanes": lanes_map,
        "control_flow": control_flow,
        "data_flow": data_flow,
        "policies": policies_typed,
        "contracts": data.get("contracts", []),
        "summaries": {"file": summaries_file, "folder": folder_rollup, "narrative": narr_steps},
        # Derived fields for list cards
        "keyFiles": key_files,
        "steps": [],
        # Data flow fields for UI
        "dataIn": data_fields["dataIn"],
        "dataOut": data_fields["dataOut"],
        "orchestrators": data_fields["orchestrators"],
        "sources": data_fields["sources"],
        "sinks": data_fields["sinks"],
        # camelCase mirrors
        "controlFlow": control_flow,
        "dataFlow": data_flow,
    }

    # Steps mapping with optional fileId linking (first step → first entrypoint)
    steps: List[Dict[str, Any]] = []
    for idx, s in enumerate(narr_steps):
        file_id = None
        if idx == 0 and entry_points:
            file_id = entry_points[0]
        steps.append({
            "title": s.get("label"),
            "description": s.get("detail"),
            "fileId": file_id,
        })
    capability["steps"] = steps

    # 8) Clean up nodeIndex and warnings - only repo files, normalized paths
    all_nodes = set(itertools.chain.from_iterable(lanes_map.values()))
    in_map: Dict[str, List[str]] = {}
    out_map: Dict[str, List[str]] = {}
    for e in control_flow:
        out_map.setdefault(e["from"], []).append(e["to"])
        in_map.setdefault(e["to"], []).append(e["from"])
    node_index: Dict[str, Any] = {}
    entry_set = {ep["path"] for ep in entrypoints}
    for n in all_nodes:
        # Only include repo files, skip stdlib/external modules
        if not n.startswith(("backend/", "apps/", "src/")):
            continue
            
        incoming = in_map.get(n, [])
        outgoing = out_map.get(n, [])
        role = "entrypoint" if n in entry_set else ("sink" if len(outgoing) == 0 else "handler")
        node_index[n] = {
            "lane": lane_for_path.get(n, "other"),
            "role": role,
            "incoming": incoming,
            "outgoing": outgoing,
            "policies": [],
            "envs": [i.get("key") for i in data_flow.get("inputs", []) if i.get("type") == "env"],
            "relatedData": [s.get("name") or s.get("path") for s in data_flow.get("stores", [])] + [e.get("name") for e in data_flow.get("externals", [])],
        }
    capability["nodeIndex"] = node_index

    # Apply comprehensive post-processing
    capability = ensure_capability_defaults(capability)
    capability = normalize_capability_paths(capability, repo_dir)
    capability = provide_trivial_fallbacks(capability)
    capability = add_camelcase_mirrors(capability)
    
    # Add normalization warnings
    if anchor_warnings:
        capability["warnings"] = capability.get("warnings", []) + anchor_warnings

    return cap_id, capability


def _derive_routes_from_files(files_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    files = files_payload.get("files", [])
    for f in files:
        path = f.get("path", "")
        hints = f.get("hints", {})
        
        # First, check if file has explicit routes array (from parser)
        file_routes = f.get("routes", [])
        if file_routes:
            for route_obj in file_routes:
                route_path = route_obj.get("path", "")
                method = route_obj.get("method", "GET")
                if route_path:
                    kind = "api" if hints.get("isAPI") else "ui"
                    routes.append({
                        "path": path, 
                        "kind": kind, 
                        "route": route_path,
                        "method": method
                    })
            continue
        
        # Prefer explicit hints when present (only if route is specified)
        if hints.get("isRoute") and hints.get("route"):
            routes.append({"path": path, "kind": "ui", "route": hints.get("route")})
            continue
        if hints.get("isAPI") and hints.get("route"):
            routes.append({"path": path, "kind": "api", "route": hints.get("route")})
            continue

        # Next.js app router: src/app/**/page.tsx => route
        if "/src/app/" in path and path.endswith("/page.tsx"):
            seg = path.split("/src/app/")[-1][:-len("/page.tsx")]
            route = "/" + seg.strip("/")
            if route == "/" or route == "//":
                route = "/"
            routes.append({"path": path, "kind": "ui", "route": route})
            continue

        # Next.js API route: src/app/api/**/route.ts
        if "/src/app/api/" in path and path.endswith("/route.ts"):
            seg = path.split("/src/app/api/")[-1][:-len("/route.ts")]
            route = "/api/" + seg.strip("/")
            routes.append({"path": path, "kind": "api", "route": route})
            continue

        # Generic routes folder heuristics
        if "/routes/" in path and (path.endswith(".ts") or path.endswith(".js")):
            # Try to infer route from filename
            name = Path(path).stem
            route = "/" + name.replace("index", "").strip("/")
            routes.append({"path": path, "kind": "api", "route": route or "/"})
            continue

        # Webhooks heuristic
        if "webhook" in path or "webhooks" in path:
            name = Path(path).stem
            route = "/webhooks/" + name
            routes.append({"path": path, "kind": "webhook", "route": route})
            continue

    # De-duplicate by (path, route)
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in routes:
        k = (r.get("path"), r.get("route"))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


async def build_all_capabilities(files_payload: Dict[str, Any], graph_payload: Dict[str, Any], repo_dir: Path) -> Dict[str, Any]:
    """Build all capabilities from files and graph payloads."""

    # Derive routes from files.hints
    routes = _derive_routes_from_files(files_payload)

    groups = _group_routes(routes)
    
    # Apply budget limit
    budget = settings.LLM_CAP_BUDGET
    if len(groups) > budget:
        groups = groups[:budget]
        logger.warning(f"Capability count ({len(groups)}) exceeds budget ({budget}), processing first {budget}")

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(settings.LLM_CONCURRENCY)
    
    # Track capability budget
    cap_budget = settings.LLM_CAP_BUDGET
    budget_warnings = []

    index: List[Dict[str, Any]] = []
    by_id: Dict[str, Any] = {}
    for i, g in enumerate(groups):
        if i >= cap_budget:
            budget_warnings.append(f"Capability budget ({cap_budget}) exceeded, stopping at {i} capabilities")
            break
            
        cap_id, cap = await _build_capability(files_payload, graph_payload, repo_dir, g, semaphore)
        by_id[cap_id] = cap
        index.append({
            "id": cap_id, 
            "name": cap.get("name", ""),
            "purpose": cap.get("purpose", ""),
            "entryPoints": cap.get("entryPoints", []),
            "keyFiles": cap.get("keyFiles", []),
            "dataIn": cap.get("dataIn", []),
            "dataOut": cap.get("dataOut", []),
            "sources": cap.get("sources", []),
            "sinks": cap.get("sinks", []),
            "anchors": cap.get("anchors", []), 
            "lanes": {k: len(v) for k, v in cap.get("swimlanes", {}).items()},
            "status": cap.get("status", "healthy")
        })

    # Persist - ensure stable shape for index
    stable_index = []
    for item in index:
        stable_item = {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "purpose": item.get("purpose", ""),
            "entryPoints": item.get("entryPoints", []),
            "keyFiles": item.get("keyFiles", []),
            "dataIn": item.get("dataIn", []),
            "dataOut": item.get("dataOut", []),
            "sources": item.get("sources", []),
            "sinks": item.get("sinks", []),
            "anchors": item.get("anchors", []),
            "lanes": item.get("lanes", {"web": 0, "api": 0, "workers": 0, "other": 0}),
        }
        stable_index.append(stable_item)
    
    # Write capabilities index atomically
    index_path = repo_dir / "capabilities" / "index.json"
    index_path.parent.mkdir(exist_ok=True)
    index_data = {"index": stable_index}
    write_json_atomic(index_path, index_data)
    
    # Record metrics for index creation
    metrics = get_metrics_collector()
    index_bytes = len(json.dumps(index_data, indent=2).encode('utf-8'))
    metrics.record_artifact_created("capabilities_index", index_bytes)
    
    # Write individual capability files with comprehensive defaults
    files_idx = {f["path"]: f for f in files_payload.get("files", [])}
    for cid, cap in by_id.items():
        # Validate references before persisting
        cap = _validate_references(cap, files_idx)
        _write_capability_with_defaults(repo_dir, cap, cid)
        
        # Record metrics for capability creation
        cap_bytes = len(json.dumps(cap, indent=2).encode('utf-8'))
        metrics.record_artifact_created("capability", cap_bytes)

    result = {
        "repoId": files_payload.get("repoId", "unknown"),
        "generatedAt": _now(),
        "capabilities": stable_index
    }
    
    # Add budget warnings if any
    if budget_warnings:
        result["warnings"] = budget_warnings
    
    return result


def list_capabilities_index(base: Path) -> Dict[str, Any]:
    p = _repo_paths(base)["index"]
    if not p.exists():
        raise FileNotFoundError("capabilities index not found")
    return _read_json(p)


def read_capability_by_id(base: Path, cap_id: str) -> Dict[str, Any]:
    p = _repo_paths(base)["caps_dir"] / cap_id / "capability.json"
    if not p.exists():
        raise FileNotFoundError("capability not found")
    return _read_json(p)


