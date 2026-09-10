"""
Database setup routes for initial installation
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from database import (
    database_exists, create_database, create_schema,
    get_postgres_connection, get_db_connection
)
from settings import get_database_config, DatabaseConfig
from settings.config import set_config, AppConfig
import logging
import os
import psycopg2

logger = logging.getLogger(__name__)

setup_bp = Blueprint('setup', __name__)


def check_database_initialized():
    """
    Check if database is initialized.
    First checks the system initialization marker file (fastest),
    then falls back to database checks if needed.
    """
    # First check: System initialization marker file (fastest and most reliable)
    try:
        from core.initialization import is_system_initialized
        if is_system_initialized():
            logger.debug("System initialization marker found - database is initialized")
            return True
    except Exception as e:
        logger.debug(f"Could not check system initialization marker: {e}")
    
    # Second check: Try database connection and setup marker
    try:
        from database import get_db_config, database_exists
        db_config = get_db_config()
        
        # First check if database exists
        try:
            if not database_exists(db_config['database'], db_config.get('password', '')):
                logger.debug("Database does not exist")
                return False
        except Exception as e:
            logger.debug(f"Could not check if database exists: {e}")
            # If we can't check, assume it doesn't exist
            return False
        
        # Try to connect to the database
        try:
            conn = psycopg2.connect(
                dbname=db_config.get('database', 'analysis'),
                user=db_config.get('user', 'postgres'),
                password=db_config.get('password', ''),
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432)
            )
            cursor = conn.cursor()
            
            # Check if setup marker exists (most reliable indicator)
            try:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = '_setup_completed'
                """)
                setup_marker_exists = cursor.fetchone()[0] > 0
                
                if setup_marker_exists:
                    cursor.close()
                    conn.close()
                    logger.debug("Setup marker found in database - database is initialized")
                    return True
            except Exception:
                pass
            
            # Fallback: Check if any application tables exist
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name IN ('words', 'files', 'content', 'categories')
            """)
            table_count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            if table_count > 0:
                logger.debug(f"Found {table_count} application tables - database is initialized")
                return True
            
            return False
        except Exception as conn_error:
            # If connection fails, check if it's just a password issue
            # If system marker exists, assume initialized (password can be fixed in settings)
            try:
                from core.initialization import is_system_initialized
                if is_system_initialized():
                    logger.debug("System initialized but database connection failed (may need password update)")
                    return True
            except:
                pass
            
            logger.debug(f"Could not connect to database: {conn_error}")
            return False
            
    except Exception as e:
        logger.debug(f"Database check failed: {e}")
        # If system marker exists, assume initialized
        try:
            from core.initialization import is_system_initialized
            if is_system_initialized():
                return True
        except:
            pass
        return False


@setup_bp.route('/setup', methods=['GET'])
def setup_page():
    """Display database setup page"""
    # Check if already initialized
    if check_database_initialized():
        return redirect(url_for('index'))
    
    return render_template('Setup/database_setup.html')


@setup_bp.route('/api/setup/database', methods=['POST'])
def setup_database():
    """Handle database setup request - uses standardized settings"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Standardized database configuration - fixed values, no variations
        # Only password is required from user
        host = 'localhost'  # Fixed
        port = 5432  # Fixed
        user = 'postgres'  # Fixed
        database = 'analysis'  # Fixed
        password = data.get('password', '')
        
        if not password:
            return jsonify({'error': 'Database password is required'}), 400
        
        # First, try to verify if setup is truly complete by checking for critical tables
        # This allows re-setup if tables are missing (e.g., alerts table)
        setup_complete = False
        try:
            # Try to connect to check if database and critical tables exist
            conn_check = psycopg2.connect(
                dbname=database,
                user=user,
                password=password,
                host=host,
                port=port
            )
            cursor_check = conn_check.cursor()
            
            # Check if alerts table exists (required by notification service)
            cursor_check.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'alerts'
            """)
            alerts_exists = cursor_check.fetchone()[0] > 0
            
            # Check for other critical tables
            cursor_check.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('words', 'categorys', 'paths', 'contents')
            """)
            critical_tables_count = cursor_check.fetchone()[0]
            
            cursor_check.close()
            conn_check.close()
            
            # Setup is complete only if alerts table exists AND all critical tables exist
            setup_complete = alerts_exists and critical_tables_count >= 4
            
            if not setup_complete:
                logger.warning(f"Database connection successful but critical tables missing (alerts: {alerts_exists}, critical: {critical_tables_count}/4). Allowing setup to complete.")
        except psycopg2.OperationalError as e:
            # Database doesn't exist or connection failed - allow setup
            logger.info(f"Database connection failed (may not exist yet): {e}. Allowing setup.")
            setup_complete = False
        except Exception as check_error:
            # Any other error - allow setup to proceed (safer to allow than block)
            logger.warning(f"Could not verify table existence: {check_error}. Allowing setup.")
            setup_complete = False
        
        # Only block if setup is truly complete (all tables exist)
        if setup_complete:
            return jsonify({
                'error': 'Database is already initialized. Setup can only be performed once.',
                'message': 'If you need to reconfigure, please use the Settings page.'
            }), 400
        
        # Update global configuration
        db_config = DatabaseConfig(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        
        # Update the global config
        app_config = get_database_config()
        app_config.host = host
        app_config.port = port
        app_config.user = user
        app_config.password = password
        app_config.database = database
        
        # Also set environment variables for persistence
        os.environ['DB_HOST'] = host
        os.environ['DB_PORT'] = str(port)
        os.environ['DB_USER'] = user
        os.environ['DB_PASSWORD'] = password
        os.environ['DB_NAME'] = database
        
        # Save configuration to file for persistence
        try:
            from settings.config import save_database_config_to_file
            save_database_config_to_file()
        except Exception as e:
            logger.warning(f"Could not save database config to file: {e}")
        
        # Check if database exists
        db_exists = database_exists(database, password)
        database_created = False
        
        if not db_exists:
            # Create database
            logger.info(f"Creating database '{database}'...")
            if create_database(database, user, password, host, port):
                database_created = True
                logger.info(f"Database '{database}' created successfully")
            else:
                return jsonify({'error': 'Failed to create database'}), 500
        
        # Create the schema through the versioned migration bootstrap (DB-01).
        # The legacy inline DDL path was removed: it ran statements in an order
        # that violated foreign-key dependencies and broke fresh installs.
        logger.info(f"Bootstrapping schema in database '{database}'...")
        from database.bootstrap import bootstrap_database, BootstrapError
        try:
            bootstrap_report = bootstrap_database({
                'host': host, 'port': port, 'user': user,
                'password': password, 'database': database,
            })
        except BootstrapError as boot_error:
            logger.error("Schema bootstrap failed: %s", boot_error)
            return jsonify({
                'error': str(boot_error),
                'message': 'Failed to create the database schema. Check PostgreSQL settings.'
            }), 500
        
        try:
            # Mark setup as completed by creating a setup marker
            # This ensures setup only happens once
            try:
                conn = psycopg2.connect(
                    dbname=database, user=user, password=password,
                    host=host, port=port
                )
                # Ensure autocommit is enabled for this operation
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _setup_completed (
                        id SERIAL PRIMARY KEY,
                        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        host VARCHAR(255),
                        port INTEGER,
                        user_name VARCHAR(255),
                        database_name VARCHAR(255)
                    );
                """)
                # Check if setup marker already exists
                cursor.execute("SELECT COUNT(*) FROM _setup_completed")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO _setup_completed (host, port, user_name, database_name)
                        VALUES (%s, %s, %s, %s)
                    """, (host, port, user, database))
                cursor.close()
                
                # Also mark system as initialized in file system
                from core.initialization import mark_system_initialized
                mark_system_initialized()
                logger.info("✅ System marked as initialized after database setup")
            except Exception as e:
                logger.debug(f"Could not create setup marker: {e}")
        finally:
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Database setup completed successfully with standardized settings',
            'database_created': database_created,
            'database': database,
            'redirect': url_for('index'),  # Redirect to dashboard after setup
            'settings': {
                'host': host,
                'port': port,
                'user': user,
                'database': database
            }
        }), 200
        
    except Exception:
        # SEC-08: client-safe error; details logged server-side only.
        from core.errors import new_correlation_id
        logger.error("Database setup failed", exc_info=True)
        return jsonify({
            'error': 'Failed to setup database. Check your PostgreSQL connection settings.',
            'correlation_id': new_correlation_id(),
            'message': 'Failed to setup database. Please check your PostgreSQL connection settings.'
        }), 500


