# tests/test_capability_spec.py
import json, os
from pathlib import Path
from typing import Optional, List, Tuple

CAP_ENV = "PROVIS_CAP_PATH"
CANDIDATE_NAMES = [
    "capability.json",
    "capabilities.json",
    "capability_output.json",
    "capability.final.json",
]
SEARCH_ROOT_ENV = "PROVIS_CAP_DIR"  # optional override for the search root

def _try_load(p: Path):
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _select_best(paths: List[Path]) -> Optional[Path]:
    # prefer shortest path depth, then most recent mtime
    if not paths:
        return None
    paths = sorted(paths, key=lambda p: (len(p.parts), -p.stat().st_mtime))
    return paths[0]

def load_cap() -> dict:
    """
    Resolution order:
    1) PROVIS_CAP_PATH (exact file path)
    2) ./capability.json (in repo root or tests parent)
    3) common locations under current working dir and tests/ parent
    4) recursive glob for *capab*.json under the chosen search root
    """
    # 1) explicit
    env_path = os.environ.get(CAP_ENV)
    if env_path:
        p = Path(env_path).expanduser().resolve()
        assert p.exists(), f"Capability file not found at {p} (from {CAP_ENV})"
        cap = _try_load(p)
        assert cap is not None, f"Failed to parse JSON at {p}"
        return cap

    # choose a search root
    search_root = os.environ.get(SEARCH_ROOT_ENV)
    if search_root:
        root = Path(search_root).expanduser().resolve()
    else:
        root = Path.cwd()

    # 2) direct names in a few roots
    roots = [
        root,
        Path(__file__).resolve().parent.parent,  # repo root (if running from tests/)
        root / "backend",
        root / "capabilities",
        root / "out",
    ]
    for r in roots:
        for name in CANDIDATE_NAMES:
            p = (r / name)
            if p.exists():
                cap = _try_load(p)
                if cap is not None:
                    return cap

    # 3) glob search
    candidates = []
    for pat in ["**/capab*.json", "**/*capability*.json", "**/capabilities*.json"]:
        candidates.extend(root.glob(pat))
    if candidates:
        chosen = _select_best(candidates)
        if chosen:
            cap = _try_load(chosen)
            if cap is not None:
                return cap

    assert False, (
        "Capability file not found. Fix by either:\n"
        f"  - Set {CAP_ENV}=/absolute/path/to/capability.json\n"
        f"  - Or set {SEARCH_ROOT_ENV}=/repo/root and keep capability.json somewhere under it\n"
        "  - Or place capability.json at repo root\n"
        "  - Or pass one of the common names in ./, ./backend, ./capabilities, ./out"
    )

def _paths_from_entrypoints(cap):
    eps = cap.get("entrypoints", [])
    return [ep.get("path") for ep in eps if isinstance(ep, dict) and ep.get("path")]

def _edge_key(e):
    return (e.get("from"), e.get("to"), e.get("kind"))

# ---------------- Basic shape ----------------

def test_snake_case_only():
    cap = load_cap()
    assert "data_flow" in cap, "data_flow must exist (snake_case)"
    assert "dataFlow" not in cap, "dataFlow (camelCase) must NOT be present"

def test_entrypoints_structured_and_present():
    cap = load_cap()
    eps = cap.get("entrypoints", [])
    assert isinstance(eps, list) and len(eps) > 0, "entrypoints must be a non-empty list"
    for ep in eps:
        assert isinstance(ep, dict), "each entrypoint must be an object"
        for k in ("path", "framework", "kind", "route"):
            assert k in ep, f"entrypoint missing key: {k}"
        assert ep["framework"] == "fastapi", f"entrypoint.framework should be 'fastapi', got {ep['framework']}"
        assert ep["kind"] == "api", f"entrypoint.kind should be 'api', got {ep['kind']}"

def test_control_flow_present_and_well_formed():
    cap = load_cap()
    edges = cap.get("control_flow", [])
    assert isinstance(edges, list) and len(edges) > 0, "control_flow must be a non-empty list"
    for e in edges:
        assert isinstance(e, dict), "each control_flow edge must be an object"
        for k in ("from", "to", "kind"):
            assert k in e, f"control_flow edge missing key: {k}"
        assert e["from"] and e["to"], "control_flow edge must have non-empty from/to"

def test_orchestrators_include_core():
    cap = load_cap()
    orch = set(cap.get("orchestrators", []))
    required = {
        "backend/app/routers/deck.py",
        "backend/app/routers/email.py",
        "backend/app/main.py",
    }
    missing = required - orch
    assert not missing, f"orchestrators must include {required}; missing={missing}"

def test_no_suspect_rank_anywhere():
    cap = load_cap()
    assert "suspectRank" not in cap, "suspectRank must not be present"

# ---------------- Lanes / swimlanes ----------------

def test_swimlanes_and_lanes_consistency():
    cap = load_cap()
    swim = cap.get("swimlanes", {})
    for key in ("web", "api", "workers", "other"):
        assert key in swim, f"swimlanes must include '{key}'"

    api_lane = set(swim.get("api", []))
    web_lane = set(swim.get("web", []))

    # All FastAPI routers from entrypoints must be in api lane (not web)
    ep_paths = _paths_from_entrypoints(cap)
    for p in ep_paths:
        assert p in api_lane, f"Router {p} should be in swimlanes.api"
        assert p not in web_lane, f"Router {p} must not be in swimlanes.web"

# ---------------- Data flow ----------------

