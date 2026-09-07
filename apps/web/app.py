"""
PostgreSQL Flask Web Application - MODERNIZED
Fully integrated with modern processing pipeline, monitoring, and error handling
REFACTORED: Routes split into separate modules
"""

from flask import Flask, render_template
from flask_babel import Babel
import os
import sys
from pathlib import Path
import logging
import warnings

# Suppress common ML library warnings
warnings.filterwarnings("ignore", message=".*Using CPU.*Note: This module is much faster with a GPU.*")
warnings.filterwarnings("ignore", message=".*pin_memory.*argument is set as true but no accelerator is found.*")
warnings.filterwarnings("ignore", category=UserWarning, module="torch.utils.data.dataloader")
# Suppress EasyOCR GPU warnings
warnings.filterwarnings("ignore", message=".*GPU.*")
# Suppress all UserWarnings from torch
warnings.filterwarnings("ignore", category=UserWarning)

# Set environment variables to suppress library-level warnings
os.environ['PYTHONWARNINGS'] = 'ignore'
# Suppress PyTorch warnings about pin_memory
os.environ['TORCH_WARN'] = '0'

# Add project root to path for modern imports
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Add web app directory to path for Api imports
web_app_dir = str(Path(__file__).parent)
if web_app_dir not in sys.path:
    sys.path.insert(0, web_app_dir)


from core.monitoring.monitor import PerformanceMonitor

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_compress import Compress
from functools import wraps
from flask import make_response, request
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app with modern config
# Point to templates and static folders at project root
template_dir = os.path.join(project_root, 'templates')
static_dir = os.path.join(project_root, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)


# Configure Flask-Babel for internationalization
# RTL languages: ar, fa, he, ur
app.config['LANGUAGES'] = {
    'en': 'English',
    'ar': 'العربية',  # Arabic (RTL)
    'fa': 'فارسی',  # Persian/Farsi (RTL)
    'he': 'עברית',  # Hebrew (RTL)
}
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'UTC'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(project_root, 'translations')

# Define locale selector function
def get_locale():
    """Get the locale/language from session (user choice), system settings, or browser preference"""
    from flask import session, request
    # PRIORITY 1: Check session first (user's explicit choice takes precedence)
    # This ensures that when user switches language, it doesn't get overridden
    if 'language' in session:
        session_lang = session.get('language')
        if session_lang and session_lang in app.config['LANGUAGES']:
            return session_lang
    
    # PRIORITY 2: Check system settings (persistent across restarts)
    if 'SETTINGS' in app.config and app.config['SETTINGS']:
        try:
            system_config = app.config['SETTINGS'].get_system_config()
            system_language = system_config.get('language', 'en')
            if system_language in app.config['LANGUAGES']:
                # Sync session with system setting for consistency (only if session not set)
                if 'language' not in session:
                    session['language'] = system_language
                return system_language
        except Exception as e:
            # Settings error is non-critical - fall through to browser preference
            logger.debug(f"Could not get language from settings: {e}, using browser preference")
    
    # PRIORITY 3: Check browser's Accept-Language header (but only if no explicit choice)
    browser_lang = request.accept_languages.best_match(app.config['LANGUAGES'].keys())
    if browser_lang:
        # Only use browser language if session doesn't have an explicit choice
        if 'language' not in session:
            return browser_lang
    
    # PRIORITY 4: Default fallback
    return app.config['BABEL_DEFAULT_LOCALE']

# Initialize Babel with locale selector (Flask-Babel 3.0+)
babel = Babel(app, locale_selector=get_locale)

# Set up upload folder from unified settings
from settings import get_settings
settings = get_settings()
if settings.uploads_dir:
    upload_folder = str(settings.uploads_dir)
else:
    upload_folder = os.path.join(project_root, 'uploads')
    # Set it in settings for future use
    if settings.project_root is None:
        settings.set_project_root(project_root)
app.config['UPLOAD_FOLDER'] = upload_folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logger.info("✅ Web app using modern database connection manager")

from core.monitoring.monitor import get_monitor, start_monitoring
web_monitor = start_monitoring()  # Uses global singleton
logger.info("✅ Performance monitoring started for web app")

app.config['PERFORMANCE_MONITOR'] = web_monitor

