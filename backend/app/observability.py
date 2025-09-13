"""
Observability and metrics collection for Provis.
Tracks parsing performance, LLM usage, and degradation patterns.
"""
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from threading import Lock

logger = logging.getLogger(__name__)

@dataclass
class MetricsCollector:
    """Thread-safe metrics collector for Provis operations."""
    
    # Counters
    files_parsed: int = 0
    files_skipped: int = 0
    imports_resolved: int = 0
    imports_unresolved: int = 0
    routes_detected: int = 0
    jobs_detected: int = 0
    stores_detected: int = 0
    externals_detected: int = 0
    
    # LLM metrics
    llm_calls_total: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    llm_cache_hits: int = 0
    llm_timeouts: int = 0
    
    # Detector hit rates
    detector_hits: Dict[str, int] = field(default_factory=dict)
    
    # Fallback tracking
    fallback_counts: Dict[str, int] = field(default_factory=dict)
    fallback_samples: Dict[str, list] = field(default_factory=dict)
    
    # Timing
    phase_timings: Dict[str, float] = field(default_factory=dict)
    file_parse_times: list = field(default_factory=list)
    
    # Thread safety
    _lock: Lock = field(default_factory=Lock)
    
    def record_file_parsed(self, parse_time: float, skipped: bool = False):
        """Record a file parsing event."""
        with self._lock:
            if skipped:
                self.files_skipped += 1
            else:
                self.files_parsed += 1
            self.file_parse_times.append(parse_time)
    
    def record_import_resolved(self, resolved: bool):
        """Record an import resolution event."""
        with self._lock:
            if resolved:
                self.imports_resolved += 1
            else:
                self.imports_unresolved += 1
    
    def record_detector_hit(self, detector_name: str):
        """Record a detector hit."""
        with self._lock:
            self.detector_hits[detector_name] = self.detector_hits.get(detector_name, 0) + 1
    
    def record_llm_call(self, tokens_in: int, tokens_out: int, model: str, 
                       cache_hit: bool = False, timeout: bool = False):
        """Record an LLM call."""
        with self._lock:
            self.llm_calls_total += 1
            self.llm_tokens_in += tokens_in
            self.llm_tokens_out += tokens_out
            if cache_hit:
                self.llm_cache_hits += 1
            if timeout:
                self.llm_timeouts += 1
    
    def record_fallback(self, reason_code: str, file_path: str, sample_limit: int = 10):
        """Record a fallback event with sample."""
        with self._lock:
            self.fallback_counts[reason_code] = self.fallback_counts.get(reason_code, 0) + 1
            if reason_code not in self.fallback_samples:
                self.fallback_samples[reason_code] = []
            if len(self.fallback_samples[reason_code]) < sample_limit:
                self.fallback_samples[reason_code].append(file_path)
    
    def record_phase_timing(self, phase: str, duration: float):
        """Record phase timing."""
        with self._lock:
            self.phase_timings[phase] = duration
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        with self._lock:
            total_files = self.files_parsed + self.files_skipped
            total_imports = self.imports_resolved + self.imports_unresolved
            
            return {
                "files": {
                    "parsed": self.files_parsed,
                    "skipped": self.files_skipped,
                    "total": total_files,
                    "big_file_ratio": self.files_skipped / max(total_files, 1)
                },
                "imports": {
                    "resolved": self.imports_resolved,
                    "unresolved": self.imports_unresolved,
                    "total": total_imports,
                    "unresolved_ratio": self.imports_unresolved / max(total_imports, 1)
                },
                "detectors": {
                    "routes": self.routes_detected,
                    "jobs": self.jobs_detected,
                    "stores": self.stores_detected,
                    "externals": self.externals_detected,
                    "hit_rates": dict(self.detector_hits)
                },
                "llm": {
                    "calls_total": self.llm_calls_total,
                    "tokens_in": self.llm_tokens_in,
                    "tokens_out": self.llm_tokens_out,
                    "cache_hits": self.llm_cache_hits,
                    "timeouts": self.llm_timeouts,
                    "cache_hit_rate": self.llm_cache_hits / max(self.llm_calls_total, 1)
                },
                "fallbacks": {
                    "counts": dict(self.fallback_counts),
                    "samples": dict(self.fallback_samples)
                },
                "timing": {
                    "phase_timings": dict(self.phase_timings),
                    "avg_file_parse_time": sum(self.file_parse_times) / max(len(self.file_parse_times), 1)
                }
            }

# Global metrics collector instance
_metrics_collector = MetricsCollector()

def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _metrics_collector

def record_fallback(reason_code: str, file_path: str):
    """Convenience function to record a fallback."""
    _metrics_collector.record_fallback(reason_code, file_path)

def record_llm_call(tokens_in: int, tokens_out: int, model: str, 
                   cache_hit: bool = False, timeout: bool = False):
    """Convenience function to record an LLM call."""
    _metrics_collector.record_llm_call(tokens_in, tokens_out, model, cache_hit, timeout)

def record_detector_hit(detector_name: str):
    """Convenience function to record a detector hit."""
    _metrics_collector.record_detector_hit(detector_name)

def record_phase_timing(phase: str, duration: float):
    """Convenience function to record phase timing."""
    _metrics_collector.record_phase_timing(phase, duration)