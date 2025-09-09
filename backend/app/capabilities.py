from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from .llm.client import LLMClient


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
        # Mark worker interactions
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
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- Route grouping ----
def _normalize_route(route: str) -> str:
    if not route:
        return "/"
    r = route.strip()
    if not r.startswith("/"):
        r = "/" + r
    if len(r) > 1 and r.endswith("/"):
        r = r[:-1]
    return r


def _group_routes(routes: List[Dict[str, Any]]) -> List[List[Anchor]]:
    buckets: Dict[str, List[Anchor]] = {}
    for r in routes:
        key = _normalize_route(r.get("route", ""))
        a = Anchor(path=r.get("path", ""), kind=r.get("kind", "ui"), route=key)
        buckets.setdefault(key, []).append(a)
    return list(buckets.values())


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
async def _llm_expand(llm: LLMClient, anchors: List[Anchor], files: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
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
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Be precise, conservative, and avoid hallucinations. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"ANCHORS:\n{[a.__dict__ for a in anchors]}\n\nCONTEXT NODES (focused):\n{subset}\n\nRAW EDGES WITHIN CONTEXT (may be incomplete):\n{raw_edges}\n\nTASK:\nInfer the minimal end-to-end set of files for the capability serving route {route}. Assign lanes (web|api|workers|other) and propose edges (import|call|http|queue|webhook). Exclude shared infra. RETURN strict JSON per schema."},
    ]
    try:
        res = await llm.acomplete_json(messages, EXPANSION_SCHEMA)
    except Exception:
        res = {"nodes": [], "edges": []}

    # Fallback: if model returns empty, synthesize from context
    if not res.get("nodes"):
        nodes = [{"path": p, "lane": _infer_lane_from_path(p)} for p in context_paths[:60]]
        edges = raw_edges[:1000]
        return {"nodes": nodes, "edges": edges}
    return res


async def _llm_extract_data(llm: LLMClient, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Be precise, conservative. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"NODES:\n{nodes}\n\nTASK:\nIdentify inputs, stores, externals, contracts, policies across these nodes. Include concise 'why' citing which file suggests it. RETURN strict JSON per schema."},
    ]
    return await llm.acomplete_json(messages, DATA_SCHEMA)


async def _llm_summarize_file(llm: LLMClient, path: str, lane: Lane, neighbors_in: List[str], neighbors_out: List[str], symbols: Dict[str, Any]) -> str:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Return one or two concise sentences, present tense, no speculation."},
        {"role": "user", "content": f"FILE: {path}\nLANE: {lane}\nNEIGHBORS IN: {neighbors_in}\nNEIGHBORS OUT: {neighbors_out}\nSYMBOLS: {symbols}\nCONSTRAINTS: ≤2 sentences, present tense, no speculation, mention role. RETURN: plain text (≤200 chars)."},
    ]
    # Use JSON mode wrapper to keep caching uniform; wrap text
    schema = {"type": "object", "properties": {"t": {"type": "string"}}, "required": ["t"]}
    res = await llm.acomplete_json(messages, schema)
    return str(res.get("t", ""))[:400]


async def _llm_narrative(llm: LLMClient, name: str, anchors: List[str], lanes: Dict[Lane, List[str]], edges: List[Dict[str, Any]], data: Dict[str, Any]) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"CAPABILITY: {name}\nANCHORS: {anchors}\nLANES: {lanes}\nEDGES: {edges}\nDATA: {data}\n\nTASK:\nWrite 6–10 ordered steps (happy path). Add 2–3 edge/failure cases. RETURN as {{steps:[{{label, detail, scenario?}}]}}"},
    ]
    return await llm.acomplete_json(messages, NARRATIVE_SCHEMA)


async def _llm_touches(llm: LLMClient, data_item: str, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"DATA ITEM: {data_item}\nNODES: {nodes}\nEDGES: {edges}\n\nTASK:\nList files that likely READ vs WRITE (or enqueue/consume/call) this item within this capability only. For each, provide {{actorPath, action, via, reason}}. RETURN as TouchesOut."},
    ]
    return await llm.acomplete_json(messages, TOUCHES_SCHEMA)


async def _llm_suspects(llm: LLMClient, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"CONTEXT: {context}\n\nTASK:\nRank top 5 likely-problem files (0..1 score), with brief reason, prioritizing central writers and external callers on critical path. RETURN array of SuspectOut."},
    ]
    return await llm.acomplete_json(messages, SUSPECTS_SCHEMA)  # type: ignore


