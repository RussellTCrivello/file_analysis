"""
Entry point for the CLI application
"""

import sys
import multiprocessing
from pathlib import Path

# Set multiprocessing start method (Windows uses 'spawn' by default)
if __name__ == '__main__':
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set, ignore

# Simplified initialization
from core.init import (
    setup_project_path,
    initialize_settings,
    initialize_database_config,
    initialize_system
)

# Set up project path
project_root = setup_project_path(__file__)

# Initialize settings
initialize_settings(project_root)

# Load database configuration
initialize_database_config()

# Initialize system
initialize_system()

# Import and run the CLI app
if __name__ == '__main__':
    from apps.cli.main import main
    main()
else:
    # When imported by multiprocessing child process, ensure path is set up
    setup_project_path()
