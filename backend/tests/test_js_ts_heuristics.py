"""
Unit tests for JS/TS heuristics in the Provis backend.
Tests framework detection, component detection, and import resolution.
"""

import pytest
import tempfile
import json
from pathlib import Path
from app.parsers.base import discover_files, parse_files, build_files_payload, build_graph


@pytest.fixture
def nextjs_fixture():
    """Create a minimal Next.js fixture for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot_dir = Path(tmpdir) / "snapshot"
        snapshot_dir.mkdir()
        
        # Create package.json with Next.js dependencies
        package_json = {
            "dependencies": {
                "next": "^14.0.0",
                "react": "^18.0.0",
                "react-dom": "^18.0.0"
            }
        }
        (snapshot_dir / "package.json").write_text(json.dumps(package_json))
        
        # Create src/app structure
        app_dir = snapshot_dir / "src" / "app"
        app_dir.mkdir(parents=True)
        
        # Create page.tsx (should be isRoute: true)
        page_content = '''import Image from "next/image";
import Hero from "@/components/Hero";
import Button from "@/components/Button";

export default function Home() {
  return (
    <div>
      <Hero title="Welcome!" />
      <Button>Click me</Button>
    </div>
  );
}'''
        (app_dir / "page.tsx").write_text(page_content)
        
        # Create layout.tsx (should be isRoute: true)
        layout_content = '''import { Inter } from 'next/font/google';
import './globals.css';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}'''
        (app_dir / "layout.tsx").write_text(layout_content)
        
        # Create components directory
        components_dir = snapshot_dir / "src" / "components"
        components_dir.mkdir(parents=True)
        
        # Create Hero.tsx (should be isReactComponent: true)
        hero_content = '''import React from 'react';

interface HeroProps {
  title: string;
}

export default function Hero({ title }: HeroProps) {
  return <h1>{title}</h1>;
}'''
        (components_dir / "Hero.tsx").write_text(hero_content)
        
        # Create Button.tsx (should be isReactComponent: true)
        button_content = '''import React from 'react';

interface ButtonProps {
  children: React.ReactNode;
}

const Button = ({ children }: ButtonProps) => {
  return <button>{children}</button>;
};

export default Button;'''
        (components_dir / "Button.tsx").write_text(button_content)
        
        # Create globals.css
        (app_dir / "globals.css").write_text("body { margin: 0; }")
        
        yield snapshot_dir


def test_nextjs_framework_detection(nextjs_fixture):
    """Test that Next.js framework is correctly detected."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    # Check that TSX files have framework: "nextjs"
    tsx_files = [f for f in files_list if f["ext"] in [".tsx", ".jsx"]]
    assert len(tsx_files) > 0, "Should have TSX files"
    
    for file in tsx_files:
        assert file["hints"]["framework"] == "nextjs", f"File {file['path']} should have framework: nextjs"


def test_route_detection(nextjs_fixture):
    """Test that page.tsx and layout.tsx are marked as routes."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    # Find page.tsx and layout.tsx
    page_file = next((f for f in files_list if f["path"].endswith("page.tsx")), None)
    layout_file = next((f for f in files_list if f["path"].endswith("layout.tsx")), None)
    
    assert page_file is not None, "Should have page.tsx"
    assert layout_file is not None, "Should have layout.tsx"
    
    assert page_file["hints"]["isRoute"] is True, "page.tsx should be marked as route"
    assert layout_file["hints"]["isRoute"] is True, "layout.tsx should be marked as route"


def test_react_component_detection(nextjs_fixture):
    """Test that component files are marked as React components."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    # Find component files
    hero_file = next((f for f in files_list if f["path"].endswith("Hero.tsx")), None)
    button_file = next((f for f in files_list if f["path"].endswith("Button.tsx")), None)
    
    assert hero_file is not None, "Should have Hero.tsx"
    assert button_file is not None, "Should have Button.tsx"
    
    assert hero_file["hints"]["isReactComponent"] is True, "Hero.tsx should be marked as React component"
    assert button_file["hints"]["isReactComponent"] is True, "Button.tsx should be marked as React component"


def test_alias_resolution(nextjs_fixture):
    """Test that @/ aliases resolve to src/ paths."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    # Build graph to test import resolution
    files_payload = build_files_payload("test_repo", files_list, warnings)
    graph_payload = build_graph(files_payload)
    
    # Find edges from page.tsx to components
    page_edges = [e for e in graph_payload["edges"] if e["from"].endswith("page.tsx")]
    
    # Should have edges to Hero and Button components
    hero_edge = next((e for e in page_edges if "Hero" in e["to"]), None)
    button_edge = next((e for e in page_edges if "Button" in e["to"]), None)
    
    assert hero_edge is not None, "Should have edge to Hero component"
    assert button_edge is not None, "Should have edge to Button component"
    
    # These should be internal (not external) and resolved
    assert hero_edge["external"] is False, "Hero import should be internal"
    assert button_edge["external"] is False, "Button import should be internal"
    
    assert "resolved" in hero_edge, "Hero import should be resolved"
    assert "resolved" in button_edge, "Button import should be resolved"
    
    # Resolved paths should point to actual files
    assert hero_edge["resolved"].endswith("Hero.tsx"), "Hero should resolve to Hero.tsx"
    assert button_edge["resolved"].endswith("Button.tsx"), "Button should resolve to Button.tsx"


def test_node_degrees(nextjs_fixture):
    """Test that node degrees are calculated correctly."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    files_payload = build_files_payload("test_repo", files_list, warnings)
    graph_payload = build_graph(files_payload)
    
    # Find nodes
    page_node = next((n for n in graph_payload["nodes"] if n["id"].endswith("page.tsx")), None)
    hero_node = next((n for n in graph_payload["nodes"] if n["id"].endswith("Hero.tsx")), None)
    button_node = next((n for n in graph_payload["nodes"] if n["id"].endswith("Button.tsx")), None)
    
    assert page_node is not None, "Should have page.tsx node"
    assert hero_node is not None, "Should have Hero.tsx node"
    assert button_node is not None, "Should have Button.tsx node"
    
    # page.tsx should have outDegree >= 2 (imports Hero and Button)
    assert page_node["outDegree"] >= 2, f"page.tsx should have outDegree >= 2, got {page_node['outDegree']}"
    
    # Hero and Button should have inDegree >= 1 (imported by page.tsx)
    assert hero_node["inDegree"] >= 1, f"Hero.tsx should have inDegree >= 1, got {hero_node['inDegree']}"
    assert button_node["inDegree"] >= 1, f"Button.tsx should have inDegree >= 1, got {button_node['inDegree']}"


def test_no_unresolved_warnings(nextjs_fixture):
    """Test that there are no unresolved local import warnings for valid imports."""
    discovered = discover_files(nextjs_fixture)
    files_list, warnings = parse_files(nextjs_fixture, discovered)
    
    files_payload = build_files_payload("test_repo", files_list, warnings)
    graph_payload = build_graph(files_payload)
    
    # Should have no warnings for valid Next.js setup
    assert len(graph_payload.get("warnings", [])) == 0, f"Should have no warnings, got: {graph_payload.get('warnings', [])}"