def test_data_flow_sections_present_and_populated():
    cap = load_cap()
    df = cap.get("data_flow", {})
    for key in ("inputs", "stores", "externals"):
        assert key in df, f"data_flow must include '{key}'"
        assert isinstance(df[key], list), f"data_flow.{key} must be a list"
    assert len(df["inputs"]) > 0, "data_flow.inputs must be non-empty (env + requestSchema)"
    assert len(df["stores"]) > 0, "data_flow.stores must be non-empty (dbModel entries)"
    assert len(df["externals"]) > 0, "data_flow.externals must be non-empty (OpenAI/SMTP/etc.)"

def test_inputs_have_env_and_request_schema():
    cap = load_cap()
    df = cap["data_flow"]
    kinds = [i.get("type") for i in df["inputs"] if isinstance(i, dict)]
    assert any(k == "env" for k in kinds), "data_flow.inputs must include at least one 'env' item (e.g., OPENAI_API_KEY)"
    assert any(k == "requestSchema" for k in kinds), "data_flow.inputs must include at least one 'requestSchema' item"

def test_outputs_present_and_examples_optional():
    cap = load_cap()
    df = cap.get("data_flow", {})
    outs = df.get("outputs", [])
    assert isinstance(outs, list) and len(outs) > 0, "data_flow.outputs must be a non-empty list (response schemas)"
    for o in outs:
        assert "type" in o and o["type"] in ("responseSchema", "event", "artifact", "email"), "outputs must label type as responseSchema, event, artifact, or email"
        assert "name" in o or "path" in o, "each output requires a 'name' or 'path'"

def test_stores_have_fields_and_types():
    cap = load_cap()
    stores = cap["data_flow"]["stores"]
    for s in stores:
        assert s.get("type") == "dbModel", "stores entries must be type 'dbModel'"
        assert "path" in s and s["path"].endswith(".py"), "dbModel path must be a .py file"
        fields = s.get("fields", [])
        assert isinstance(fields, list) and len(fields) > 0, "dbModel must include 'fields'"
        for f in fields:
            assert "name" in f and "type" in f, "each field must include 'name' and 'type'"
            assert "nullable" in f, "each field should include 'nullable'"
            assert "primary_key" in f, "each field should include 'primary_key'"

def test_externals_present_and_named_clients():
    cap = load_cap()
    exts = cap["data_flow"]["externals"]
    assert len(exts) > 0, "externals must include at least one API (e.g., OpenAI, SMTP)"
    names = [e.get("name","").lower() for e in exts if isinstance(e, dict)]
    assert any("openai" in n for n in names) or any("sendgrid" in n or "smtp" in n for n in names), \
        "externals should include OpenAI and/or an email provider (SendGrid/SMTP)"
    for e in exts:
        assert "path" in e, "externals should include a 'path' file path that calls the API"

def test_contracts_cover_request_and_response_schemas():
    cap = load_cap()
    contracts = cap.get("contracts", [])
    assert isinstance(contracts, list) and len(contracts) > 0, "contracts must be non-empty"
    df = cap["data_flow"]
    req_paths = {i.get("path") for i in df["inputs"] if i.get("type") == "requestSchema" and i.get("path")}
    out_paths = {o.get("path") for o in df.get("outputs", []) if o.get("path")}
    all_needed = {p for p in req_paths | out_paths if p}
    covered = set()
    for c in contracts:
        p = c.get("path") or ""
        if p:
            covered.add(p)
    missing = all_needed - covered
    assert not missing, f"contracts must include entries for all request/response schema paths; missing={missing}"

def test_policies_present_and_typed():
    cap = load_cap()
    policies = cap.get("policies", [])
    assert isinstance(policies, list) and len(policies) > 0, "policies must be non-empty"
    allowed_types = {"middleware", "dependency", "schemaGuard"}
    assert any(p.get("type") in allowed_types for p in policies), \
        "at least one policy must have a recognized type (middleware/dependency/schemaGuard)"
    assert any("CORS" in (p.get("name","") + p.get("type","")) or "CORSMiddleware" in (p.get("name","")) for p in policies), \
        "policies should include CORSMiddleware from main.py"
    assert any("appliedAt" in p for p in policies), "at least one policy should have 'appliedAt' with a file:line"

# ---------------- Steps / flow narrative ----------------

def test_steps_are_single_sequence_and_deduped():
    cap = load_cap()
    steps = cap.get("steps", [])
    assert isinstance(steps, list) and 6 <= len(steps) <= 10, "steps must be a 6–10 item list"
    titles = [s.get("title") for s in steps]
    assert all(titles), "each step must have a title"
    assert len(set(titles)) == len(titles), f"steps must be deduped (duplicate titles: {titles})"
    anchors = {"Receive Request", "Fetch Prospect Data", "Generate Deck Content", "Return Success"}
    assert anchors.issubset(set(titles)), f"steps should contain canonical anchors {anchors}"

# ---------------- DataOut ----------------

def test_dataout_unique_if_present():
    cap = load_cap()
    dataout = cap.get("dataOut", [])
    assert isinstance(dataout, list), "dataOut must be a list"
    assert len(dataout) > 0, "dataOut must be present and non-empty"
    lowered = [str(x).lower() for x in dataout]
    assert len(set(lowered)) == len(lowered), f"dataOut contains duplicates: {dataout}"

# ---------------- Graph integrity ----------------

def test_store_touches_match_edges_when_present():
    cap = load_cap()
    edges = { _edge_key(e) for e in cap.get("control_flow", []) }
    for store in cap.get("data_flow", {}).get("stores", []):
        touches = store.get("touches", [])
        for t in touches:
            if isinstance(t, dict):
                key = (t.get("from"), t.get("to"), t.get("kind"))
                assert key in edges, f"store.touch {key} not found in control_flow edges"
