"""
Versioned artifact storage for S3/MinIO with write-once behavior.
"""
import os
import json
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
import logging

logger = logging.getLogger(__name__)

class StorageError(Exception):
    """Storage-related errors."""
    pass

class ArtifactStorage:
    """Handles versioned artifact storage in S3/MinIO."""
    
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET", "provis-artifacts")
        self.region = os.getenv("S3_REGION", "us-east-1")
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")  # For MinIO
        
        # Configure S3 client
        config = Config(
            region_name=self.region,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50
        )
        
        try:
            if self.endpoint_url:
                # MinIO configuration
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                    config=config
                )
            else:
                # AWS S3 configuration
                self.s3_client = boto3.client('s3', config=config)
                
            # Test connection
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.info(f"Connected to storage bucket: {self.bucket}")
            
        except NoCredentialsError:
            logger.error("S3 credentials not found")
            raise StorageError("S3 credentials not configured")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"Bucket {self.bucket} not found")
                raise StorageError(f"Bucket {self.bucket} does not exist")
            else:
                logger.error(f"S3 connection error: {e}")
                raise StorageError(f"S3 connection failed: {e}")
    
    def _generate_key(self, repo_id: str, commit_hash: str, settings_hash: str, 
                     kind: str, version: int) -> str:
        """Generate S3 key for artifact."""
        return f"repos/{repo_id}/snapshots/{commit_hash}/{settings_hash}/{kind}.v{version}.json"
    
    def _get_latest_version(self, repo_id: str, commit_hash: str, 
                           settings_hash: str, kind: str) -> int:
        """Get the latest version number for an artifact kind."""
        prefix = f"repos/{repo_id}/snapshots/{commit_hash}/{settings_hash}/{kind}.v"
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=1000
            )
            
            if 'Contents' not in response:
                return 0
            
            versions = []
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith('.json'):
                    # Extract version number from key
                    version_part = key.split('.v')[-1].replace('.json', '')
                    try:
                        versions.append(int(version_part))
                    except ValueError:
                        continue
            
            return max(versions) if versions else 0
            
        except ClientError as e:
            logger.warning(f"Error listing versions for {kind}: {e}")
            return 0
    
    def write_versioned_artifact(self, snapshot_id: str, kind: str, 
                               content_bytes: bytes, *, 
                               schema_version: int = 1,
                               generator_version: str = "1.0.0",
                               repo_id: str = None,
                               commit_hash: str = None,
                               settings_hash: str = None) -> Dict[str, Any]:
        """
        Write a versioned artifact to S3 with write-once behavior.
        
        Args:
            snapshot_id: Unique snapshot identifier
            kind: Artifact type (files/graph/summaries/capabilities/metrics/tree)
            content_bytes: Artifact content as bytes
            schema_version: Schema version for compatibility
            generator_version: Generator version for tracking
            repo_id: Repository ID (required for key generation)
            commit_hash: Commit hash (required for key generation)
            settings_hash: Settings hash (required for key generation)
        
        Returns:
            Dict with uri, version, bytes
        """
        if not all([repo_id, commit_hash, settings_hash]):
            raise StorageError("repo_id, commit_hash, and settings_hash are required")
        
        # Get next version number
        latest_version = self._get_latest_version(repo_id, commit_hash, settings_hash, kind)
        next_version = latest_version + 1
        
        # Generate S3 key
        key = self._generate_key(repo_id, commit_hash, settings_hash, kind, next_version)
        
        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content_bytes,
                ContentType='application/json',
                Metadata={
                    'snapshot_id': snapshot_id,
                    'kind': kind,
                    'version': str(next_version),
                    'schema_version': str(schema_version),
                    'generator_version': generator_version,
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Uploaded artifact {kind} v{next_version} to {key}")
            
            return {
                'uri': f"s3://{self.bucket}/{key}",
                'version': next_version,
                'bytes': len(content_bytes)
            }
            
        except ClientError as e:
            logger.error(f"Failed to upload artifact {kind}: {e}")
            raise StorageError(f"Failed to upload artifact: {e}")
    
    def presign(self, uri: str, ttl_seconds: int = 600) -> str:
        """
        Generate a presigned URL for an artifact.
        
        Args:
            uri: S3 URI (s3://bucket/key)
            ttl_seconds: URL expiration time in seconds
        
        Returns:
            Presigned URL
        """
        if not uri.startswith('s3://'):
            raise StorageError(f"Invalid S3 URI: {uri}")
        
        # Parse S3 URI
        uri_parts = uri[5:].split('/', 1)  # Remove 's3://' and split
        if len(uri_parts) != 2:
            raise StorageError(f"Invalid S3 URI format: {uri}")
        
        bucket, key = uri_parts
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=ttl_seconds
            )
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {uri}: {e}")
            raise StorageError(f"Failed to generate presigned URL: {e}")
    
    def get_artifact(self, uri: str) -> bytes:
        """
        Retrieve an artifact from S3.
        
        Args:
            uri: S3 URI (s3://bucket/key)
        
        Returns:
            Artifact content as bytes
        """
        if not uri.startswith('s3://'):
            raise StorageError(f"Invalid S3 URI: {uri}")
        
        # Parse S3 URI
        uri_parts = uri[5:].split('/', 1)  # Remove 's3://' and split
        if len(uri_parts) != 2:
            raise StorageError(f"Invalid S3 URI format: {uri}")
        
        bucket, key = uri_parts
        
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise StorageError(f"Artifact not found: {uri}")
            else:
                logger.error(f"Failed to retrieve artifact {uri}: {e}")
                raise StorageError(f"Failed to retrieve artifact: {e}")
    
    def list_artifacts(self, repo_id: str, commit_hash: str, 
                      settings_hash: str) -> list[Dict[str, Any]]:
        """
        List all artifacts for a snapshot.
        
        Args:
            repo_id: Repository ID
            commit_hash: Commit hash
            settings_hash: Settings hash
        
        Returns:
            List of artifact metadata
        """
        prefix = f"repos/{repo_id}/snapshots/{commit_hash}/{settings_hash}/"
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=1000
            )
            
            artifacts = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    if key.endswith('.json'):
                        # Parse artifact info from key
                        parts = key.split('/')
                        if len(parts) >= 6:
                            kind_version = parts[-1].replace('.json', '')
                            if '.v' in kind_version:
                                kind, version_str = kind_version.split('.v')
                                try:
                                    version = int(version_str)
                                    artifacts.append({
                                        'kind': kind,
                                        'version': version,
                                        'uri': f"s3://{self.bucket}/{key}",
                                        'bytes': obj['Size'],
                                        'createdAt': obj['LastModified'].isoformat()
                                    })
                                except ValueError:
                                    continue
            
            # Sort by kind and version
            artifacts.sort(key=lambda x: (x['kind'], x['version']))
            return artifacts
            
        except ClientError as e:
            logger.error(f"Failed to list artifacts: {e}")
            raise StorageError(f"Failed to list artifacts: {e}")

# Global storage instance
_storage_instance: Optional[ArtifactStorage] = None

def get_storage() -> ArtifactStorage:
    """Get the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ArtifactStorage()
    return _storage_instance

def write_versioned_artifact(snapshot_id: str, kind: str, content_bytes: bytes, *, 
                           schema_version: int = 1, generator_version: str = "1.0.0",
                           repo_id: str = None, commit_hash: str = None, 
                           settings_hash: str = None) -> Dict[str, Any]:
    """Convenience function for writing versioned artifacts."""
    storage = get_storage()
    return storage.write_versioned_artifact(
        snapshot_id, kind, content_bytes,
        schema_version=schema_version,
        generator_version=generator_version,
        repo_id=repo_id,
        commit_hash=commit_hash,
        settings_hash=settings_hash
    )

def presign(uri: str, ttl_seconds: int = 600) -> str:
    """Convenience function for generating presigned URLs."""
    storage = get_storage()
    return storage.presign(uri, ttl_seconds)
