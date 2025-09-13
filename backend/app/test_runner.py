"""Test runner for validating the complete system."""
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

from .qa_harness import QAHarness, AcceptanceThresholds
from .pipeline_orchestrator import PipelineOrchestrator
from .status_manager import StatusManager
from .storage import ArtifactStorage
from .api_v2 import create_app

logger = logging.getLogger(__name__)

async def run_system_tests() -> Dict[str, Any]:
    """Run comprehensive system tests."""
    logger.info("Starting system tests")
    
    try:
        # Initialize services
        status_dir = Path("data/status")
        storage_dir = Path("data/storage")
        
        status_manager = StatusManager(status_dir)
        artifact_storage = ArtifactStorage(storage_dir)
        pipeline_orchestrator = PipelineOrchestrator()
        
        # Start pipeline orchestrator
        await pipeline_orchestrator.start()
        
        # Create QA harness
        qa_harness = QAHarness(pipeline_orchestrator, artifact_storage)
        
        # Run QA tests
        test_results = await qa_harness.run_full_qa_suite()
        
        # Stop pipeline orchestrator
        await pipeline_orchestrator.stop()
        
        return test_results
        
    except Exception as e:
        logger.error(f"System tests failed: {e}")
        return {
            "overall_score": 0.0,
            "error": str(e),
            "test_results": [],
            "recommendations": ["Fix system initialization errors"]
        }

def run_api_tests() -> Dict[str, Any]:
    """Run API tests."""
    logger.info("Starting API tests")
    
    try:
        # Create FastAPI app
        app = create_app()
        
        # Test app creation
        if app is None:
            return {"passed": False, "error": "Failed to create FastAPI app"}
        
        # Test routes
        routes = [route.path for route in app.routes]
        expected_routes = [
            "/health",
            "/ingest", 
            "/status/{job_id}",
            "/events/{job_id}",
            "/artifacts/{repo_id}",
            "/artifacts/{repo_id}/{artifact_type}",
            "/stats",
            "/status"
        ]
        
        missing_routes = [route for route in expected_routes if route not in routes]
        
        return {
            "passed": len(missing_routes) == 0,
            "total_routes": len(routes),
            "missing_routes": missing_routes,
            "routes": routes
        }
        
    except Exception as e:
        logger.error(f"API tests failed: {e}")
        return {"passed": False, "error": str(e)}

async def main():
    """Main test runner."""
    logging.basicConfig(level=logging.INFO)
    
    print("Running Provis System Tests")
    print("=" * 50)
    
    # Run API tests
    print("\n1. API Tests")
    api_results = run_api_tests()
    if api_results["passed"]:
        print("✅ API tests passed")
    else:
        print(f"❌ API tests failed: {api_results.get('error', 'Unknown error')}")
    
    # Run system tests
    print("\n2. System Tests")
    try:
        system_results = await run_system_tests()
        
        overall_score = system_results.get("overall_score", 0.0)
        total_tests = system_results.get("total_tests", 0)
        passed_tests = system_results.get("passed_tests", 0)
        
        print(f"Overall Score: {overall_score:.2f}")
        print(f"Tests Passed: {passed_tests}/{total_tests}")
        
        if overall_score >= 0.8:
            print("✅ System tests passed")
        else:
            print("❌ System tests failed - score below threshold")
            
        # Print recommendations
        recommendations = system_results.get("recommendations", [])
        if recommendations:
            print("\nRecommendations:")
            for rec in recommendations:
                print(f"  - {rec}")
        
    except Exception as e:
        print(f"❌ System tests failed: {e}")
    
    print("\n" + "=" * 50)
    print("Test run completed")

if __name__ == "__main__":
    asyncio.run(main())
