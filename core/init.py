"""
Simplified initialization module for project entry points.
Consolidates common initialization logic.
"""

import sys
import os
from pathlib import Path
from typing import Optional

# Ensure UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        # Python < 3.7 or reconfigure not available
        pass

def safe_print(message: str) -> None:
    """Safely print message, handling encoding issues"""
    try:
        print(message)
    except UnicodeEncodeError:
        # Fallback: replace problematic characters
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        print(safe_message)


def setup_project_path(file_path: Optional[str] = None) -> Path:
    """
    Set up Python path by adding project root to sys.path.
    Simplified version that handles common cases.
    
    Args:
        file_path: Path to the file calling this function (usually __file__)
    
    Returns:
        Path object to project root
    """
    if file_path is None:
        file_path = __file__
    
    current_file = Path(file_path).resolve()
    project_root = current_file.parent
    
    # For entry points at project root, project_root is already correct
    # For files in subdirectories, go up to project root
    # Check if we're in a subdirectory that indicates we need to go up
    if project_root.name in ['apps', 'core', 'database', 'Api']:
        project_root = project_root.parent
    
    project_root_str = str(project_root)
    
    # Remove if exists elsewhere to avoid conflicts
    if project_root_str in sys.path:
        sys.path.remove(project_root_str)
    
    # Add to beginning of path
    sys.path.insert(0, project_root_str)
    
    # Clear any cached wrong imports for core.path_utils
    if 'core.path_utils' in sys.modules:
        module = sys.modules['core.path_utils']
        if hasattr(module, '__file__'):
            module_path = Path(module.__file__).resolve()
            if 'managers' in str(module_path):
                del sys.modules['core.path_utils']
                if 'core' in sys.modules and hasattr(sys.modules['core'], 'path_utils'):
                    delattr(sys.modules['core'], 'path_utils')
    
    return project_root


def initialize_settings(project_root: Path) -> None:
    """
    Initialize unified settings with project root.
    
    Args:
        project_root: Path to project root
    """
    try:
        from settings import get_settings, ensure_settings_file_exists
        settings = get_settings()
        if settings.project_root is None:
            settings.set_project_root(project_root)
        
        settings_file = ensure_settings_file_exists()
        settings.reload_from_file()
        
        # Initialize resource coordinator
        try:
            from core.resource_coordinator import (
                get_resource_coordinator,
                get_safe_worker_count,
                get_safe_db_pool_size
            )
            coordinator = get_resource_coordinator()
            
            # Apply safe resource limits
            requested_workers = settings.processing.max_workers
            safe_workers = get_safe_worker_count(requested_workers)
            if safe_workers != requested_workers:
                settings.processing.max_workers = safe_workers
                safe_print(f"[WARNING] Worker count adjusted from {requested_workers} to {safe_workers}")
            
            requested_db_pool = settings.database.pool_max_conn
            safe_db_pool = get_safe_db_pool_size(requested_db_pool)
            if safe_db_pool != requested_db_pool:
                settings.database.pool_max_conn = safe_db_pool
                safe_print(f"[WARNING] DB pool size adjusted from {requested_db_pool} to {safe_db_pool}")
            
            status = coordinator.get_resource_status()
            safe_print(f"[OK] Resource Coordinator active - {status['running_instances']['total']} instance(s)")
        except Exception as e:
            safe_print(f"[WARNING] Resource coordinator warning: {e}")
        
        processing_timeout = getattr(settings.processing, 'file_processing_timeout', 1200)
        safe_print(f"[OK] Settings initialized - File processing timeout: {processing_timeout}s")
    except Exception as e:
        safe_print(f"[WARNING] Settings initialization warning: {e}")


def initialize_database_config() -> None:
    """Load saved database configuration if available."""
    try:
        from settings.config import load_database_config_from_file
        load_database_config_from_file()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Database config not found (using defaults): {e}")


def initialize_system() -> None:
    """Initialize system on startup."""
    try:
        from core.initialization import ensure_system_initialized
        ensure_system_initialized()
        safe_print("[OK] System initialization completed")
    except Exception as e:
        safe_print(f"[WARNING] System initialization warning: {e}")