try:
    from settings import get_settings
    settings = get_settings()
    app.config['SETTINGS'] = settings
    
    # Apply system settings to Flask app
    system_config = settings.get_system_config()
    app.config['BABEL_DEFAULT_LOCALE'] = system_config.get('language', 'en')
    app.config['BABEL_DEFAULT_TIMEZONE'] = system_config.get('timezone', 'UTC')
    
    logger.info("✅ Settings manager initialized at system level")
    logger.info(f"   Language: {system_config.get('language', 'en')}")
    logger.info(f"   Timezone: {system_config.get('timezone', 'UTC')}")
except Exception as e:
    logger.warning(f"⚠️  Could not initialize settings manager: {e}")
    app.config['SETTINGS'] = None

try:
    from core.monitoring.notification_service import get_notification_service
    notification_service = get_notification_service()
    app.config['NOTIFICATION_SERVICE'] = notification_service
    logger.info("✅ Notification service initialized at system level")
except Exception as e:
    logger.warning(f"⚠️  Could not initialize notification service: {e}")
    app.config['NOTIFICATION_SERVICE'] = None

# Configure SECRET_KEY for CSRF protection and session management
# Priority: 1) Environment variable, 2) Persistent file, 3) Generate new and save
import secrets
_secret_key_file = Path(project_root) / '.flask_secret_key'

def get_or_create_secret_key():
    """Get SECRET_KEY from environment, file, or generate a new one"""
    # First, try environment variable
    env_key = os.environ.get('FLASK_SECRET_KEY')
    if env_key:
        logger.info("✅ SECRET_KEY loaded from environment variable")
        return env_key.strip()
    
    # Second, try to load from persistent file
    if _secret_key_file.exists():
        try:
            with open(_secret_key_file, 'r') as f:
                key = f.read().strip()
            if key and len(key) >= 32:  # Ensure it's a valid key
                logger.info("✅ SECRET_KEY loaded from persistent file")
                return key
            else:
                logger.warning("⚠️  Invalid SECRET_KEY in file, generating new one")
        except Exception as e:
            logger.warning(f"⚠️  Could not read SECRET_KEY file: {e}, generating new one")
    
    # Third, generate a new secure key and save it
    new_key = secrets.token_hex(32)
    try:
        # Ensure the directory exists
        _secret_key_file.parent.mkdir(parents=True, exist_ok=True)
        # Save with restricted permissions (owner read/write only)
        with open(_secret_key_file, 'w') as f:
            f.write(new_key)
        # On Unix systems, restrict file permissions (Windows will ignore this)
        try:
            os.chmod(_secret_key_file, 0o600)
        except (AttributeError, OSError) as chmod_error:
            # Windows doesn't support chmod the same way - this is expected
            logger.debug(f"Could not set file permissions (expected on Windows): {chmod_error}")
        logger.info("✅ SECRET_KEY generated and saved to persistent file")
    except Exception as e:
        logger.warning(f"⚠️  Could not save SECRET_KEY to file: {e}, using in-memory key")
    
    return new_key

app.config['SECRET_KEY'] = get_or_create_secret_key()

# Verify SECRET_KEY is set
if not app.config.get('SECRET_KEY'):
    raise RuntimeError("SECRET_KEY is required but was not set!")
logger.info(f"✅ SECRET_KEY configured (length: {len(app.config['SECRET_KEY'])})")

# Initialize session configuration
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'





csrf = CSRFProtect(app)
logger.info("✅ CSRF protection enabled")

# Enable gzip compression for all responses
compress = Compress(app)
logger.info("✅ Gzip compression enabled")

# Add response caching and performance headers
@app.after_request
def add_performance_headers(response):
    """Add performance and caching headers to all responses"""
    # Cache static assets for 1 year
    if request.endpoint and 'static' in request.endpoint:
        response.cache_control.max_age = 31536000
        response.cache_control.public = True
        response.cache_control.immutable = True
    # Cache API responses for 5 minutes (can be overridden per route)
    elif request.path.startswith('/api/'):
        if not response.cache_control.max_age:
            response.cache_control.max_age = 300
            response.cache_control.public = False
    # HTML pages - no cache by default
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
    
    # Performance headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

# Request timing middleware
@app.before_request
def before_request():
    """Track request timing"""
    request.start_time = time.time()

