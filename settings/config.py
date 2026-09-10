"""
Database Configuration Module
File: settings/config.py

Centralized database connection configuration and utilities
"""

from typing import Dict, Optional
from pathlib import Path
import json
import logging
import os

from .settings_adapter import get_settings

def get_database_config():
    """Get database configuration from settings"""
    settings = get_settings()
    return settings.database

logger = logging.getLogger(__name__)


def get_db_config() -> Dict[str, any]:
    """
    Get database configuration from centralized settings system.

    ARCH-02 precedence: environment variables override the persisted
    settings file AT READ TIME, so a stale cached settings object can never
    override a deployment's environment.
    """
    db_config = get_database_config()
    d = db_config.to_dict_full()
    d["host"] = os.environ.get("DB_HOST", d["host"])
    d["port"] = int(os.environ.get("DB_PORT", d["port"]))
    d["database"] = os.environ.get("DB_NAME", d["database"])
    d["user"] = os.environ.get("DB_USER", d["user"])
    if os.environ.get("DB_PASSWORD") is not None:
        d["password"] = os.environ["DB_PASSWORD"]
    return d


def get_connection_string() -> str:
    """
    Get PostgreSQL connection string
    
    Returns:
        Connection string in format: postgresql://user:pass@host:port/database
    """
    db_config = get_database_config()
    return f"postgresql://{db_config.user}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.database}"


# Connection pool settings (from centralized config)
# These constants are evaluated at import time from centralized config
_db_config = get_database_config()

# Export constants for backward compatibility
POOL_MIN_CONN = _db_config.pool_min_conn
POOL_MAX_CONN = _db_config.pool_max_conn
POOL_TIMEOUT = _db_config.pool_timeout
QUERY_TIMEOUT = _db_config.query_timeout
BATCH_SIZE = _db_config.batch_size
CHUNK_SIZE = _db_config.chunk_size


# Backward compatibility: AppConfig
class AppConfig:
    """
    AppConfig for backward compatibility.
    Now uses unified settings internally.
    """
    
    def __init__(self):
        settings = get_settings()
        self.processing = settings.processing
        self.storage = settings.storage
        self.database = settings.database
        self.log_level = settings.system.log_level
        self.log_file = settings.system.log_file
        self.action_logging_enabled = settings.system.action_logging_enabled
        self.project_root = settings.project_root
        self.uploads_dir = settings.uploads_dir
        self.logs_dir = settings.logs_dir
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Load configuration from environment variables"""
        return cls()
    
    def set_project_root(self, root_path):
        """Set project root and update dependent paths"""
        settings = get_settings()
        settings.set_project_root(root_path)
        self.project_root = settings.project_root
        self.uploads_dir = settings.uploads_dir
        self.logs_dir = settings.logs_dir


# Global configuration instance (backward compatibility)
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    Get the global configuration instance (backward compatibility).
    
    Returns:
        AppConfig instance
    """
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def set_config(config: AppConfig):
    """
    Set the global configuration instance (backward compatibility).
    
    Args:
        config: AppConfig instance to use
    """
    global _config
    _config = config
    settings = get_settings()
    if config.project_root:
        settings.set_project_root(config.project_root)


def reset_config():
    """Reset configuration to defaults (useful for testing)"""
    global _config
    _config = None
    from .settings_adapter import get_settings
    # Reset is handled by settings manager


def load_database_config_from_file(config_path=None) -> bool:
    """
    Load database configuration from a file.

    Uses the SettingsManager's validated set path rather than directly
    mutating database config attributes.

    Args:
        config_path: Path to config file (defaults to checking multiple locations)

    Returns:
        True if config was loaded successfully, False otherwise
    """
    settings = get_settings()

    if config_path is None:
        # Check multiple possible locations
        if settings.project_root:
            project_root = settings.project_root
            if project_root.name == 'settings':
                project_root = project_root.parent
        else:
            current_file = Path(__file__).resolve()
            if current_file.parent.name == 'settings':
                project_root = current_file.parent.parent
            else:
                project_root = current_file.parent.parent

        possible_paths = [
            project_root / 'data' / '.db_config.json',
            project_root / '.db_config.json',
        ]

        # Try each path until we find one that exists
        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break

        if config_path is None:
            logger.debug("Database config file not found in any of the checked locations")
            return False
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return False

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Use the validated set_setting path
        for key in ['host', 'port', 'database', 'user', 'password',
                     'pool_min_conn', 'pool_max_conn', 'pool_timeout',
                     'query_timeout', 'batch_size', 'chunk_size']:
            val = config_data.get(key)
            if val is not None:
                settings.set_setting(f'database.{key}', val)

        # Sync to environment variables
        db = settings.database
        os.environ['DB_HOST'] = str(db.host)
        os.environ['DB_PORT'] = str(db.port)
        os.environ['DB_NAME'] = str(db.database)
        os.environ['DB_USER'] = str(db.user)
        if db.password:
            os.environ['DB_PASSWORD'] = str(db.password)

        logger.info(f"Database configuration loaded from {config_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to load database configuration: {e}")
        return False


def invalidate_database_connections():
    """
    Invalidate all database connections across the application.
    This forces all DatabaseHub instances to reconnect with new settings.
    """
    # This is a placeholder - actual invalidation would be handled by DatabaseHub
    # if it implements connection pooling with invalidation
    logger.debug("Database connection invalidation requested (no-op in current implementation)")

