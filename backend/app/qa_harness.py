"""
QA harness with acceptance thresholds for automated testing and validation.
Tests the complete pipeline against golden repository samples.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import logging

from .models import CapabilityModel, GraphModel, RouteModel
from .pipeline_orchestrator import PipelineOrchestrator
from .storage import ArtifactStorage
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

@dataclass
class AcceptanceThresholds:
    """Acceptance thresholds for QA testing."""
    routes_recall: float = 0.8  # 80% of expected routes found
    routes_precision: float = 0.9  # 90% of found routes are correct
    job_edges_precision: float = 0.8  # 80% of job edges are correct
    stores_precision: float = 0.8  # 80% of stores detected correctly
    externals_precision: float = 0.7  # 70% of externals detected correctly
    unresolved_import_ratio: float = 0.2  # Max 20% unresolved imports
    capability_coverage: float = 0.8  # 80% of expected capabilities found
    p95_runtime_seconds: float = 300.0  # 95th percentile runtime under 5 minutes
    hypothesis_ratio: float = 0.3  # Max 30% hypothesis edges
    llm_token_efficiency: float = 0.8  # 80% token efficiency

@dataclass
class TestResult:
    """Result of a QA test."""
    test_name: str
    passed: bool
    score: float
    threshold: float
    details: Dict[str, Any]
    error: Optional[str] = None

@dataclass
class GoldenRepository:
    """Golden repository sample for testing."""
    name: str
    path: Path
    expected_routes: List[Dict[str, Any]]
    expected_jobs: List[Dict[str, Any]]
    expected_stores: List[Dict[str, Any]]
    expected_externals: List[Dict[str, Any]]
    expected_capabilities: List[Dict[str, Any]]
    expected_imports: List[Dict[str, Any]]

class QAHarness:
    """QA harness for automated testing and validation."""
    
    def __init__(self, pipeline_orchestrator: PipelineOrchestrator, artifact_storage: ArtifactStorage):
        self.pipeline_orchestrator = pipeline_orchestrator
        self.artifact_storage = artifact_storage
        self.llm_client = LLMClient()
        
        # Test results
        self.test_results: List[TestResult] = []
        self.golden_repositories: List[GoldenRepository] = []
        
        # Load golden repositories
        self._load_golden_repositories()
    
    def _load_golden_repositories(self) -> None:
        """Load golden repository samples for testing."""
        # This would load from a configuration file or database
        # For now, create a sample golden repository
        sample_repo = GoldenRepository(
            name="sample_fastapi_app",
            path=Path("tests/golden_repos/sample_fastapi_app"),
            expected_routes=[
                {"method": "GET", "path": "/health", "handler": "health_check"},
                {"method": "POST", "path": "/users", "handler": "create_user"},
                {"method": "GET", "path": "/users/{user_id}", "handler": "get_user"}
            ],
            expected_jobs=[
                {"name": "send_email", "type": "celery", "producer": "user_service"}
            ],
            expected_stores=[
                {"name": "User", "type": "sqlalchemy", "fields": ["id", "name", "email"]}
            ],
            expected_externals=[
                {"name": "sendgrid", "type": "email_service"},
                {"name": "postgres", "type": "database"}
            ],
            expected_capabilities=[
                {"name": "User Management API", "lane": "api", "entrypoints": ["/users"]}
            ],
            expected_imports=[
                {"from": "fastapi", "to": "FastAPI", "external": True},
                {"from": "sqlalchemy", "to": "Column", "external": True}
            ]
        )
        
        self.golden_repositories.append(sample_repo)
    
    async def run_full_qa_suite(self, thresholds: Optional[AcceptanceThresholds] = None) -> Dict[str, Any]:
        """Run the complete QA test suite."""
        if thresholds is None:
            thresholds = AcceptanceThresholds()
        
        logger.info("Starting QA test suite")
        start_time = time.time()
        
        # Clear previous results
        self.test_results.clear()
        
        # Run tests for each golden repository
        for golden_repo in self.golden_repositories:
            await self._test_golden_repository(golden_repo, thresholds)
        
        # Calculate overall results
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.passed)
        overall_score = passed_tests / max(total_tests, 1)
        
        # Generate report
        report = {
            "overall_score": overall_score,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "test_results": [result.__dict__ for result in self.test_results],
            "thresholds": thresholds.__dict__,
            "execution_time_seconds": time.time() - start_time,
            "recommendations": self._generate_recommendations()
        }
        
        logger.info(f"QA test suite completed: {passed_tests}/{total_tests} tests passed")
        return report
    
    async def _test_golden_repository(self, golden_repo: GoldenRepository, thresholds: AcceptanceThresholds) -> None:
        """Test a single golden repository."""
        logger.info(f"Testing golden repository: {golden_repo.name}")
        
        try:
            # Run analysis pipeline
            job_id = await self.pipeline_orchestrator.ingest_repository(
                golden_repo.name, 
                golden_repo.path
            )
            
            # Wait for completion
            await self._wait_for_completion(job_id)
            
            # Retrieve artifacts
            artifacts = await self._retrieve_artifacts(golden_repo.name)
            
            # Run individual tests
            await self._test_routes_recall(golden_repo, artifacts, thresholds)
            await self._test_routes_precision(golden_repo, artifacts, thresholds)
            await self._test_job_edges_precision(golden_repo, artifacts, thresholds)
            await self._test_stores_precision(golden_repo, artifacts, thresholds)
            await self._test_externals_precision(golden_repo, artifacts, thresholds)
            await self._test_unresolved_imports(golden_repo, artifacts, thresholds)
            await self._test_capability_coverage(golden_repo, artifacts, thresholds)
            await self._test_runtime_performance(golden_repo, artifacts, thresholds)
            await self._test_hypothesis_ratio(golden_repo, artifacts, thresholds)
            await self._test_llm_efficiency(golden_repo, artifacts, thresholds)
            
        except Exception as e:
            logger.error(f"Failed to test golden repository {golden_repo.name}: {e}")
            self.test_results.append(TestResult(
                test_name=f"repository_{golden_repo.name}",
                passed=False,
                score=0.0,
                threshold=0.0,
                details={},
                error=str(e)
            ))
    
    async def _wait_for_completion(self, job_id: str, timeout: int = 600) -> None:
        """Wait for job completion with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.pipeline_orchestrator.get_job_status(job_id)
            if status and status.get("status") in ["completed", "failed"]:
                return
            
            await asyncio.sleep(1)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    async def _retrieve_artifacts(self, repo_id: str) -> Dict[str, Any]:
        """Retrieve all artifacts for a repository."""
        artifacts = {}
        
        artifact_types = ["graphs", "capabilities", "summaries", "metrics"]
        for artifact_type in artifact_types:
            artifact_data = self.artifact_storage.retrieve_artifact(repo_id, artifact_type)
            if artifact_data:
                artifacts[artifact_type] = artifact_data.get("content", {})
        
        return artifacts
    
    async def _test_routes_recall(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test route recall - how many expected routes were found."""
        try:
            expected_routes = golden_repo.expected_routes
            found_routes = self._extract_found_routes(artifacts)
            
            # Calculate recall
            found_expected = 0
            for expected_route in expected_routes:
                if self._route_matches_expected(expected_route, found_routes):
                    found_expected += 1
            
            recall = found_expected / max(len(expected_routes), 1)
            passed = recall >= thresholds.routes_recall
            
            self.test_results.append(TestResult(
                test_name="routes_recall",
                passed=passed,
                score=recall,
                threshold=thresholds.routes_recall,
                details={
                    "expected_routes": len(expected_routes),
                    "found_expected": found_expected,
                    "found_routes": len(found_routes)
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="routes_recall",
                passed=False,
                score=0.0,
                threshold=thresholds.routes_recall,
                details={},
                error=str(e)
            ))
    
    async def _test_routes_precision(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test route precision - how many found routes are correct."""
        try:
            expected_routes = golden_repo.expected_routes
            found_routes = self._extract_found_routes(artifacts)
            
            # Calculate precision
            correct_routes = 0
            for found_route in found_routes:
                if self._route_matches_any_expected(found_route, expected_routes):
                    correct_routes += 1
            
            precision = correct_routes / max(len(found_routes), 1)
            passed = precision >= thresholds.routes_precision
            
            self.test_results.append(TestResult(
                test_name="routes_precision",
                passed=passed,
                score=precision,
                threshold=thresholds.routes_precision,
                details={
                    "found_routes": len(found_routes),
                    "correct_routes": correct_routes
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="routes_precision",
                passed=False,
                score=0.0,
                threshold=thresholds.routes_precision,
                details={},
                error=str(e)
            ))
    
    async def _test_job_edges_precision(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test job edges precision."""
        try:
            expected_jobs = golden_repo.expected_jobs
            found_jobs = self._extract_found_jobs(artifacts)
            
            # Calculate precision
            correct_jobs = 0
            for found_job in found_jobs:
                if self._job_matches_any_expected(found_job, expected_jobs):
                    correct_jobs += 1
            
            precision = correct_jobs / max(len(found_jobs), 1)
            passed = precision >= thresholds.job_edges_precision
            
            self.test_results.append(TestResult(
                test_name="job_edges_precision",
                passed=passed,
                score=precision,
                threshold=thresholds.job_edges_precision,
                details={
                    "found_jobs": len(found_jobs),
                    "correct_jobs": correct_jobs
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="job_edges_precision",
                passed=False,
                score=0.0,
                threshold=thresholds.job_edges_precision,
                details={},
                error=str(e)
            ))
    
    async def _test_stores_precision(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test stores precision."""
        try:
            expected_stores = golden_repo.expected_stores
            found_stores = self._extract_found_stores(artifacts)
            
            # Calculate precision
            correct_stores = 0
            for found_store in found_stores:
                if self._store_matches_any_expected(found_store, expected_stores):
                    correct_stores += 1
            
            precision = correct_stores / max(len(found_stores), 1)
            passed = precision >= thresholds.stores_precision
            
            self.test_results.append(TestResult(
                test_name="stores_precision",
                passed=passed,
                score=precision,
                threshold=thresholds.stores_precision,
                details={
                    "found_stores": len(found_stores),
                    "correct_stores": correct_stores
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="stores_precision",
                passed=False,
                score=0.0,
                threshold=thresholds.stores_precision,
                details={},
                error=str(e)
            ))
    
    async def _test_externals_precision(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test externals precision."""
        try:
            expected_externals = golden_repo.expected_externals
            found_externals = self._extract_found_externals(artifacts)
            
            # Calculate precision
            correct_externals = 0
            for found_external in found_externals:
                if self._external_matches_any_expected(found_external, expected_externals):
                    correct_externals += 1
            
            precision = correct_externals / max(len(found_externals), 1)
            passed = precision >= thresholds.externals_precision
            
            self.test_results.append(TestResult(
                test_name="externals_precision",
                passed=passed,
                score=precision,
                threshold=thresholds.externals_precision,
                details={
                    "found_externals": len(found_externals),
                    "correct_externals": correct_externals
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="externals_precision",
                passed=False,
                score=0.0,
                threshold=thresholds.externals_precision,
                details={},
                error=str(e)
            ))
    
    async def _test_unresolved_imports(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test unresolved import ratio."""
        try:
            metrics = artifacts.get("metrics", {})
            unresolved_ratio = metrics.get("unresolved_import_ratio", 0.0)
            
            passed = unresolved_ratio <= thresholds.unresolved_import_ratio
            
            self.test_results.append(TestResult(
                test_name="unresolved_imports",
                passed=passed,
                score=1.0 - unresolved_ratio,  # Invert so higher is better
                threshold=1.0 - thresholds.unresolved_import_ratio,
                details={
                    "unresolved_ratio": unresolved_ratio
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="unresolved_imports",
                passed=False,
                score=0.0,
                threshold=1.0 - thresholds.unresolved_import_ratio,
                details={},
                error=str(e)
            ))
    
    async def _test_capability_coverage(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test capability coverage."""
        try:
            expected_capabilities = golden_repo.expected_capabilities
            found_capabilities = self._extract_found_capabilities(artifacts)
            
            # Calculate coverage
            found_expected = 0
            for expected_capability in expected_capabilities:
                if self._capability_matches_expected(expected_capability, found_capabilities):
                    found_expected += 1
            
            coverage = found_expected / max(len(expected_capabilities), 1)
            passed = coverage >= thresholds.capability_coverage
            
            self.test_results.append(TestResult(
                test_name="capability_coverage",
                passed=passed,
                score=coverage,
                threshold=thresholds.capability_coverage,
                details={
                    "expected_capabilities": len(expected_capabilities),
                    "found_expected": found_expected,
                    "found_capabilities": len(found_capabilities)
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="capability_coverage",
                passed=False,
                score=0.0,
                threshold=thresholds.capability_coverage,
                details={},
                error=str(e)
            ))
    
    async def _test_runtime_performance(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test runtime performance."""
        try:
            metrics = artifacts.get("metrics", {})
            runtime_seconds = metrics.get("total_duration", 0.0)
            
            passed = runtime_seconds <= thresholds.p95_runtime_seconds
            
            self.test_results.append(TestResult(
                test_name="runtime_performance",
                passed=passed,
                score=max(0.0, 1.0 - (runtime_seconds / thresholds.p95_runtime_seconds)),
                threshold=thresholds.p95_runtime_seconds,
                details={
                    "runtime_seconds": runtime_seconds
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="runtime_performance",
                passed=False,
                score=0.0,
                threshold=thresholds.p95_runtime_seconds,
                details={},
                error=str(e)
            ))
    
    async def _test_hypothesis_ratio(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test hypothesis ratio."""
        try:
            metrics = artifacts.get("metrics", {})
            hypothesis_ratio = metrics.get("hypothesis_edge_ratio", 0.0)
            
            passed = hypothesis_ratio <= thresholds.hypothesis_ratio
            
            self.test_results.append(TestResult(
                test_name="hypothesis_ratio",
                passed=passed,
                score=1.0 - hypothesis_ratio,  # Invert so lower is better
                threshold=1.0 - thresholds.hypothesis_ratio,
                details={
                    "hypothesis_ratio": hypothesis_ratio
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="hypothesis_ratio",
                passed=False,
                score=0.0,
                threshold=1.0 - thresholds.hypothesis_ratio,
                details={},
                error=str(e)
            ))
    
    async def _test_llm_efficiency(self, golden_repo: GoldenRepository, artifacts: Dict[str, Any], thresholds: AcceptanceThresholds) -> None:
        """Test LLM token efficiency."""
        try:
            llm_stats = self.llm_client.get_usage_stats()
            
            # Calculate efficiency (simplified)
            total_tokens = llm_stats.get("usage_stats", {}).get("total_tokens", 0)
            successful_calls = llm_stats.get("usage_stats", {}).get("successful_calls", 0)
            
            if total_tokens > 0 and successful_calls > 0:
                efficiency = successful_calls / (total_tokens / 1000)  # Calls per 1K tokens
            else:
                efficiency = 1.0
            
            passed = efficiency >= thresholds.llm_token_efficiency
            
            self.test_results.append(TestResult(
                test_name="llm_efficiency",
                passed=passed,
                score=efficiency,
                threshold=thresholds.llm_token_efficiency,
                details={
                    "total_tokens": total_tokens,
                    "successful_calls": successful_calls,
                    "efficiency": efficiency
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name="llm_efficiency",
                passed=False,
                score=0.0,
                threshold=thresholds.llm_token_efficiency,
                details={},
                error=str(e)
            ))
    
    def _extract_found_routes(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract found routes from artifacts."""
        routes = []
        
        # Extract from graphs artifact
        graphs = artifacts.get("graphs", {})
        if "routes" in graphs:
            routes.extend(graphs["routes"])
        
        return routes
    
    def _extract_found_jobs(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract found jobs from artifacts."""
        jobs = []
        
        # Extract from graphs artifact
        graphs = artifacts.get("graphs", {})
        if "jobs" in graphs:
            jobs.extend(graphs["jobs"])
        
        return jobs
    
    def _extract_found_stores(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract found stores from artifacts."""
        stores = []
        
        # Extract from graphs artifact
        graphs = artifacts.get("graphs", {})
        if "stores" in graphs:
            stores.extend(graphs["stores"])
        
        return stores
    
    def _extract_found_externals(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract found externals from artifacts."""
        externals = []
        
        # Extract from graphs artifact
        graphs = artifacts.get("graphs", {})
        if "externals" in graphs:
            externals.extend(graphs["externals"])
        
        return externals
    
    def _extract_found_capabilities(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract found capabilities from artifacts."""
        capabilities = artifacts.get("capabilities", {}).get("capabilities", [])
        return capabilities
    
    def _route_matches_expected(self, expected_route: Dict[str, Any], found_routes: List[Dict[str, Any]]) -> bool:
        """Check if an expected route was found."""
        for found_route in found_routes:
            if (found_route.get("method") == expected_route.get("method") and
                found_route.get("path") == expected_route.get("path")):
                return True
        return False
    
    def _route_matches_any_expected(self, found_route: Dict[str, Any], expected_routes: List[Dict[str, Any]]) -> bool:
        """Check if a found route matches any expected route."""
        for expected_route in expected_routes:
            if (found_route.get("method") == expected_route.get("method") and
                found_route.get("path") == expected_route.get("path")):
                return True
        return False
    
    def _job_matches_any_expected(self, found_job: Dict[str, Any], expected_jobs: List[Dict[str, Any]]) -> bool:
        """Check if a found job matches any expected job."""
        for expected_job in expected_jobs:
            if found_job.get("name") == expected_job.get("name"):
                return True
        return False
    
    def _store_matches_any_expected(self, found_store: Dict[str, Any], expected_stores: List[Dict[str, Any]]) -> bool:
        """Check if a found store matches any expected store."""
        for expected_store in expected_stores:
            if found_store.get("name") == expected_store.get("name"):
                return True
        return False
    
    def _external_matches_any_expected(self, found_external: Dict[str, Any], expected_externals: List[Dict[str, Any]]) -> bool:
        """Check if a found external matches any expected external."""
        for expected_external in expected_externals:
            if found_external.get("name") == expected_external.get("name"):
                return True
        return False
    
    def _capability_matches_expected(self, expected_capability: Dict[str, Any], found_capabilities: List[Dict[str, Any]]) -> bool:
        """Check if an expected capability was found."""
        for found_capability in found_capabilities:
            if found_capability.get("name") == expected_capability.get("name"):
                return True
        return False
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_tests = [result for result in self.test_results if not result.passed]
        
        for test_result in failed_tests:
            if test_result.test_name == "routes_recall":
                recommendations.append("Improve route detection algorithms")
            elif test_result.test_name == "routes_precision":
                recommendations.append("Reduce false positive route detections")
            elif test_result.test_name == "unresolved_imports":
                recommendations.append("Improve import resolution accuracy")
            elif test_result.test_name == "hypothesis_ratio":
                recommendations.append("Reduce hypothesis edges with better static analysis")
            elif test_result.test_name == "runtime_performance":
                recommendations.append("Optimize pipeline performance")
            elif test_result.test_name == "llm_efficiency":
                recommendations.append("Improve LLM token efficiency")
        
        if not recommendations:
            recommendations.append("All tests passed - system is performing well")
        
        return recommendations
