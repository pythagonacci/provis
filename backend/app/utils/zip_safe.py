"""
Secure zip extraction with protection against zip-slip attacks and resource exhaustion.
"""
import os
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import Iterator, Tuple
import shutil

logger = logging.getLogger(__name__)

class ZipExtractionError(Exception):
    """Zip extraction related errors."""
    pass

class SecureZipExtractor:
    """Secure zip extractor with comprehensive safety checks."""
    
    def __init__(self, max_entries: int = 60000, max_depth: int = 20, 
                 max_uncompressed_bytes: int = 1024 * 1024 * 1024,  # 1GB
                 max_compression_ratio: int = 200):
        self.max_entries = max_entries
        self.max_depth = max_depth
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.max_compression_ratio = max_compression_ratio
        
        logger.info(f"Initialized secure zip extractor: max_entries={max_entries}, "
                   f"max_depth={max_depth}, max_uncompressed_bytes={max_uncompressed_bytes}, "
                   f"max_compression_ratio={max_compression_ratio}")
    
    def _validate_zip_entry(self, zip_info: zipfile.ZipInfo, total_uncompressed: int) -> None:
        """
        Validate a single zip entry for security and resource limits.
        
        Args:
            zip_info: ZipInfo object for the entry
            total_uncompressed: Total uncompressed bytes processed so far
        
        Raises:
            ZipExtractionError: If entry is invalid or unsafe
        """
        # Check file size
        if zip_info.file_size > self.max_uncompressed_bytes:
            raise ZipExtractionError(f"File {zip_info.filename} too large: {zip_info.file_size} bytes")
        
        # Check total uncompressed size
        if total_uncompressed + zip_info.file_size > self.max_uncompressed_bytes:
            raise ZipExtractionError(f"Total uncompressed size would exceed limit: "
                                   f"{total_uncompressed + zip_info.file_size} bytes")
        
        # Check compression ratio
        if zip_info.compress_size > 0:
            ratio = zip_info.file_size / zip_info.compress_size
            if ratio > self.max_compression_ratio:
                raise ZipExtractionError(f"Compression ratio too high for {zip_info.filename}: {ratio}")
        
        # Check path depth
        path_parts = Path(zip_info.filename).parts
        if len(path_parts) > self.max_depth:
            raise ZipExtractionError(f"Path too deep for {zip_info.filename}: {len(path_parts)} levels")
        
        # Check for path traversal
        if self._is_unsafe_path(zip_info.filename):
            raise ZipExtractionError(f"Unsafe path detected: {zip_info.filename}")
    
    def _is_unsafe_path(self, path: str) -> bool:
        """
        Check if a path is unsafe (contains traversal or absolute paths).
        
        Args:
            path: Path to check
        
        Returns:
            True if path is unsafe
        """
        # Normalize the path
        normalized = os.path.normpath(path)
        
        # Check for absolute paths
        if os.path.isabs(normalized):
            return True
        
        # Check for path traversal
        if '..' in normalized or normalized.startswith('/'):
            return True
        
        # Check for Windows drive letters
        if len(normalized) >= 2 and normalized[1] == ':':
            return True
        
        # Check for reserved names (Windows)
        reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                         'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                         'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
        
        path_parts = Path(normalized).parts
        for part in path_parts:
            if part.upper() in reserved_names:
                return True
        
        return False
    
    def _validate_zip_file(self, zip_path: Path) -> None:
        """
        Validate the entire zip file before extraction.
        
        Args:
            zip_path: Path to the zip file
        
        Raises:
            ZipExtractionError: If zip file is invalid or unsafe
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Check number of entries
                if len(zip_file.infolist()) > self.max_entries:
                    raise ZipExtractionError(f"Too many entries in zip: {len(zip_file.infolist())}")
                
                # Validate each entry
                total_uncompressed = 0
                for zip_info in zip_file.infolist():
                    self._validate_zip_entry(zip_info, total_uncompressed)
                    total_uncompressed += zip_info.file_size
                
                logger.info(f"Zip file validation passed: {len(zip_file.infolist())} entries, "
                           f"{total_uncompressed} bytes uncompressed")
                
        except zipfile.BadZipFile as e:
            raise ZipExtractionError(f"Invalid zip file: {e}")
        except Exception as e:
            raise ZipExtractionError(f"Failed to validate zip file: {e}")
    
    def extract_to_temp(self, zip_path: Path) -> Path:
        """
        Extract zip file to a temporary directory with security checks.
        
        Args:
            zip_path: Path to the zip file
        
        Returns:
            Path to the temporary extraction directory
        
        Raises:
            ZipExtractionError: If extraction fails or is unsafe
        """
        # Validate zip file first
        self._validate_zip_file(zip_path)
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="provis_extract_")
        temp_path = Path(temp_dir)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                for zip_info in zip_file.infolist():
                    # Double-check each entry during extraction
                    if self._is_unsafe_path(zip_info.filename):
                        raise ZipExtractionError(f"Unsafe path during extraction: {zip_info.filename}")
                    
                    # Extract the file
                    target_path = temp_path / zip_info.filename
                    
                    # Ensure target is within temp directory
                    try:
                        target_path.resolve().relative_to(temp_path.resolve())
                    except ValueError:
                        raise ZipExtractionError(f"Path outside extraction directory: {zip_info.filename}")
                    
                    # Create parent directories
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Extract file
                    if zip_info.is_dir():
                        target_path.mkdir(exist_ok=True)
                    else:
                        with zip_file.open(zip_info) as source, open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)
            
            logger.info(f"Successfully extracted zip to {temp_path}")
            return temp_path
            
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_path, ignore_errors=True)
            raise ZipExtractionError(f"Failed to extract zip: {e}")
    
    def cleanup_temp(self, temp_path: Path) -> None:
        """
        Clean up temporary extraction directory.
        
        Args:
            temp_path: Path to the temporary directory
        """
        try:
            shutil.rmtree(temp_path)
            logger.debug(f"Cleaned up temporary directory: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_path}: {e}")

# Global extractor instance
_extractor_instance: Optional[SecureZipExtractor] = None

def get_extractor() -> SecureZipExtractor:
    """Get the global secure zip extractor instance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = SecureZipExtractor()
    return _extractor_instance

def extract_zip_safely(zip_path: Path) -> Path:
    """Convenience function for safe zip extraction."""
    extractor = get_extractor()
    return extractor.extract_to_temp(zip_path)

def cleanup_extraction(temp_path: Path) -> None:
    """Convenience function for cleaning up extraction."""
    extractor = get_extractor()
    extractor.cleanup_temp(temp_path)
