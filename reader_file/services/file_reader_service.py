"""
File Reader Service - Orchestrates all file readers
Aligned with database design principles (similar to ContentDBService)

This service manages all file readers and routes files to the appropriate reader
based on file extension, following the same design pattern as the database layer.
"""

import os
import logging
from typing import Dict, Any, Optional, Set, List
from pathlib import Path

from ..readers.base_reader import BaseReader
from ..readers.read_remaining import RemainingFileReader
from ..readers.read_archive import ArchiveFileReader
from ..readers.read_office import OfficeFileReader
from ..readers.read_pdf import PDFFileReader
from ..readers.read_img_fast import ImageFileReader
from ..readers.read_email import EmailFileReader
from ..readers.read_audio import AudioFileReader
from ..readers.read_video import VideoFileReader
from ..readers.read_ebook import EbookFileReader
from ..readers.read_database import DatabaseFileReader

logger = logging.getLogger(__name__)


class FileReaderService:
    """
    Service class that orchestrates all file readers.
    
    Follows database design principles (similar to ContentDBService):
    - Manages all reader instances
    - Routes files to appropriate readers
    - Provides unified interface
    - Consistent error handling
    - Resource management
    """
    
    def __init__(self):
        """Initialize service and all reader instances"""
        self._init_readers()
        self._build_extension_map()
    
    def _init_readers(self):
        """Initialize all reader instances"""
        # Initialize all readers (similar to ContentDBService._init_repositories)
        self.remaining_reader = RemainingFileReader()
        self.archive_reader = ArchiveFileReader()
        self.office_reader = OfficeFileReader()
        self.pdf_reader = PDFFileReader()
        self.image_reader = ImageFileReader()
        self.email_reader = EmailFileReader()
        self.audio_reader = AudioFileReader()
        self.video_reader = VideoFileReader()
        self.ebook_reader = EbookFileReader()
        self.database_reader = DatabaseFileReader()
        
        # Store all readers in a list for iteration
        self._readers: List[BaseReader] = [
            self.remaining_reader,
            self.archive_reader,
            self.office_reader,
            self.pdf_reader,
            self.image_reader,
            self.email_reader,
            self.audio_reader,
            self.video_reader,
            self.ebook_reader,
            self.database_reader,
        ]
    
    def _build_extension_map(self):
        """Build a map of extensions to readers for fast lookup"""
        self._extension_map: Dict[str, BaseReader] = {}
        
        for reader in self._readers:
            extensions = reader.get_supported_extensions()
            for ext in extensions:
                # Handle conflicts - first reader wins
                if ext not in self._extension_map:
                    self._extension_map[ext] = reader
    
    def get_reader_for_extension(self, extension: str) -> Optional[BaseReader]:
        """
        Get the appropriate reader for a file extension.
        
        Args:
            extension: File extension (e.g., '.pdf', '.docx')
        
        Returns:
            BaseReader instance or None if no reader supports the extension
        """
        extension = extension.lower()
        if not extension.startswith('.'):
            extension = '.' + extension
        
        return self._extension_map.get(extension)
    
    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read a file using the appropriate reader.
        
        Args:
            file_info: Dictionary containing file information with 'path' and 'extension' keys
        
        Returns:
            Dictionary with extracted content or None on error
        """
        # Validate file_info
        if not file_info or not isinstance(file_info, dict):
            logger.error("Invalid file_info: must be a non-empty dictionary")
            return None
        
        file_path = file_info.get("path")
        extension = file_info.get("extension", "")
        
        if not file_path:
            logger.error("file_info must contain 'path' key")
            return None
        
        # Get extension from path if not provided
        if not extension:
            extension = os.path.splitext(file_path)[1]
        
        # Find appropriate reader
        reader = self.get_reader_for_extension(extension)
        
        if not reader:
            logger.warning(f"No reader found for extension: {extension} (file: {file_path})")
            return {
                "error": f"Unsupported file type: {extension}",
                "path": file_path
            }
        
        # Use reader to read file
        try:
            return reader.read_file(file_info)
        except Exception as e:
            logger.error(f"Error reading file {file_path} with {reader.__class__.__name__}: {e}")
            return {
                "error": str(e),
                "path": file_path
            }
    
    def get_supported_extensions(self) -> Set[str]:
        """
        Get all supported file extensions across all readers.
        
        Returns:
            Set of all supported file extensions
        """
        all_extensions = set()
        for reader in self._readers:
            all_extensions.update(reader.get_supported_extensions())
        return all_extensions
    
    def is_supported(self, extension: str) -> bool:
        """
        Check if a file extension is supported.
        
        Args:
            extension: File extension to check
        
        Returns:
            True if extension is supported, False otherwise
        """
        extension = extension.lower()
        if not extension.startswith('.'):
            extension = '.' + extension
        return extension in self._extension_map
    
    def get_reader_info(self) -> Dict[str, Any]:
        """
        Get information about all registered readers.
        
        Returns:
            Dictionary with reader information
        """
        info = {
            "total_readers": len(self._readers),
            "total_extensions": len(self._extension_map),
            "readers": []
        }
        
        for reader in self._readers:
            extensions = reader.get_supported_extensions()
            info["readers"].append({
                "name": reader.__class__.__name__,
                "supported_extensions": sorted(list(extensions)),
                "extension_count": len(extensions)
            })
        
        return info


# Create singleton instance for backward compatibility
_file_reader_service = FileReaderService()


def get_file_reader_service() -> FileReaderService:
    """Get the singleton FileReaderService instance"""
    return _file_reader_service
