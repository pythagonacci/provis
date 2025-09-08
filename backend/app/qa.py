from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .llm.client import LLMClient


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _tokenize(s: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_./-]+", (s or "").lower())


def _score_file(q_tokens: List[str], f: Dict[str, Any]) -> float:
    score = 0.0
    text_parts: List[str] = []
    text_parts.append(f.get("path", ""))
    summary = (f.get("summary", {}) or {}).get("blurb") or f.get("blurb") or ""
    text_parts.append(summary)
    symbols = f.get("symbols", {}) or {}
    for k in ("functions", "classes", "exports", "imports"):
        vals = symbols.get(k) or []
        if isinstance(vals, list):
            text_parts.extend([str(v) for v in vals])
    text = " \n ".join(text_parts).lower()
    for t in q_tokens:
        if t in text:
            score += 1.0
    # small boost for route/API hints
    hints = f.get("hints", {}) or {}
    if hints.get("isRoute") or hints.get("isAPI"):
        score += 0.3
    return score


def _filter_files_for_capability(files: List[Dict[str, Any]], cap: Dict[str, Any]) -> List[Dict[str, Any]]:
    node_paths = set()
    lanes = cap.get("lanes", {}) or {}
    for lane_list in lanes.values():
        for n in lane_list:
            p = n.get("path") if isinstance(n, dict) else None
            if p:
                node_paths.add(p)
    return [f for f in files if f.get("path") in node_paths]


async def answer_question(repo_dir: Path, question: str, capability_id: str | None = None) -> Dict[str, Any]:
    files_payload = _read_json(repo_dir / "files.json")
    graph_payload = _read_json(repo_dir / "graph.json") if (repo_dir / "graph.json").exists() else {"edges": []}

    # Optional capability scoping
    scoped_files = files_payload.get("files", [])
    cap_obj = None
    caps_index_path = repo_dir / "capabilities" / "index.json"
    if capability_id and caps_index_path.exists():
        cap_path = repo_dir / "capabilities" / capability_id / "capability.json"
        if cap_path.exists():
            cap_obj = _read_json(cap_path)
            scoped_files = _filter_files_for_capability(scoped_files, cap_obj)

    # Retrieve top-k files by simple lexical scoring over path/summary/symbols
    q_tokens = _tokenize(question)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for f in scoped_files:
        scored.append((_score_file(q_tokens, f), f))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for s, f in scored[:20] if s > 0] or [f for s, f in scored[:10]]

    # Build compact context to keep latency low
    ctx_files = []
    for f in top:
        ctx_files.append({
            "path": f.get("path"),
            "language": f.get("language"),
            "hints": f.get("hints", {}),
            "symbols": f.get("symbols", {}),
            "blurb": (f.get("summary", {}) or {}).get("blurb") or f.get("blurb"),
        })

    # Edge subset within selected files
    selected_paths = set([f.get("path") for f in ctx_files])
    edges = [
        {"from": e.get("from"), "to": (e.get("resolved") or e.get("to")), "kind": "import" if not e.get("external") else "call"}
        for e in graph_payload.get("edges", [])
        if e.get("from") in selected_paths and ((e.get("resolved") or e.get("to")) in selected_paths)
    ]

    # Prepare LLM
    llm = LLMClient(cache_dir=repo_dir / "cache_llm")
    system = (
        "You are Provis, an expert codebase assistant. Given a user question and a set of relevant files "
        "plus local dependency edges, answer precisely with concrete file paths and next steps. "
        "Never invent code; cite specific files. Return strict JSON matching the schema."
    )
    user = {
        "question": question,
        "capability": cap_obj.get("name") if cap_obj else None,
        "files": ctx_files,
        "edges": edges,
    }
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "why": {"type": "string"}},
                    "required": ["path", "why"],
                },
            },
            "next_edits": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "files"],
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]
    try:
        res = await llm.acomplete_json(messages, schema)
    except Exception as e:
        res = {"answer": "Unable to answer due to model error.", "files": [], "error": str(e)}

    # Ensure minimal shape
    if "files" not in res:
        res["files"] = []
    return res


