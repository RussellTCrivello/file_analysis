"""
Database configuration management - Backward Compatibility Wrapper
This module provides backward compatibility while using the unified settings system.

All functionality is provided by settings.config as the single source of truth.
"""
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """
    Database configuration dataclass - Backward compatibility wrapper.
    
    This class now uses the unified settings system from settings.config.
    All database configuration should go through the unified settings system.
    """
    dbname: str
    user: str
    password: str
    host: str
    port: int
    min_connections: int = 1
    max_connections: int = 20
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """
        Create configuration from unified settings system.
        
        This method uses the unified settings system as the single source of truth.
        Environment variables are used as fallback only.
        """
        try:
            # Use unified settings system
            from settings import get_database_config
            db_config = get_database_config()
            
            # Apply safe pool size from resource coordinator if available
            try:
                from core.resource_coordinator import get_safe_db_pool_size
                safe_max_conn = get_safe_db_pool_size(db_config.pool_max_conn)
                max_connections = safe_max_conn
                if safe_max_conn != db_config.pool_max_conn:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"DB pool size adjusted by resource coordinator: {db_config.pool_max_conn} -> {safe_max_conn}")
            except Exception as e:
                # If resource coordinator not available, use settings value
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Resource coordinator not available, using settings pool size: {e}")
                max_connections = db_config.pool_max_conn
            
            return cls(
                dbname=db_config.database,
                user=db_config.user,
                password=db_config.password or os.getenv('DB_PASSWORD', ''),
                host=db_config.host,
                port=db_config.port,
                min_connections=db_config.pool_min_conn,
                max_connections=max_connections
            )
        except Exception as e:
            # Fallback to environment variables if settings not available
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not load database config from unified settings: {e}, using environment variables")
            
            return cls(
                dbname=os.getenv('DB_NAME', 'analysis'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', ''),
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                min_connections=int(os.getenv('DB_MIN_CONNECTIONS', '1')),
                max_connections=int(os.getenv('DB_MAX_CONNECTIONS', '20'))
            )
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'DatabaseConfig':
        """Create configuration from dictionary."""
        return cls(**config_dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for psycopg2 connection."""
        return {
            'dbname': self.dbname,
            'user': self.user,
            'password': self.password,
            'host': self.host,
            'port': self.port
        }