@app.after_request
def after_request(response):
    """Log slow requests"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        if duration > 1.0:  # Log requests slower than 1 second
            logger.warning(f"⚠️ SLOW REQUEST ({duration:.2f}s): {request.method} {request.path}")
        # Add timing header
        response.headers['X-Response-Time'] = f"{duration:.3f}"
    return response

# Global error handler
@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler that records errors to monitoring"""
    try:
        from Hdg_Err_Ex_Log import handle_error, ErrorCategory, ErrorSeverity, record_error_to_monitor as record_error
        
        # Determine category and severity
        category = ErrorCategory.UNKNOWN
        severity = ErrorSeverity.MEDIUM
        
        # Check if it's a database error
        error_str = str(e).lower()
        if 'database' in error_str or 'connection' in error_str:
            category = ErrorCategory.DATABASE_CONNECTION
            severity = ErrorSeverity.HIGH
        elif 'file' in error_str or 'path' in error_str:
            category = ErrorCategory.FILE_PROCESSING
        elif 'validation' in error_str:
            category = ErrorCategory.VALIDATION
        
        context = {
            'request_path': request.path,
            'request_method': request.method,
            'request_url': request.url
        }
        
        # Handle error with logging
        handle_error(e, category=category, severity=severity, context=context)
        
        # Record to monitoring
        record_error(
            e,
            category=category.value,
            severity=severity.value,
            context=context,
            request_id=request.headers.get('X-Request-ID')
        )
    except Exception as monitor_error:
        # Don't fail if error monitoring fails
        logger.error(f"Error in global exception handler: {monitor_error}")
    
    # Return error response
    from flask import jsonify
    return jsonify({
        'error': str(e),
        'type': type(e).__name__
    }), 500

# Register setup routes FIRST - before any other routes
# This ensures setup page is shown before database connections are attempted
from Api.routes.setup import register_setup_routes, setup_bp
register_setup_routes(app)
logger.info("✅ Setup routes registered (first)")

# Exempt setup routes from CSRF (one-time setup before system is initialized)
try:
    csrf.exempt(setup_bp)
    logger.info("✅ Setup routes exempted from CSRF protection")
except Exception as e:
    logger.debug(f"Could not exempt setup routes from CSRF: {e}")

from Api.blueprints.paths import paths_bp
app.register_blueprint(paths_bp)
from Api.blueprints.analytics import analytics_bp
app.register_blueprint(analytics_bp)
from Api.blueprints.files import files_bp
app.register_blueprint(files_bp)
from Api.blueprints.content_analysis import content_analysis_bp
app.register_blueprint(content_analysis_bp)
logger.info("✅ Content analysis API registered")

from Api.routes import register_all_routes
register_all_routes(app, babel)

from Api.routes.archives_api import archives_api_bp
app.register_blueprint(archives_api_bp)

from Api.routes.cursor_api import cursor_api_bp
app.register_blueprint(cursor_api_bp)
logger.info("✅ Cursor-based pagination API registered")

from Api.routes.concurrency import concurrency_bp
app.register_blueprint(concurrency_bp)
logger.info("✅ Concurrency monitoring dashboard registered")

# Note: Performance routes are registered via register_all_routes() above
# No need to register separately here

from Api.routes.translations import register_translation_routes
register_translation_routes(app)
logger.info("✅ Translation API routes registered")

# Register error dashboard routes
from Api.routes.error_dashboard import error_dashboard_bp
app.register_blueprint(error_dashboard_bp)
logger.info("✅ Error monitoring dashboard API registered")

# ==================== FAVICON ROUTE ====================
@app.route('/favicon.ico')
def favicon():
    """Serve favicon to prevent 404 errors"""
    # Return a simple 204 No Content response to suppress the 404
    # The actual favicon is served via SVG data URI in base.html
    from flask import Response
    return Response(status=204)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


from flask_wtf.csrf import CSRFError, generate_csrf
from flask import request, jsonify

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors - return JSON for JSON requests, HTML otherwise"""
    if request.is_json or request.content_type == 'application/json' or 'application/json' in (request.headers.get('Content-Type') or ''):
        return jsonify({'error': 'CSRF token is missing or invalid'}), 400
    # For non-JSON requests, Flask-WTF will handle it automatically
    return render_template('500.html', error=str(e)), 400

@app.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """Get CSRF token for AJAX requests"""
    return jsonify({'csrf_token': generate_csrf()})


def shutdown_handler():
    """Graceful shutdown handler"""
    logger.info("Shutting down web application...")
    web_monitor.stop()
    


if __name__ == '__main__':
    import atexit
    atexit.register(shutdown_handler)
    
    # Get debug mode from environment or default to False
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    try:
        app.run(debug=debug_mode, host='127.0.0.1', port=5000, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        shutdown_handler()
    except Exception as e:
        logger.error(f"Application error: {e}")
        shutdown_handler()
