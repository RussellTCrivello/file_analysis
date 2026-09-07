"""
Entry point for the domain import utility.

This script imports domain classification data into the database.

Usage:
    python run_import.py
"""

import sys
from pathlib import Path

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

# Import and run the import utility
from apps.importing.import_domains import main

if __name__ == '__main__':
    main()
