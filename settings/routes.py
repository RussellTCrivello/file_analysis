"""
Settings API Routes
File: settings/routes.py

RESTful API for settings management
Enhanced with all existing system features
"""

from flask import Blueprint, request, jsonify, current_app, session
from functools import wraps
from pathlib import Path
from werkzeug.utils import secure_filename
import logging
import os
import uuid
import re

from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)

# Create blueprint
settings_bp = Blueprint('settings_api', __name__, url_prefix='/api/settings')


def handle_errors(f):
    """Decorator for consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"API error in {f.__name__}: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    return decorated_function


# ============================================================================
# GET ENDPOINTS - Read settings
# ============================================================================

@settings_bp.route('/', methods=['GET'])
@handle_errors
def get_all_settings():
    """Get all settings"""
    manager = get_settings_manager()
    
    return jsonify({
        'success': True,
        'settings': manager.export()
    })


@settings_bp.route('/<category>', methods=['GET'])
@handle_errors
def get_category_settings(category):
    """Get settings for a specific category"""
    manager = get_settings_manager()
    settings = manager.settings
    
    # Get category object
    category_obj = getattr(settings, category, None)
    if category_obj is None:
        return jsonify({
            'success': False,
            'error': f'Unknown category: {category}'
        }), 404
    
    # Convert to dict
    if hasattr(category_obj, 'to_dict'):
        data = category_obj.to_dict()
    else:
        data = vars(category_obj)
    
    return jsonify({
        'success': True,
        'category': category,
        'settings': data
    })


@settings_bp.route('/<category>/<key>', methods=['GET'])
@handle_errors
def get_single_setting(category, key):
    """Get a single setting value"""
    manager = get_settings_manager()
    full_key = f"{category}.{key}"
    value = manager.get(full_key)
    
    return jsonify({
        'success': True,
        'key': full_key,
        'value': value
    })


# ============================================================================
# POST/PUT ENDPOINTS - Update settings
# ============================================================================

@settings_bp.route('/<category>/<key>', methods=['POST', 'PUT'])
@handle_errors
def update_single_setting(category, key):
    """Update a single setting"""
    data = request.get_json() or {}
    value = data.get('value')
    
    if value is None:
        return jsonify({
            'success': False,
            'error': 'Missing "value" in request body'
        }), 400
    
    manager = get_settings_manager()
    full_key = f"{category}.{key}"
    
    # Special handling for language changes
    if category == 'system' and key == 'language':
        # Validate language code
        from flask import current_app
        languages = current_app.config.get('LANGUAGES', {})
        if value not in languages:
            return jsonify({
                'success': False,
                'error': f'Invalid language code: {value}'
            }), 400
        
        # Update app config
        current_app.config['BABEL_DEFAULT_LOCALE'] = value
        
        # Update session
        session['language'] = value
        session.permanent = True
    
    # Update setting
    success, error = manager.set(full_key, value, validate=True)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    # Save to file
    manager.save()
    
    return jsonify({
        'success': True,
        'key': full_key,
        'value': value,
        'message': f'Setting {full_key} updated successfully'
    })


@settings_bp.route('/batch', methods=['POST', 'PUT'])
@handle_errors
def batch_update_settings():
    """
    Update multiple settings at once.
    
    Request body:
    {
        "updates": {
            "system.language": "fr",
            "theme.primary_color": "#ff0000",
            "display.compact_view": true
        }
    }
    """
    data = request.get_json() or {}
    updates = data.get('updates', {})
    
    if not updates:
        return jsonify({
            'success': False,
            'error': 'No updates provided'
        }), 400
    
    manager = get_settings_manager()
    
    # Handle language changes
    if 'system.language' in updates:
        from flask import current_app
        value = updates['system.language']
        languages = current_app.config.get('LANGUAGES', {})
        if value not in languages:
            return jsonify({
                'success': False,
                'error': f'Invalid language code: {value}'
            }), 400
        current_app.config['BABEL_DEFAULT_LOCALE'] = value
        session['language'] = value
        session.permanent = True
    
    # Update all settings
    success, errors = manager.update_many(updates, validate=True)
    
    if not success:
        return jsonify({
            'success': False,
            'error': 'Some updates failed',
            'errors': errors
        }), 400
    
    # Save to file
    manager.save()
    
    return jsonify({
        'success': True,
        'updated_count': len(updates),
        'message': f'Successfully updated {len(updates)} settings'
    })


# ============================================================================
# DATABASE SETTINGS ENDPOINTS
# ============================================================================

@settings_bp.route('/database', methods=['GET'])
@handle_errors
def get_database_settings():
    """Get database settings (password not exposed)"""
    manager = get_settings_manager()
    db_config = manager.settings.database
    
    return jsonify({
        'success': True,
        'settings': db_config.to_dict()  # This excludes password
    })


@settings_bp.route('/database', methods=['POST'])
@handle_errors
def update_database_settings():
    """Update database settings"""
    data = request.get_json() or {}
    manager = get_settings_manager()
    
    # Update database config
    db_config = manager.settings.database
    
    # Update fields if provided
    if 'host' in data:
        db_config.host = str(data['host'])
    if 'port' in data:
        db_config.port = int(data['port'])
    if 'database' in data:
        db_config.database = str(data['database'])
    if 'user' in data:
        db_config.user = str(data['user'])
    if 'password' in data and data['password']:
        db_config.password = str(data['password'])
        os.environ['DB_PASSWORD'] = db_config.password
    if 'pool_min_conn' in data:
        db_config.pool_min_conn = int(data['pool_min_conn'])
    if 'pool_max_conn' in data:
        db_config.pool_max_conn = int(data['pool_max_conn'])
    if 'pool_timeout' in data:
        db_config.pool_timeout = int(data['pool_timeout'])
    if 'query_timeout' in data:
        db_config.query_timeout = int(data['query_timeout'])
    if 'batch_size' in data:
        db_config.batch_size = int(data['batch_size'])
    if 'chunk_size' in data:
        db_config.chunk_size = int(data['chunk_size'])
    
    # Update environment variables
    os.environ['DB_HOST'] = db_config.host
    os.environ['DB_PORT'] = str(db_config.port)
    os.environ['DB_USER'] = db_config.user
    os.environ['DB_NAME'] = db_config.database
    
    # Save
    manager.save()
    
    # Invalidate database connections
    try:
        from .config import invalidate_database_connections
        invalidate_database_connections()
    except ImportError:
        pass
    
    return jsonify({
        'success': True,
        'message': 'Database settings updated successfully',
        'settings': db_config.to_dict()
    })


# ============================================================================
# STORAGE SETTINGS ENDPOINTS
# ============================================================================

@settings_bp.route('/storage', methods=['GET'])
@handle_errors
def get_storage_settings():
    """Get storage settings"""
    manager = get_settings_manager()
    storage_config = manager.settings.storage
    
    return jsonify({
        'success': True,
        'settings': storage_config.to_dict()
    })


@settings_bp.route('/storage/<key>', methods=['POST'])
@handle_errors
def update_storage_setting(key):
    """Update a storage setting"""
    data = request.get_json() or {}
    value = data.get('value')
    
    if value is None:
        return jsonify({
            'success': False,
            'error': 'Missing "value" in request body'
        }), 400
    
    manager = get_settings_manager()
    full_key = f"storage.{key}"
    
    success, error = manager.set(full_key, value, validate=True)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    manager.save()
    
    return jsonify({
        'success': True,
        'key': full_key,
        'value': value,
        'message': f'Storage setting {key} updated successfully'
    })


# ============================================================================
# LOGO UPLOAD/REMOVE ENDPOINTS
# ============================================================================

@settings_bp.route('/logo/upload', methods=['POST'])
@handle_errors
def upload_logo():
    """Upload app logo"""
    if 'logo' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['logo']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico'}
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
        }), 400
    
    # Check file size (max 5MB)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    max_size = 5 * 1024 * 1024  # 5MB
    if file_size > max_size:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size: 5MB'
        }), 400
    
    # Create logos directory
    static_folder = Path(current_app.static_folder)
    logos_dir = static_folder / 'logos'
    logos_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    unique_filename = f"logo_{uuid.uuid4().hex[:8]}.{file_ext}"
    filepath = logos_dir / unique_filename
    
    # Save file
    file.save(str(filepath))
    
    # Generate URL path
    logo_url = f"/static/logos/{unique_filename}"
    
    # Update setting
    manager = get_settings_manager()
    manager.set('system.app_logo', logo_url)
    manager.set('system.app_icon', '')  # Clear icon if logo is set
    manager.save()
    
    logger.info(f"✅ Logo uploaded: {logo_url}")
    
    return jsonify({
        'success': True,
        'logo_url': logo_url,
        'message': 'Logo uploaded successfully'
    })


@settings_bp.route('/logo/remove', methods=['POST'])
@handle_errors
def remove_logo():
    """Remove app logo"""
    manager = get_settings_manager()
    current_logo = manager.get('system.app_logo', '')
    
    # Remove logo file if it exists
    if current_logo:
        try:
            logo_path = Path(current_app.static_folder) / current_logo.replace('/static/', '')
            if logo_path.exists():
                logo_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete logo file: {e}")
    
    # Clear logo setting
    manager.set('system.app_logo', '')
    manager.set('system.app_icon', 'bi-file-earmark-text')  # Restore default icon
    manager.save()
    
    logger.info("✅ Logo removed")
    
    return jsonify({
        'success': True,
        'message': 'Logo removed successfully'
    })


# ============================================================================
# INTERFACE MANAGEMENT ENDPOINTS
# ============================================================================

@settings_bp.route('/interfaces', methods=['GET'])
@handle_errors
def get_interfaces():
    """Get all interface settings"""
    manager = get_settings_manager()
    interfaces = manager.settings.interfaces
    
    # Convert to dict format
    interfaces_dict = {}
    for interface_id, config in interfaces.interfaces.items():
        interfaces_dict[interface_id] = config.to_dict()
    
    return jsonify({
        'success': True,
        'interfaces': interfaces_dict
    })


@settings_bp.route('/interfaces/<interface_id>', methods=['POST'])
@handle_errors
def toggle_interface(interface_id):
    """Toggle interface enabled/disabled"""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    
    manager = get_settings_manager()
    full_key = f"interfaces.{interface_id}.enabled"
    
    success, error = manager.set(full_key, enabled, validate=True)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    manager.save()
    
    return jsonify({
        'success': True,
        'interface_id': interface_id,
        'enabled': enabled,
        'message': f"Interface '{interface_id}' {'enabled' if enabled else 'disabled'}"
    })


@settings_bp.route('/interfaces/reset', methods=['POST'])
@handle_errors
def reset_interfaces():
    """Reset all interface settings to defaults"""
    manager = get_settings_manager()
    
    # Reset all interfaces to enabled
    for interface_id in manager.settings.interfaces.interfaces.keys():
        manager.set(f"interfaces.{interface_id}.enabled", True)
    
    manager.save()
    
    return jsonify({
        'success': True,
        'message': 'Interface settings reset to defaults'
    })


# ============================================================================
# THEME ENDPOINTS
# ============================================================================

@settings_bp.route('/theme', methods=['GET'])
@handle_errors
def get_theme_settings():
    """Get all theme settings"""
    manager = get_settings_manager()
    theme = manager.settings.theme
    
    return jsonify({
        'success': True,
        'theme': theme.to_dict()
    })


@settings_bp.route('/theme/<key>', methods=['POST'])
@handle_errors
def update_theme_setting(key):
    """Update a theme setting"""
    data = request.get_json() or {}
    value = data.get('value')
    
    if value is None:
        return jsonify({
            'success': False,
            'error': 'Missing "value" in request body'
        }), 400
    
    # Validate color format for color settings
    color_pattern = re.compile(r'^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$')
    css_value_pattern = re.compile(r'^[\d.]+(rem|px|em|%|deg|vh|vw|pt)$|^\d+$')
    
    non_color_settings = [
        'gradient_direction', 'spacing_xs', 'spacing_sm', 'spacing_md', 'spacing_lg',
        'spacing_xl', 'spacing_2xl', 'sidebar_width', 'font_size_xs', 'font_size_sm',
        'font_size_base', 'font_size_lg', 'font_size_xl', 'font_size_2xl', 'font_size_3xl',
        'font_weight_normal', 'font_weight_medium', 'font_weight_semibold', 'font_weight_bold',
        'border_radius_sm', 'border_radius_md', 'border_radius_lg', 'border_radius_xl',
        'shadow_sm', 'shadow_md', 'shadow_lg', 'shadow_xl',
        'icon_size_sm', 'icon_size_md', 'icon_size_lg', 'icon_size_xl', 'custom_css'
    ]
    
    if key in non_color_settings:
        # Validate CSS value
        if not (css_value_pattern.match(value) or value.endswith('deg') or 
                value.startswith('rgba') or value.startswith('rgb') or key == 'custom_css'):
            return jsonify({
                'success': False,
                'error': f'Invalid format for {key}. Must be a valid CSS value'
            }), 400
    else:
        # Validate color
        if not (color_pattern.match(value) or value.startswith('rgb(') or 
                value.startswith('rgba(')):
            return jsonify({
                'success': False,
                'error': f'Invalid color format for {key}. Must be hex, rgb(), or rgba()'
            }), 400
    
    manager = get_settings_manager()
    full_key = f"theme.{key}"
    
    success, error = manager.set(full_key, value, validate=False)  # Custom validation above
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    manager.save()
    
    return jsonify({
        'success': True,
        'key': full_key,
        'value': value,
        'message': f'Theme setting {key} updated successfully'
    })


@settings_bp.route('/theme/bulk', methods=['POST'])
@handle_errors
def update_theme_bulk():
    """Update multiple theme settings at once"""
    data = request.get_json() or {}
    colors = data.get('colors', {})
    
    if not colors:
        return jsonify({
            'success': False,
            'error': 'Colors object is required'
        }), 400
    
    manager = get_settings_manager()
    updates = {}
    
    for key, value in colors.items():
        updates[f"theme.{key}"] = value
    
    success, errors = manager.update_many(updates, validate=False)
    
    if not success:
        return jsonify({
            'success': False,
            'error': 'Some updates failed',
            'errors': errors
        }), 400
    
    manager.save()
    
    return jsonify({
        'success': True,
        'updated_count': len(updates),
        'message': f'Successfully updated {len(updates)} theme settings'
    })


@settings_bp.route('/theme/custom_css', methods=['GET', 'POST'])
@handle_errors
def theme_custom_css():
    """Get or update custom CSS"""
    manager = get_settings_manager()
    
    if request.method == 'GET':
        custom_css = manager.get('theme.custom_css', '')
        return jsonify({
            'success': True,
            'custom_css': custom_css
        })
    
    # POST
    data = request.get_json() or {}
    custom_css = data.get('custom_css', '')
    
    if not isinstance(custom_css, str):
        return jsonify({
            'success': False,
            'error': 'custom_css must be a string'
        }), 400
    
    # Size limit
    if len(custom_css) > 100000:
        return jsonify({
            'success': False,
            'error': 'custom_css is too large (max 100000 characters)'
        }), 400
    
    # Basic safety
    custom_css = custom_css.replace('</style>', '')
    
    manager.set('theme.custom_css', custom_css)
    manager.save()
    
    return jsonify({
        'success': True,
        'message': 'Custom CSS updated successfully'
    })


# ============================================================================
# IMPORT/EXPORT ENDPOINTS
# ============================================================================

@settings_bp.route('/export', methods=['GET'])
@handle_errors
def export_settings():
    """Export all settings as JSON"""
    manager = get_settings_manager()
    
    from datetime import datetime
    filename = f"settings_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    return jsonify({
        'success': True,
        'filename': filename,
        'settings': manager.export()
    })


@settings_bp.route('/import', methods=['POST'])
@handle_errors
def import_settings():
    """
    Import settings from JSON.
    
    Request body: Complete settings dictionary
    """
    data = request.get_json() or {}
    
    if not data:
        return jsonify({
            'success': False,
            'error': 'No settings data provided'
        }), 400
    
    manager = get_settings_manager()
    success, error = manager.import_settings(data)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    return jsonify({
        'success': True,
        'message': 'Settings imported successfully'
    })


# ============================================================================
# BACKUP/RESTORE ENDPOINTS
# ============================================================================

@settings_bp.route('/backups', methods=['GET'])
@handle_errors
def list_backups():
    """List all available backups"""
    manager = get_settings_manager()
    backups = manager.list_backups()
    
    return jsonify({
        'success': True,
        'count': len(backups),
        'backups': backups
    })


@settings_bp.route('/backups', methods=['POST'])
@handle_errors
def create_backup():
    """Create a manual backup"""
    manager = get_settings_manager()
    manager._create_backup()
    
    return jsonify({
        'success': True,
        'message': 'Backup created successfully'
    })


@settings_bp.route('/backups/<filename>/restore', methods=['POST'])
@handle_errors
def restore_backup(filename):
    """Restore settings from a backup"""
    manager = get_settings_manager()
    success, error = manager.restore_backup(filename)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    return jsonify({
        'success': True,
        'message': f'Settings restored from {filename}'
    })


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@settings_bp.route('/reload', methods=['POST'])
@handle_errors
def reload_settings():
    """Reload settings from file"""
    manager = get_settings_manager()
    success = manager.reload()
    
    if not success:
        return jsonify({
            'success': False,
            'error': 'Failed to reload settings'
        }), 500
    
    return jsonify({
        'success': True,
        'message': 'Settings reloaded successfully',
        'settings': manager.export()
    })


@settings_bp.route('/reset', methods=['POST'])
@handle_errors
def reset_to_defaults():
    """Reset all settings to default values"""
    # Require confirmation
    data = request.get_json() or {}
    confirm = data.get('confirm', False)
    
    if not confirm:
        return jsonify({
            'success': False,
            'error': 'Reset requires confirmation. Send {"confirm": true}'
        }), 400
    
    manager = get_settings_manager()
    success = manager.reset_to_defaults()
    
    if not success:
        return jsonify({
            'success': False,
            'error': 'Failed to reset settings'
        }), 500
    
    return jsonify({
        'success': True,
        'message': 'Settings reset to defaults'
    })


@settings_bp.route('/validate', methods=['POST'])
@handle_errors
def validate_settings():
    """
    Validate settings without saving.
    
    Request body: Same as batch update
    """
    data = request.get_json() or {}
    updates = data.get('updates', {})
    
    if not updates:
        return jsonify({
            'success': False,
            'error': 'No updates provided'
        }), 400
    
    manager = get_settings_manager()
    
    # Validate without saving
    from .settings_models import get_setting_definition, ValidationError
    errors = []
    
    for key, value in updates.items():
        definition = get_setting_definition(key)
        if definition:
            try:
                definition.validate(value)
            except ValidationError as e:
                errors.append(f"{key}: {str(e)}")
    
    if errors:
        return jsonify({
            'success': False,
            'errors': errors
        }), 400
    
    return jsonify({
        'success': True,
        'message': 'All settings are valid'
    })


# ============================================================================
# PAGE ROUTE
# ============================================================================

@settings_bp.route('/page', methods=['GET'])
@handle_errors
def settings_page():
    """Settings Page"""
    from flask import render_template
    from .settings_adapter import get_interface_manager
    
    try:
        from version import get_version
    except ImportError:
        def get_version():
            return "3.0.0"
    
    interface_manager = get_interface_manager()
    interfaces_by_category = interface_manager.get_interfaces_by_category()
    all_interfaces = interface_manager.get_all_interfaces()
    
    return render_template(
        'Settings/settings.html',
        interfaces_by_category=interfaces_by_category,
        all_interfaces=all_interfaces,
        user_settings=interface_manager,
        version=get_version()
    )


# Also register as direct route (for backward compatibility)
def register_settings_page_route(app):
    """Register settings page route directly on app"""
    from flask import render_template
    from .settings_adapter import get_interface_manager
    
    try:
        from version import get_version
    except ImportError:
        def get_version():
            return "3.0.0"
    
    @app.route('/settings')
    def settings_page_direct():
        """Settings Page (direct route)"""
        interface_manager = get_interface_manager()
        interfaces_by_category = interface_manager.get_interfaces_by_category()
        all_interfaces = interface_manager.get_all_interfaces()
        
        return render_template(
            'Settings/settings.html',
            interfaces_by_category=interfaces_by_category,
            all_interfaces=all_interfaces,
            user_settings=interface_manager,
            version=get_version()
        )


# Register blueprint
def register_settings_routes(app):
    """Register settings blueprint and page route with Flask app"""
    # Register API blueprint
    app.register_blueprint(settings_bp)
    
    # Register page route directly
    register_settings_page_route(app)
    
    logger.info("✅ Settings API routes and page route registered")

