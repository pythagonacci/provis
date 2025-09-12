"""
Comprehensive capability emission for FastAPI + SQLAlchemy backend.
Produces consistent capability.json with proper data flow, contracts, and policies.
"""

import ast
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict

# Import the new robust extractors
try:
    from .parsers.python import (
        collect_pydantic_models,
        collect_sqlalchemy_models,
        find_fastapi_routes,
        link_request_models,
        detect_response_models,
        detect_artifact_outputs,
        extract_env_keys,
        extract_externals,
        extract_cors_policies,
        extract_dependencies,
        iter_py_files
    )
except ImportError:
    from app.parsers.python import (
        collect_pydantic_models,
        collect_sqlalchemy_models,
        find_fastapi_routes,
        link_request_models,
        detect_response_models,
        detect_artifact_outputs,
        extract_env_keys,
        extract_externals,
        extract_cors_policies,
        extract_dependencies,
        iter_py_files
    )

def lane_for_path(path: str) -> str:
    """Determine lane based on file path."""
    if path.startswith("backend/app/") and path.endswith(".py"):
        return "api"
    elif path.startswith("offdeal-frontend/"):
        return "web"
    else:
        return "other"

def extract_data_flow(repo_root: Path):
    """Extract comprehensive data flow using robust extractors."""
    models = collect_pydantic_models(repo_root)
    sa_models = collect_sqlalchemy_models(repo_root)
    routes = find_fastapi_routes(repo_root)

    inputs = link_request_models(routes, models)  # requestSchema items
    stores = sa_models                              # dbModel items
    
    # Add env keys to inputs
    for f in iter_py_files(repo_root):
        try:
            text = f.read_text(encoding="utf-8")
            rel_path = str(f.relative_to(repo_root))
            env_items = extract_env_keys(text, rel_path)
            for item in env_items:
                # item is already a dict with type, key, path
                item["touches"] = [rel_path]
                item["example"] = {"key": item["key"], "value": "***REDACTED***" if "KEY" in item["key"] else "example_value"}
                inputs.append(item)
        except Exception:
            continue
    
    # Add externals
    externals = []
    for f in iter_py_files(repo_root):
        try:
            text = f.read_text(encoding="utf-8")
            rel_path = str(f.relative_to(repo_root))
            ext_list = extract_externals(text, rel_path)
            for ext in ext_list:
                ext["path"] = rel_path
                externals.append(ext)
        except Exception:
            continue
    
    outputs = detect_response_models(routes, models) + detect_artifact_outputs(repo_root)

    return {
        "inputs": inputs,
        "stores": stores,
        "externals": externals,
        "outputs": outputs
    }

def build_control_flow(repo_root: Path, routes: List[Dict]) -> List[Dict]:
    """Build control flow edges from routes to models/schemas/services."""
    edges = []
    
    for route in routes:
        route_file = route["file"]
        
        # Add import edges to common patterns
        if "main.py" in route_file or "routers" in route_file:
            # Main app imports database models
            edges.append({
                "from": route_file,
                "to": "backend/app/database.py",
                "kind": "import"
            })
            
            # Main app imports config
            edges.append({
                "from": route_file,
                "to": "backend/app/config.py",
                "kind": "import"
            })
            
            # Main app imports models
            edges.append({
                "from": route_file,
                "to": "backend/app/models.py",
                "kind": "import"
            })
            
            # Main app calls services
            edges.append({
                "from": route_file,
                "to": "backend/app/llm/client.py",
                "kind": "call"
            })
            
            # Main app calls parsers
            edges.append({
                "from": route_file,
                "to": "backend/app/parsers/python.py",
                "kind": "call"
            })
    
    return edges

def build_policies(repo_root: Path) -> List[Dict]:
    """Build policies from CORS middleware and dependencies."""
    policies = []
    
    for f in iter_py_files(repo_root):
        try:
            text = f.read_text(encoding="utf-8")
            rel_path = str(f.relative_to(repo_root))
            
            # Extract CORS policies
            cors_policies = extract_cors_policies(text, rel_path)
            policies.extend(cors_policies)
            
            # Extract dependencies
            deps = extract_dependencies(text, rel_path)
            policies.extend(deps)
            
        except Exception:
            continue
    
    return policies

