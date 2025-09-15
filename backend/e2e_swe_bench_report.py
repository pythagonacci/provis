#!/usr/bin/env python3
"""
Comprehensive E2E SWE-bench test report for Provis ingestion pipeline.
Tests timing (<2min) and accuracy (>80%) requirements.
"""

import tempfile
import zipfile
from pathlib import Path
import sys
import time
import json

# Add the backend directory to the path
sys.path.insert(0, '/Users/amnaahmad/provis/provis/backend')

from app.ingest import extract_snapshot
from app.parsers.base import parse_files, discover_files, build_graph, build_files_payload
from app.preflight import run_preflight_scan
from app.detectors import DetectorRegistry

def main():
    print("🚀 Starting E2E SWE-bench Test for Provis Ingestion Pipeline")
    print("=" * 60)
    
    # Use the domain-locker repository as our SWE-bench sample
    domain_locker_path = Path("/Users/amnaahmad/provis/provis/domain-locker")
    print(f"📁 Test Repository: {domain_locker_path.name}")
    print(f"   - Angular/TypeScript application")
    print(f"   - Complex codebase with multiple components")
    print(f"   - Real-world SWE-bench style sample")
    
    # Create a temporary ZIP
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        zip_path = Path(tmp_file.name)
    
    print(f"\n📦 Creating test ZIP...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in domain_locker_path.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(domain_locker_path.parent)
                zipf.write(file_path, arcname)
    
    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo_dir = Path(temp_dir) / "repo_test"
        temp_repo_dir.mkdir(parents=True)
        
        snapshot_dir = temp_repo_dir / "snapshot"
        snapshot_dir.mkdir()
        
        print(f"\n⏱️  Running E2E Pipeline...")
        start_time = time.time()
        
        # Stage 1: Upload and extract
        upload_start = time.time()
        file_count = extract_snapshot(zip_path, snapshot_dir)
        upload_time = time.time() - upload_start
        
        # Stage 2: Preflight detection
        preflight_start = time.time()
        preflight_result = run_preflight_scan(snapshot_dir)
        preflight_time = time.time() - preflight_start
        
        # Stage 3: File discovery and parsing
        parse_start = time.time()
        discovered = discover_files(snapshot_dir)
        files_list, warnings = parse_files(snapshot_dir, discovered)
        parse_time = time.time() - parse_start
        
        # Create files_payload structure
        files_payload = build_files_payload('test_repo', files_list, warnings)
        
        # Stage 4: Graph building (includes import resolution)
        graph_start = time.time()
        graph_payload = build_graph(files_payload)
        graph_time = time.time() - graph_start
        
        # Stage 5: Detection (sample)
        detect_start = time.time()
        detector_registry = DetectorRegistry()
        detection_results = {}
        sample_files = files_list[:10] if len(files_list) > 10 else files_list
        for file_info in sample_files:
            file_path = Path(file_info['path'])
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                detection_results[str(file_path)] = detector_registry.detect_all(file_path, content)
        detect_time = time.time() - detect_start
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        total_files = len(files_payload.get('files', []))
        files_with_imports = sum(1 for f in files_payload.get('files', []) if f.get('imports'))
        files_with_functions = sum(1 for f in files_payload.get('files', []) if f.get('functions'))
        files_with_classes = sum(1 for f in files_payload.get('files', []) if f.get('classes'))
        
        edges = graph_payload.get('edges', [])
        total_imports = len(edges)
        resolved_imports = sum(1 for edge in edges if not edge.get('external', True))
        
        # Calculate percentages
        parse_accuracy = (files_with_imports / total_files * 100) if total_files > 0 else 0
        function_accuracy = (files_with_functions / total_files * 100) if total_files > 0 else 0
        import_accuracy = (resolved_imports / total_imports * 100) if total_imports > 0 else 0
        
        # Overall accuracy (weighted average)
        overall_accuracy = (parse_accuracy * 0.4 + function_accuracy * 0.3 + import_accuracy * 0.3)
        
        # Processing speed
        files_per_second = total_files / parse_time if parse_time > 0 else 0
        
        print(f"\n📊 E2E Test Results")
        print(f"=" * 40)
        
        print(f"\n⏱️  TIMING RESULTS:")
        print(f"   Upload & Extract: {upload_time:.2f}s")
        print(f"   Preflight Scan:   {preflight_time:.2f}s")
        print(f"   File Parsing:     {parse_time:.2f}s")
        print(f"   Graph Building:   {graph_time:.2f}s")
        print(f"   Detection:        {detect_time:.2f}s")
        print(f"   ─────────────────────")
        print(f"   TOTAL TIME:       {total_time:.2f}s")
        print(f"   Processing Speed: {files_per_second:.1f} files/sec")
        
        print(f"\n🎯 ACCURACY RESULTS:")
        print(f"   Files Processed:     {total_files}")
        print(f"   Files with Imports:  {files_with_imports} ({parse_accuracy:.1f}%)")
        print(f"   Files with Functions: {files_with_functions} ({function_accuracy:.1f}%)")
        print(f"   Files with Classes:   {files_with_classes}")
        print(f"   ─────────────────────")
        print(f"   Total Imports:       {total_imports}")
        print(f"   Resolved Imports:    {resolved_imports} ({import_accuracy:.1f}%)")
        print(f"   ─────────────────────")
        print(f"   OVERALL ACCURACY:    {overall_accuracy:.1f}%")
        
        print(f"\n🔍 DETECTION RESULTS:")
        total_detections = 0
        for file_path, detections in detection_results.items():
            for detector_name, detector_result in detections.items():
                items = detector_result.items if hasattr(detector_result, 'items') else []
                total_detections += len(items)
        print(f"   Sample Files Tested: {len(sample_files)}")
        print(f"   Total Detections:    {total_detections}")
        
        print(f"\n✅ REQUIREMENTS CHECK:")
        timing_ok = total_time < 120  # 2 minutes
        accuracy_ok = overall_accuracy >= 80.0
        speed_ok = files_per_second >= 10
        
        print(f"   {'✅' if timing_ok else '❌'} Timing <2min:     {total_time:.1f}s ({'PASS' if timing_ok else 'FAIL'})")
        print(f"   {'✅' if accuracy_ok else '❌'} Accuracy >80%:    {overall_accuracy:.1f}% ({'PASS' if accuracy_ok else 'FAIL'})")
        print(f"   {'✅' if speed_ok else '❌'} Speed >10 files/s: {files_per_second:.1f} files/sec ({'PASS' if speed_ok else 'FAIL'})")
        
        print(f"\n🏆 FINAL RESULT:")
        if timing_ok and accuracy_ok and speed_ok:
            print(f"   🎉 E2E SWE-Bench Test: PASSED")
            print(f"   ✅ All requirements met!")
        else:
            print(f"   ❌ E2E SWE-Bench Test: FAILED")
            failed_requirements = []
            if not timing_ok:
                failed_requirements.append("timing")
            if not accuracy_ok:
                failed_requirements.append("accuracy")
            if not speed_ok:
                failed_requirements.append("speed")
            print(f"   ❌ Failed requirements: {', '.join(failed_requirements)}")
        
        # Save detailed report
        report = {
            "test_info": {
                "repository": "domain-locker",
                "type": "Angular/TypeScript",
                "total_files": total_files,
                "test_date": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "timing": {
                "total_time": total_time,
                "upload_time": upload_time,
                "preflight_time": preflight_time,
                "parse_time": parse_time,
                "graph_time": graph_time,
                "detect_time": detect_time,
                "files_per_second": files_per_second
            },
            "accuracy": {
                "parse_accuracy": parse_accuracy,
                "function_accuracy": function_accuracy,
                "import_accuracy": import_accuracy,
                "overall_accuracy": overall_accuracy,
                "files_with_imports": files_with_imports,
                "files_with_functions": files_with_functions,
                "total_imports": total_imports,
                "resolved_imports": resolved_imports
            },
            "requirements": {
                "timing_ok": timing_ok,
                "accuracy_ok": accuracy_ok,
                "speed_ok": speed_ok,
                "overall_pass": timing_ok and accuracy_ok and speed_ok
            }
        }
        
        report_path = Path("e2e_swe_bench_final_report.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_path}")
        print(f"=" * 60)
    
    # Cleanup
    zip_path.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
