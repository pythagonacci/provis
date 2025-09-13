"""Storage system for artifacts with schema versioning."""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ArtifactStorage:
    """Manages storage of analysis artifacts."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Schema versions
        self.schema_versions = {
            "tree": "1.0.0",
            "files": "1.0.0", 
            "graphs": "1.0.0",
            "capabilities": "1.0.0",
            "summaries": "1.0.0",
            "warnings": "1.0.0",
            "metrics": "1.0.0",
            "preflight": "1.0.0"
        }
    
    def store_artifact(self, repo_id: str, kind: str, content: Dict[str, Any]) -> str:
        """Store an artifact with versioning."""
        try:
            # Generate artifact ID
            artifact_id = self._generate_artifact_id(repo_id, kind)
            
            # Add schema version
            schema_version = self.schema_versions.get(kind, "1.0.0")
            
            # Create artifact data
            artifact_data = {
                "schema_version": schema_version,
                "content_hash": "",
                "generated_at": datetime.now().isoformat(),
                "repo_id": repo_id,
                "content": content
            }
            
            # Calculate content hash
            content_json = json.dumps(artifact_data, sort_keys=True)
            content_hash = hashlib.sha256(content_json.encode()).hexdigest()
            artifact_data["content_hash"] = content_hash
            
            # Create directory structure
            repo_dir = self.base_path / repo_id
            repo_dir.mkdir(exist_ok=True)
            
            # Store artifact
            artifact_path = repo_dir / f"{kind}.json"
            with open(artifact_path, 'w') as f:
                json.dump(artifact_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Stored artifact: {artifact_id} ({kind})")
            return artifact_id
            
        except Exception as e:
            logger.error(f"Failed to store artifact {kind} for repo {repo_id}: {e}")
            raise
    
    def retrieve_artifact(self, repo_id: str, kind: str) -> Optional[Dict[str, Any]]:
        """Retrieve an artifact by repo and kind."""
        try:
            artifact_path = self.base_path / repo_id / f"{kind}.json"
            
            if not artifact_path.exists():
                return None
            
            with open(artifact_path, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Failed to retrieve artifact {kind} for repo {repo_id}: {e}")
            return None
    
    def _generate_artifact_id(self, repo_id: str, kind: str) -> str:
        """Generate a unique artifact ID."""
        timestamp = datetime.now().isoformat()
        id_data = f"{repo_id}:{kind}:{timestamp}"
        return hashlib.sha256(id_data.encode()).hexdigest()[:16]