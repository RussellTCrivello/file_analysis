"""
Archive file reader - Extract archives
Aligned with database design principles - all functions within class
Supports: ZIP, TAR, GZ, BZ2, RAR, 7Z
"""

import bz2
import gzip
import os
from typing import Dict, Any, Optional, Set
from pathlib import Path
import shutil
import tarfile
import zipfile

from core.path_utils import get_extraction_name_file

from .base_reader import BaseReader

from Hdg_Err_Ex_Log import (
    handle_error,
    ErrorCategory,
    ErrorSeverity,
    format_validation_error
)

import logging
logger = logging.getLogger(__name__)


class ArchiveFileReader(BaseReader):
    """
    Reader for archive files.
    
    Follows database design principles:
    - All functions are within the class
    - Inherits from BaseReader
    - Consistent error handling
    - Proper resource management
    """
    
    def get_supported_extensions(self) -> Set[str]:
        """Return set of supported archive extensions"""
        return {
            '.zip',
            '.tar',
            '.gz',
            '.bz2',
            '.rar',
            '.7z'
        }
    
    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read archive file and extract contents with improved error handling
        
        Args:
            file_info: Dictionary containing file information with 'path' key
        
        Returns:
            Dictionary with extraction path or error information
        """
        # Validate file info using base class method
        is_valid, error_msg = self.validate_file_info(file_info)
        if not is_valid:
            return self.create_error_result(error_msg or "Invalid file info", file_info.get("path", "unknown"))
        
        file_path = str(file_info.get("path"))
        file_lower = file_path.lower()
        
        try:
            extraction_path = None
            
            if file_lower.endswith('.zip'):
                extraction_path = self.extract_zip(file_path)
            elif file_lower.endswith('.tar') or file_lower.endswith('.tar.gz') or file_lower.endswith('.tar.bz2') or file_lower.endswith('.tar.xz'):
                extraction_path = self.extract_tar(file_path)
            elif file_lower.endswith('.gz'):
                extraction_path = self.extract_gz(file_path)
            elif file_lower.endswith('.bz2'):
                extraction_path = self.extract_bz2(file_path)
            elif file_lower.endswith('.rar'):
                extraction_path = self.extract_rar(file_path)
            elif file_lower.endswith('.7z'):
                extraction_path = self.extract_7z(file_path)
            else:
                error_msg = f"Unsupported archive type: {file_path}"
                return self.handle_read_error(ValueError(error_msg), file_path, "read_file")
            
            # STANDARDIZED: Always return dict
            if extraction_path:
                return {
                    "extraction_path": extraction_path,
                    "status": "success",
                    "archive_type": file_lower.split('.')[-1]
                }
            else:
                error_msg = "Extraction failed"
                return self.handle_read_error(Exception(error_msg), file_path, "read_file")
                
        except Exception as e:
            return self.handle_read_error(e, file_path, "read_file")
    
    def extract_zip(self, file_path):
        """Extract ZIP files"""
        extract_to = get_extraction_name_file(file_path, '.zip')
        os.makedirs(extract_to, exist_ok=True)
        
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"✓ Extracted {file_path} to {extract_to}/")
        return extract_to
    
    def extract_tar(self, file_path):
        """Extract TAR files (.tar, .tar.gz, .tar.bz2, .tar.xz)"""
        # Determine extension to use for folder name
        if file_path.endswith('.tar.gz'):
            extension = '.tar.gz'
        elif file_path.endswith('.tar.bz2'):
            extension = '.tar.bz2'
        elif file_path.endswith('.tar.xz'):
            extension = '.tar.xz'
        else:
            extension = '.tar'
        
        extract_to = get_extraction_name_file(file_path, extension)
        os.makedirs(extract_to, exist_ok=True)
        
        with tarfile.open(file_path, 'r:*') as tar_ref:
            tar_ref.extractall(extract_to)
        print(f"✓ Extracted {file_path} to {extract_to}/")
        return extract_to
    
    def extract_gz(self, file_path):
        """Extract GZ files (single file compression)"""
        extract_to = get_extraction_name_file(file_path, '.gz')
        os.makedirs(extract_to, exist_ok=True)
        
        # Output file inside the folder
        output_file = os.path.join(extract_to, Path(file_path).stem)
        
        with gzip.open(file_path, 'rb') as f_in:
            with open(output_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"✓ Extracted {file_path} to {extract_to}/")
        return extract_to
    
    def extract_bz2(self, file_path):
        """Extract BZ2 files (single file compression)"""
        extract_to = get_extraction_name_file(file_path, '.bz2')
        os.makedirs(extract_to, exist_ok=True)
        
        # Output file inside the folder
        output_file = os.path.join(extract_to, Path(file_path).stem)
        
        with bz2.open(file_path, 'rb') as f_in:
            with open(output_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"✓ Extracted {file_path} to {extract_to}/")
        return extract_to
    
    def extract_rar(self, file_path):
        """Extract RAR files (requires rarfile package and UnRAR tool)"""
        try:
            import rarfile
            
            # Set UnRAR tool path for Windows
            rarfile.UNRAR_TOOL = "unrar"
            
            # Try to find WinRAR installation
            winrar_paths = [
                r"C:\Users\SOLO\Downloads\UnRAR.exe",
                r"C:\Program Files\WinRAR\UnRAR.exe",
                r"C:\Program Files (x86)\WinRAR\UnRAR.exe"
            ]
            for path in winrar_paths:
                if os.path.exists(path):
                    rarfile.UNRAR_TOOL = path
                    break
            
        except ImportError:
            logger.warning("rarfile not installed. Install with: pip install rarfile")
            return None
        
        extract_to = get_extraction_name_file(file_path, '.rar')
        os.makedirs(extract_to, exist_ok=True)
        
        try:
            with rarfile.RarFile(file_path, 'r') as rar_ref:
                rar_ref.extractall(extract_to)
            print(f"✓ Extracted {file_path} to {extract_to}/")
            return extract_to
        except rarfile.RarCannotExec:
            logger.warning("UnRAR tool not found. Please install UnRAR:")
            logger.warning("  Linux: sudo apt-get install unrar")
            logger.warning("  Mac: brew install unrar")
            return None
        except Exception as e:
            logger.error(f"Error extracting RAR file: {str(e)}")
            return None
    
    def extract_7z(self, file_path):
        """Extract 7Z files (requires py7zr package)"""
        try:
            import py7zr
        except ImportError:
            logger.warning("py7zr not installed. Install with: pip install py7zr")
            return None
        
        extract_to = get_extraction_name_file(file_path, '.7z')
        os.makedirs(extract_to, exist_ok=True)
        
        try:
            with py7zr.SevenZipFile(file_path, 'r') as sz_ref:
                sz_ref.extractall(extract_to)
            print(f"✓ Extracted {file_path} to {extract_to}/")
            return extract_to
        except Exception as e:
            logger.error(f"Error extracting 7z file: {str(e)}")
            return None