@setup_bp.route('/api/setup/check', methods=['GET'])
def check_setup_status():
    """Check if database is initialized"""
    try:
        initialized = check_database_initialized()
        return jsonify({
            'initialized': initialized
        }), 200
    except Exception:
        logger.error("Error checking setup status", exc_info=True)
        return jsonify({
            'initialized': False
        }), 200  # Return 200 so frontend can handle it


def register_setup_routes(app):
    """Register setup routes with the Flask app"""
    app.register_blueprint(setup_bp)
    # Note: CSRF exemption is handled in app.py after routes are registered
    
    # Add before_request handler to check database initialization
    # This MUST run before any other handlers to catch setup requirement early
    @app.before_request
    def check_database_setup():
        """Redirect to setup page if database is not initialized"""
        # Skip check for setup routes and static files
        if request.endpoint in ('setup.setup_page', 'setup.setup_database', 'setup.check_setup_status', 'static'):
            return None
        
        # Skip check for API setup endpoints
        if request.path.startswith('/api/setup/'):
            return None
        
        # Skip check for error handlers
        if request.endpoint in ('_internal_error', 'not_found'):
            return None
        
        # Check if database is initialized
        try:
            initialized = check_database_initialized()
            if not initialized:
                # Redirect to setup page - this is the first-time setup
                if request.path != '/setup' and not request.path.startswith('/static'):
                    logger.info("Database not initialized, redirecting to setup page")
                    return redirect(url_for('setup.setup_page'))
        except Exception as e:
            # If check fails (e.g., database doesn't exist), redirect to setup
            logger.debug(f"Database check failed (likely not initialized): {e}")
            if request.path != '/setup' and not request.path.startswith('/api/setup/') and not request.path.startswith('/static'):
                return redirect(url_for('setup.setup_page'))
        
        return None