# ---- Core build ----
async def _build_capability(base: Path, anchors: List[Anchor]) -> Tuple[str, Dict[str, Any]]:
    files = _read_json(_repo_paths(base)["files"]) if _repo_paths(base)["files"].exists() else {"files": []}
    graph = _read_json(_repo_paths(base)["graph"]) if _repo_paths(base)["graph"].exists() else {"edges": []}

    llm = LLMClient(cache_dir=base / "cache_llm")
    expansion = await _llm_expand(llm, anchors, files, graph)

    # Validate graph integrity basics
    node_paths = {n.get("path") for n in expansion.get("nodes", [])}
    edges = [e for e in expansion.get("edges", []) if e.get("from") in node_paths and e.get("to") in node_paths]

    data = await _llm_extract_data(llm, expansion.get("nodes", []))

    # File summaries (per node)
    files_idx = {f["path"]: f for f in files.get("files", [])}
    summaries_file: Dict[str, str] = {}
    for n in expansion.get("nodes", []):
        p = n.get("path")
        neighbors_in = [e.get("from") for e in edges if e.get("to") == p]
        neighbors_out = [e.get("to") for e in edges if e.get("from") == p]
        text = await _llm_summarize_file(llm, p, n.get("lane", "other"), neighbors_in, neighbors_out, files_idx.get(p, {}).get("symbols", {}))
        summaries_file[p] = text

    # Folder rollups: simple heuristic grouping by top folder
    folder_rollup: Dict[str, str] = {}
    for p, s in summaries_file.items():
        parts = p.split("/")
        if len(parts) > 2:
            key = "/".join(parts[:2])
            if key not in folder_rollup:
                folder_rollup[key] = s

    # Narrative & lanes mapping
    lanes_map: Dict[Lane, List[str]] = _build_swimlanes(expansion.get("nodes", []))
    narrative = await _llm_narrative(
        llm,
        name=anchors[0].route if anchors else "Capability",
        anchors=[a.path for a in anchors],
        lanes=lanes_map,
        edges=edges,
        data=data,
    )

    # Touches
    touches: Dict[str, Any] = {}
    for st in data.get("stores", []):
        di = st.get("name") or st.get("path") or "store"
        touches[di] = await _llm_touches(llm, di, expansion.get("nodes", []), edges)
    for ex in data.get("externals", []):
        di = ex.get("name") or ex.get("path") or "external"
        touches[di] = await _llm_touches(llm, di, expansion.get("nodes", []), edges)

    # Build UI-aligned fields
    lane_for_path: Dict[str, str] = {}
    for lane, paths in lanes_map.items():
        for p in paths:
            lane_for_path[p] = lane
    control_flow = _enhance_control_flow(edges, lane_for_path)

    # Entrypoints enriched with framework
    entrypoints = [{"path": a.path, "framework": _infer_framework_from_path(a.path), "kind": a.kind} for a in anchors]

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

    data_flow = {
        "inputs": _embed_touches(data.get("inputs", [])),
        "stores": _embed_touches(data.get("stores", [])),
        "externals": _embed_touches(data.get("externals", [])),
    }

    # Policy typing
    policies_typed = [{**p, "type": _classify_policy_type(p)} for p in data.get("policies", [])]

    # Assemble
    cap_id = f"cap_{anchors[0].route.strip('/').replace('/', '_') or 'root'}"
    capability = {
        "id": cap_id,
        "name": anchors[0].route.strip("/") or "/",
        "title": anchors[0].route.strip("/") or "/",
        "status": _compute_status(),
        "anchors": [a.__dict__ for a in anchors],
        # Back-compat fields
        "lanes": {k: [{"path": p} for p in v] for k, v in lanes_map.items()},
        "flow": edges,
        "data": {k: v for k, v in data.items() if k in ("inputs", "stores", "externals")},
        # UI-aligned fields
        "entrypoints": entrypoints,
        "swimlanes": lanes_map,
        "control_flow": control_flow,
        "data_flow": data_flow,
        "policies": policies_typed,
        "contracts": data.get("contracts", []),
        "summaries": {"file": summaries_file, "folder": folder_rollup, "narrative": narrative.get("steps", [])},
    }

    return cap_id, capability


def _derive_routes_from_files(files_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    files = files_payload.get("files", [])
    for f in files:
        path = f.get("path", "")
        hints = f.get("hints", {})
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


async def build_all_capabilities(base: Path) -> Dict[str, Any]:
    paths = _repo_paths(base)
    files = _read_json(paths["files"]) if paths["files"].exists() else {"files": []}

    # routes.json optional; derive basic anchors from files.hints if missing
    routes: List[Dict[str, Any]] = []
    if paths["routes"].exists():
        routes = _read_json(paths["routes"])  # type: ignore
    if not routes:
        routes = _derive_routes_from_files(files)

    groups = _group_routes(routes)

    index: List[Dict[str, Any]] = []
    by_id: Dict[str, Any] = {}
    for g in groups:
        cap_id, cap = await _build_capability(base, g)
        by_id[cap_id] = cap
        index.append({"id": cap_id, "name": cap.get("name"), "anchors": cap.get("anchors"), "lanes": {k: len(v) for k, v in cap.get("lanes", {}).items()}})

    # Persist
    _write_json(paths["index"], {"index": index})
    for cid, cap in by_id.items():
        _write_json(paths["caps_dir"] / cid / "capability.json", cap)

    return {"index": index}


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


