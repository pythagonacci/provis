"""
Lightweight LLM re-ranking for messy fallback patterns.
Uses DistilBERT via HuggingFace for semantic similarity scoring.
"""
import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RerankCandidate:
    """Candidate for re-ranking."""
    text: str
    pattern: str
    confidence: float
    metadata: Dict[str, Any]

class DetectorReranker:
    """Lightweight re-ranker for detector patterns using semantic similarity."""
    
    def __init__(self):
        self.available = self._check_huggingface_availability()
        self.model = None
        self.tokenizer = None
        
        if self.available:
            self._load_model()
    
    def _check_huggingface_availability(self) -> bool:
        """Check if HuggingFace transformers is available."""
        try:
            import transformers
            return True
        except ImportError:
            logger.debug("HuggingFace transformers not available for re-ranking")
            return False
    
    def _load_model(self):
        """Load DistilBERT model for semantic similarity."""
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            model_name = "distilbert-base-uncased"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            
            # Set to evaluation mode
            self.model.eval()
            
            logger.debug("DistilBERT model loaded for detector re-ranking")
        except Exception as e:
            logger.warning(f"Failed to load DistilBERT model: {e}")
            self.available = False
    
    def rerank_route_candidates(self, candidates: List[Dict[str, Any]], 
                               context: str, file_path: str) -> List[Dict[str, Any]]:
        """Re-rank route detection candidates using semantic similarity."""
        if not self.available or not candidates:
            return candidates
        
        try:
            # Convert candidates to rerank format
            rerank_candidates = []
            for candidate in candidates:
                rerank_candidates.append(RerankCandidate(
                    text=f"{candidate.get('method', 'GET')} {candidate.get('path', '/')}",
                    pattern=candidate.get('pattern', ''),
                    confidence=candidate.get('confidence', 0.0),
                    metadata=candidate
                ))
            
            # Re-rank using semantic similarity
            reranked = self._semantic_rerank(rerank_candidates, context)
            
            # Convert back to original format
            result = []
            for candidate in reranked:
                result.append(candidate.metadata)
            
            logger.debug(f"Re-ranked {len(candidates)} route candidates for {file_path}")
            return result
            
        except Exception as e:
            logger.warning(f"Re-ranking failed for {file_path}: {e}")
            return candidates
    
    def rerank_model_candidates(self, candidates: List[Dict[str, Any]], 
                               context: str, file_path: str) -> List[Dict[str, Any]]:
        """Re-rank model detection candidates using semantic similarity."""
        if not self.available or not candidates:
            return candidates
        
        try:
            # Convert candidates to rerank format
            rerank_candidates = []
            for candidate in candidates:
                rerank_candidates.append(RerankCandidate(
                    text=candidate.get('name', 'Unknown'),
                    pattern=candidate.get('type', ''),
                    confidence=candidate.get('confidence', 0.0),
                    metadata=candidate
                ))
            
            # Re-rank using semantic similarity
            reranked = self._semantic_rerank(rerank_candidates, context)
            
            # Convert back to original format
            result = []
            for candidate in reranked:
                result.append(candidate.metadata)
            
            logger.debug(f"Re-ranked {len(candidates)} model candidates for {file_path}")
            return result
            
        except Exception as e:
            logger.warning(f"Re-ranking failed for {file_path}: {e}")
            return candidates
    
    def _semantic_rerank(self, candidates: List[RerankCandidate], 
                        context: str) -> List[RerankCandidate]:
        """Re-rank candidates using semantic similarity to context."""
        if not self.available or not candidates:
            return candidates
        
        try:
            import torch
            import torch.nn.functional as F
            
            # Tokenize context
            context_tokens = self.tokenizer(context, return_tensors="pt", 
                                          truncation=True, max_length=512)
            
            # Get context embedding
            with torch.no_grad():
                context_output = self.model(**context_tokens)
                context_embedding = context_output.last_hidden_state.mean(dim=1)
            
            # Score each candidate
            scored_candidates = []
            for candidate in candidates:
                # Tokenize candidate text
                candidate_tokens = self.tokenizer(candidate.text, return_tensors="pt",
                                                truncation=True, max_length=128)
                
                # Get candidate embedding
                with torch.no_grad():
                    candidate_output = self.model(**candidate_tokens)
                    candidate_embedding = candidate_output.last_hidden_state.mean(dim=1)
                
                # Calculate cosine similarity
                similarity = F.cosine_similarity(context_embedding, candidate_embedding).item()
                
                # Combine with original confidence
                combined_score = (similarity * 0.3) + (candidate.confidence * 0.7)
                
                scored_candidates.append((candidate, combined_score))
            
            # Sort by combined score
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            return [candidate for candidate, score in scored_candidates]
            
        except Exception as e:
            logger.warning(f"Semantic re-ranking failed: {e}")
            return candidates

# Global instance
_reranker = DetectorReranker()

def get_reranker() -> DetectorReranker:
    """Get the global re-ranker instance."""
    return _reranker
