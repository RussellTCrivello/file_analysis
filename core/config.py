"""
Centralized Configuration System (Backward Compatibility Wrapper)
This module re-exports everything from settings.config for backward compatibility.

All functionality is provided by settings.config as the single source of truth.
This module exists only for backward compatibility with existing code.
"""

# Import everything from the unified settings.config module
from settings.config import (
    AppConfig,
    get_config,
    set_config,
    reset_config,
    get_db_config,
    get_connection_string,
    get_database_config,
    save_database_config_to_file,
    load_database_config_from_file,
    invalidate_database_connections,
    POOL_MIN_CONN,
    POOL_MAX_CONN,
    POOL_TIMEOUT,
    QUERY_TIMEOUT,
    BATCH_SIZE,
    CHUNK_SIZE,
)

# Re-export settings classes for backward compatibility
from settings import (
    ProcessingConfig,
    StorageConfig,
    DatabaseConfig,
    get_processing_config,
    get_storage_config,
)

# Re-export for convenience
__all__ = [
    'AppConfig',
    'ProcessingConfig',
    'StorageConfig',
    'DatabaseConfig',
    'get_config',
    'set_config',
    'reset_config',
    'get_processing_config',
    'get_storage_config',
    'get_database_config',
    'get_db_config',
    'get_connection_string',
    'save_database_config_to_file',
    'load_database_config_from_file',
    'invalidate_database_connections',
    'POOL_MIN_CONN',
    'POOL_MAX_CONN',
    'POOL_TIMEOUT',
    'QUERY_TIMEOUT',
    'BATCH_SIZE',
    'CHUNK_SIZE',
]
