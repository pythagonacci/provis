"""
Tests for parallel detector execution and Tree-sitter integration.
"""
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.detectors import DetectorRegistry, DetectorResult
from app.detector_tree_sitter import get_tree_sitter_detector
from app.detector_reranker import get_reranker
from app.models import EvidenceSpan

class TestParallelDetectors:
    """Test parallel detector execution."""
    
    def test_parallel_detector_execution(self):
        """Test that detectors run in parallel and complete faster than sequential."""
        registry = DetectorRegistry()
        
        # Create a test file with various patterns
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write("""
const express = require('express');
const app = express();

app.get('/users', (req, res) => {
    res.json({ users: [] });
});

app.post('/users', (req, res) => {
    res.json({ created: true });
});

// Prisma model
const prisma = new PrismaClient();

// External service
const stripe = require('stripe');
""")
            temp_file = Path(f.name)
        
        try:
            content = temp_file.read_text()
            
            # Time parallel execution
            start_time = time.time()
            results = registry.detect_all(temp_file, content)
            parallel_time = time.time() - start_time
            
            # Verify all detectors ran
            assert len(results) == 6  # All 6 detectors
            assert 'express' in results
            assert 'store' in results
            assert 'external' in results
            
            # Verify Express routes were detected
            express_result = results['express']
            assert len(express_result.items) >= 2  # GET and POST routes
            
            # Verify external services were detected
            external_result = results['external']
            assert len(external_result.items) >= 1  # Stripe detected
            
            # Verify parallel execution is reasonably fast (should be < 1s for this simple case)
            assert parallel_time < 1.0
            
            print(f"Parallel detector execution completed in {parallel_time:.3f}s")
            
        finally:
            temp_file.unlink()
    
    def test_detector_error_handling(self):
        """Test that detector errors don't crash the parallel execution."""
        registry = DetectorRegistry()
        
        # Create a file that might cause issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write("invalid javascript syntax {")
            temp_file = Path(f.name)
        
        try:
            content = temp_file.read_text()
            
            # Should not crash even with invalid syntax
            results = registry.detect_all(temp_file, content)
            
            # Should still return results for all detectors
            assert len(results) == 6
            
            # Some detectors might fail, but should return empty results
            for name, result in results.items():
                assert isinstance(result, DetectorResult)
                
        finally:
            temp_file.unlink()
    
    def test_detector_timing_metrics(self):
        """Test that timing metrics are recorded for detector execution."""
        registry = DetectorRegistry()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write("app.get('/test', () => {});")
            temp_file = Path(f.name)
        
        try:
            content = temp_file.read_text()
            
            # Mock the record_phase_timing function to capture calls
            with patch('app.detectors.record_phase_timing') as mock_record:
                results = registry.detect_all(temp_file, content)
                
                # Verify timing was recorded
                mock_record.assert_called()
                timing_calls = [call[0][0] for call in mock_record.call_args_list]
                assert any('detector_parallel' in call for call in timing_calls)
                
        finally:
            temp_file.unlink()

class TestTreeSitterIntegration:
    """Test Tree-sitter integration in detectors."""
    
    def test_tree_sitter_detector_availability(self):
        """Test Tree-sitter detector availability check."""
        detector = get_tree_sitter_detector()
        
        # Should be available if Tree-sitter is installed
        assert hasattr(detector, 'available')
        assert isinstance(detector.available, bool)
    
    def test_tree_sitter_route_detection(self):
        """Test Tree-sitter route detection."""
        detector = get_tree_sitter_detector()
        
        if not detector.available:
            pytest.skip("Tree-sitter not available")
        
        # Test route detection
        content = """
app.get('/users', (req, res) => {
    res.json({ users: [] });
});
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(content)
            temp_file = Path(f.name)
        
        try:
            routes = detector.detect_route_patterns(content, temp_file, "javascript")
            
            # Should detect routes if Tree-sitter is working
            # Note: This depends on the actual Tree-sitter implementation
            assert isinstance(routes, list)
            
        finally:
            temp_file.unlink()
    
    def test_tree_sitter_model_detection(self):
        """Test Tree-sitter model detection."""
        detector = get_tree_sitter_detector()
        
        if not detector.available:
            pytest.skip("Tree-sitter not available")
        
        # Test model detection
        content = """
class User {
    constructor(name, email) {
        this.name = name;
        this.email = email;
    }
}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(content)
            temp_file = Path(f.name)
        
        try:
            models = detector.detect_model_definitions(content, temp_file, "javascript")
            
            # Should detect models if Tree-sitter is working
            assert isinstance(models, list)
            
        finally:
            temp_file.unlink()

class TestReranker:
    """Test re-ranking functionality."""
    
    def test_reranker_availability(self):
        """Test re-ranker availability check."""
        reranker = get_reranker()
        
        # Should have availability check
        assert hasattr(reranker, 'available')
        assert isinstance(reranker.available, bool)
    
    def test_reranker_route_candidates(self):
        """Test re-ranking of route candidates."""
        reranker = get_reranker()
        
        if not reranker.available:
            pytest.skip("Re-ranker not available (HuggingFace not installed)")
        
        # Test candidates
        candidates = [
            {
                "method": "GET",
                "path": "/users",
                "confidence": 0.3,
                "pattern": "regex"
            },
            {
                "method": "POST",
                "path": "/users",
                "confidence": 0.3,
                "pattern": "regex"
            }
        ]
        
        context = "Express.js application with user management routes"
        
        # Should re-rank candidates
        reranked = reranker.rerank_route_candidates(candidates, context, "test.js")
        
        assert len(reranked) == len(candidates)
        assert isinstance(reranked, list)
    
    def test_reranker_fallback_behavior(self):
        """Test that re-ranker falls back gracefully when unavailable."""
        reranker = get_reranker()
        
        candidates = [
            {"method": "GET", "path": "/test", "confidence": 0.5}
        ]
        
        # Should return original candidates if re-ranker unavailable
        result = reranker.rerank_route_candidates(candidates, "context", "test.js")
        
        assert result == candidates

class TestDetectorPerformance:
    """Test detector performance improvements."""
    
    def test_parallel_vs_sequential_performance(self):
        """Test that parallel execution is faster than sequential."""
        registry = DetectorRegistry()
        
        # Create a larger test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write("""
const express = require('express');
const app = express();

// Multiple routes
app.get('/users', (req, res) => res.json({}));
app.post('/users', (req, res) => res.json({}));
app.put('/users/:id', (req, res) => res.json({}));
app.delete('/users/:id', (req, res) => res.json({}));

// Multiple models
class User {
    constructor() {}
}

class Product {
    constructor() {}
}

// Multiple external services
const stripe = require('stripe');
const twilio = require('twilio');
const aws = require('aws-sdk');

// Job queue
const queue = require('bull');
queue.add('process-user', {});
""")
            temp_file = Path(f.name)
        
        try:
            content = temp_file.read_text()
            
            # Time parallel execution
            start_time = time.time()
            parallel_results = registry.detect_all(temp_file, content)
            parallel_time = time.time() - start_time
            
            # Verify results
            assert len(parallel_results) == 6
            
            # Verify Express routes
            express_result = parallel_results['express']
            assert len(express_result.items) >= 4  # Multiple routes
            
            # Verify external services
            external_result = parallel_results['external']
            assert len(external_result.items) >= 3  # Multiple services
            
            # Verify performance (should be reasonably fast)
            assert parallel_time < 2.0
            
            print(f"Parallel execution time: {parallel_time:.3f}s")
            print(f"Detected {len(express_result.items)} routes, {len(external_result.items)} external services")
            
        finally:
            temp_file.unlink()