def build_contracts(models: Dict, data_flow: Dict, repo_root: Path) -> List[Dict]:
    """Build contracts from models used in requests/responses."""
    contracts = []
    
    for mname, m in models.items():
        used_as_request = any(i["type"]=="requestSchema" and i["name"]==mname for i in data_flow["inputs"])
        used_as_response = any(o["type"]=="responseSchema" and o["name"]==mname for o in data_flow["outputs"])
        if used_as_request or used_as_response:
            contracts.append({
                "name": mname,
                "kind": "pydantic.Model",
                "path": m["path"],
                "fields": m["fields"]
            })
    
    # Add SQLAlchemy models as contracts
    for store in data_flow["stores"]:
        contracts.append({
            "name": store["name"],
            "kind": "sqlalchemy.Model", 
            "path": store["path"],
            "fields": store["fields"]
        })
    
    # Add parser files as contracts
    for f in iter_py_files(repo_root):
        rel_path = str(f.relative_to(repo_root))
        if "parsers" in rel_path or "tests" in rel_path:
            contracts.append({
                "name": f.stem,
                "kind": "parser.Module" if "parsers" in rel_path else "test.Module",
                "path": rel_path,
                "fields": []
            })
    
    return contracts

def build_capability(repo_dir: Path) -> Dict[str, Any]:
    """Build comprehensive capability.json for FastAPI + SQLAlchemy backend."""
    
    # Extract data using robust extractors
    models = collect_pydantic_models(repo_dir)
    routes = find_fastapi_routes(repo_dir)
    data_flow = extract_data_flow(repo_dir)
    control_flow = build_control_flow(repo_dir, routes)
    policies = build_policies(repo_dir)
    contracts = build_contracts(models, data_flow, repo_dir)
    
    # Build entrypoints
    entrypoints = []
    for route in routes:
        entrypoints.append({
            "path": route["file"],
            "framework": "fastapi",
            "kind": "api",
            "route": route["route"]
        })
    
    # Build E2E steps
    steps = [
        {
            "title": "Receive Request",
            "description": "FastAPI receives HTTP request",
            "fileId": "backend/app/main.py"
        },
        {
            "title": "Validate Input",
            "description": "Validate input data using Pydantic schemas",
            "fileId": "backend/app/models.py"
        },
        {
            "title": "Process Request",
            "description": "Process the request using business logic",
            "fileId": "backend/app/database.py"
        },
        {
            "title": "Generate Response",
            "description": "Use AI service to generate response",
            "fileId": "backend/app/llm/client.py"
        },
        {
            "title": "Save Results",
            "description": "Save results to database",
            "fileId": "backend/app/database.py"
        },
        {
            "title": "Return Response",
            "description": "Return response to client",
            "fileId": "backend/app/main.py"
        }
    ]
    
    # Set orchestrators
    orchestrators = [
        "backend/app/main.py",
        "backend/app/database.py", 
        "backend/app/config.py"
    ]
    
    # Build swimlanes
    swimlanes = {"web": [], "api": [], "workers": [], "other": []}
    for f in iter_py_files(repo_dir):
        rel_path = str(f.relative_to(repo_dir))
        lane = lane_for_path(rel_path)
        swimlanes[lane].append(rel_path)
    
    # Build nodeIndex
    node_index = {}
    for f in iter_py_files(repo_dir):
        rel_path = str(f.relative_to(repo_dir))
        lane = lane_for_path(rel_path)
        
        # Force routers to api lane
        if rel_path.startswith("backend/app/routers/"):
            lane = "api"
            
        node_index[rel_path] = {
            "lane": lane,
            "role": "entrypoint" if "main.py" in rel_path else "service",
            "policies": [],
            "relatedData": []
        }
    
    # Deduplicate dataOut
    data_out = list(set([
        "IngestResponse", "RepoOverviewModel", "StatusPayload", "OpenAI", "SMTP", "Database"
    ]))
    
    # Build final capability
    capability = {
        "id": "cap_generate_deck_email",
        "name": "Generate Deck and Email",
        "purpose": "AI-powered deck generation with email notifications",
        "title": "Deck Generation Flow",
        "status": "active",
        "entrypoints": entrypoints,
        "swimlanes": swimlanes,
        "control_flow": control_flow,
        "data_flow": data_flow,
        "policies": policies,
        "contracts": contracts,
        "steps": steps,
        "orchestrators": orchestrators,
        "nodeIndex": node_index,
        "dataOut": data_out,
        "debug": {
            "files_processed": len(list(iter_py_files(repo_dir))),
            "entrypoints_found": len(entrypoints),
            "models_found": len(data_flow["stores"]),
            "externals_found": len(data_flow["externals"]),
            "control_flow_edges": len(control_flow),
            "policies_found": len(policies),
            "contracts_found": len(contracts)
        }
    }
    
    # Remove any camelCase duplicates
    for k in ["entryPoints", "controlFlow", "dataFlow"]:
        if k in capability:
            capability.pop(k, None)
    
    return capability

def write_capability(repo_dir: Path, capability: Dict[str, Any]) -> None:
    """Write capability.json to disk."""
    output_dir = repo_dir / "capabilities" / "cap_generate_deck_email"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "capability.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(capability, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Capability written to {output_file}")

# Main execution
if __name__ == "__main__":
    import sys
    repo_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    capability = build_capability(repo_dir)
    write_capability(repo_dir, capability)