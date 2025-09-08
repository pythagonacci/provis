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
    # Minimal content: anchors + shallow file metadata + raw edges subset
    files_idx = {f["path"]: f for f in files.get("files", [])}
    subset = [{"path": p, "lang": files_idx.get(p, {}).get("language"), "frameworkHints": files_idx.get(p, {}).get("hints", {}), "size": files_idx.get(p, {}).get("size"), "symbols": files_idx.get(p, {}).get("symbols", {})} for p in files_idx.keys()]
    raw_edges = [{"from": e.get("from"), "to": e.get("resolved") or e.get("to"), "kind": "import" if not e.get("external") else "call"} for e in graph.get("edges", []) if e.get("from") and (e.get("resolved") or e.get("to"))]
    route = anchors[0].route if anchors else "/"
    messages = [
        {"role": "system", "content": "You are a senior staff engineer documenting a codebase. Be precise, conservative, and avoid hallucinations. Always return strict JSON that matches the provided schema."},
        {"role": "user", "content": f"ANCHORS:\n{[a.__dict__ for a in anchors]}\n\nFILE METADATA (subset):\n{subset[:200]}\n\nRAW EDGES (may be incomplete):\n{raw_edges[:1000]}\n\nTASK:\nInfer the minimal end-to-end set of files for the capability serving route {route}. Assign lanes and propose edges. Exclude shared infra. RETURN strict JSON per schema."},
    ]
    return await llm.acomplete_json(messages, EXPANSION_SCHEMA)


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

    # Narrative
    lanes_map: Dict[Lane, List[str]] = {"web": [], "api": [], "workers": [], "other": []}
    for n in expansion.get("nodes", []):
        lanes_map.setdefault(n.get("lane", "other"), []).append(n.get("path"))
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

    # Suspects
    suspects = await _llm_suspects(llm, {"nodes": expansion.get("nodes", []), "edges": edges, "summaries": summaries_file, "touches": touches})

    # Assemble
    cap_id = f"cap_{anchors[0].route.strip('/').replace('/', '_') or 'root'}"
    capability = {
        "id": cap_id,
        "name": anchors[0].route.strip("/") or "/",
        "anchors": [a.__dict__ for a in anchors],
        "lanes": {k: [{"path": p} for p in v] for k, v in lanes_map.items()},
        "flow": edges,
        "data": {k: v for k, v in data.items() if k in ("inputs", "stores", "externals")},
        "policies": data.get("policies", []),
        "contracts": data.get("contracts", []),
        "summaries": {"file": summaries_file, "folder": folder_rollup, "narrative": narrative.get("steps", [])},
        "suspects": suspects,
    }

    return cap_id, capability


def _derive_routes_from_files(files_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    files = files_payload.get("files", [])
    for f in files:
        path = f.get("path", "")
        hints = f.get("hints", {})
        # Prefer explicit hints when present
        if hints.get("isRoute"):
            routes.append({"path": path, "kind": "ui", "route": hints.get("route") or "/"})
            continue
        if hints.get("isAPI"):
            routes.append({"path": path, "kind": "api", "route": hints.get("route") or "/api"})
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


