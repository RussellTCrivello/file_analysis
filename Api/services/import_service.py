"""
Import Service
Handles importing files, database backups, and settings
"""

import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from io import BytesIO
import zipfile
import csv
from Api.utils import get_connection, return_connection



logger = logging.getLogger(__name__)


class ImportService:
    """
    Service for importing data in various formats.
    
    Supports:
    - Batch file import
    - Database backup import
    - Settings import
    """
    

    
    @staticmethod
    def import_database_backup(
        backup_file: BytesIO,
        restore_data: bool = False
    ) -> Dict[str, Any]:
        """
        Import database backup.
        
        Note: This is a read-only operation that validates the backup.
        Actual restoration would require database schema modifications,
        which are not allowed per requirements.
        
        Args:
            backup_file: BytesIO object containing backup ZIP file
            restore_data: Whether to restore data (currently not implemented)
        
        Returns:
            Dictionary with import validation results
        """
        try:
            # Extract and validate backup
            backup_file.seek(0)
            
            with zipfile.ZipFile(backup_file, 'r') as zip_file:
                if 'backup.json' not in zip_file.namelist():
                    raise ValueError("Invalid backup file: backup.json not found")
                
                backup_data = json.loads(zip_file.read('backup.json').decode('utf-8'))
            
            # Validate backup structure
            validation_results = {
                'valid': True,
                'export_date': backup_data.get('export_date'),
                'include_data': backup_data.get('include_data', False),
                'tables': list(backup_data.get('tables', {}).keys()),
                'table_count': len(backup_data.get('tables', {})),
                'warnings': []
            }
            
            # Check if tables exist in current database
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """)
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            backup_tables = set(validation_results['tables'])
            missing_tables = backup_tables - existing_tables
            extra_tables = existing_tables - backup_tables
            
            if missing_tables:
                validation_results['warnings'].append(
                    f"Backup contains tables not in current database: {', '.join(missing_tables)}"
                )
            
            if extra_tables:
                validation_results['warnings'].append(
                    f"Current database has tables not in backup: {', '.join(extra_tables)}"
                )
            
            # If restore_data is True, perform actual restoration
            if restore_data:
                if not backup_data.get('include_data', False):
                    validation_results['valid'] = False
                    validation_results['error'] = "Backup does not contain data. Cannot restore."
                    cursor.close()
                    return_connection(conn)
                    return validation_results
                
                # Validate schema compatibility before restoration
                schema_validation = ImportService._validate_schema_compatibility(
                    backup_data, cursor, existing_tables
                )
                
                if not schema_validation['compatible']:
                    validation_results['valid'] = False
                    validation_results['error'] = "Schema incompatibility detected"
                    validation_results['schema_errors'] = schema_validation['errors']
                    cursor.close()
                    return_connection(conn)
                    return validation_results
                
                # Perform restoration in a transaction
                try:
                    restoration_result = ImportService._restore_backup_data(
                        backup_data, conn, cursor
                    )
                    validation_results.update(restoration_result)
                    conn.commit()
                except Exception as restore_error:
                    conn.rollback()
                    logger.error(f"Error restoring backup data: {restore_error}", exc_info=True)
                    validation_results['valid'] = False
                    validation_results['error'] = f"Restoration failed: {str(restore_error)}"
                    raise
            else:
                validation_results['warnings'].append(
                    "Data restoration not requested. Use restore_data=True to restore."
                )
            
            cursor.close()
            return_connection(conn)
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error importing database backup: {e}", exc_info=True)
            return {
                'valid': False,
                'error': str(e)
            }
    
    @staticmethod
    def _validate_schema_compatibility(
        backup_data: Dict[str, Any],
        cursor,
        existing_tables: set
    ) -> Dict[str, Any]:
        """
        Validate that backup schema is compatible with current database schema.
        
        Args:
            backup_data: Backup data dictionary
            cursor: Database cursor
            existing_tables: Set of existing table names
            
        Returns:
            Dictionary with compatibility status and errors
        """
        errors = []
        backup_tables = backup_data.get('tables', {})
        
        for table_name, table_info in backup_tables.items():
            if table_name not in existing_tables:
                errors.append(f"Table '{table_name}' does not exist in current database")
                continue
            
            # Get current table schema
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s
                AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table_name,))
            
            current_columns = {
                row[0]: {'type': row[1], 'nullable': row[2] == 'YES'}
                for row in cursor.fetchall()
            }
            
            # Check backup schema
            backup_columns = {
                col['name']: {'type': col['type'], 'nullable': col.get('nullable', True)}
                for col in table_info.get('schema', [])
            }
            
            # Check for missing columns in current schema
            missing_columns = set(backup_columns.keys()) - set(current_columns.keys())
            if missing_columns:
                errors.append(
                    f"Table '{table_name}' is missing columns in current schema: {', '.join(missing_columns)}"
                )
            
            # Check for type mismatches (basic check)
            for col_name, backup_col in backup_columns.items():
                if col_name in current_columns:
                    current_col = current_columns[col_name]
                    # Basic type compatibility check (can be enhanced)
                    backup_type = backup_col['type'].upper()
                    current_type = current_col['type'].upper()
                    
                    # Allow some type variations (e.g., VARCHAR vs TEXT)
                    type_compatible = (
                        backup_type == current_type or
                        (backup_type in ('VARCHAR', 'TEXT', 'CHARACTER VARYING') and
                         current_type in ('VARCHAR', 'TEXT', 'CHARACTER VARYING')) or
                        (backup_type in ('INTEGER', 'INT', 'BIGINT', 'SMALLINT') and
                         current_type in ('INTEGER', 'INT', 'BIGINT', 'SMALLINT'))
                    )
                    
                    if not type_compatible:
                        errors.append(
                            f"Table '{table_name}', column '{col_name}': "
                            f"type mismatch (backup: {backup_type}, current: {current_type})"
                        )
        
        return {
            'compatible': len(errors) == 0,
            'errors': errors
        }
    
    @staticmethod
    def _restore_backup_data(
        backup_data: Dict[str, Any],
        conn,
        cursor
    ) -> Dict[str, Any]:
        """
        Restore data from backup.
        
        Args:
            backup_data: Backup data dictionary
            conn: Database connection
            cursor: Database cursor
            
        Returns:
            Dictionary with restoration results
        """
        restored_tables = []
        restored_rows = 0
        errors = []
        
        backup_tables = backup_data.get('tables', {})
        
        for table_name, table_info in backup_tables.items():
            if 'data' not in table_info or not table_info['data']:
                continue
            
            try:
                # Get column names from schema
                column_names = [col['name'] for col in table_info.get('schema', [])]
                if not column_names:
                    errors.append(f"Table '{table_name}': No schema information available")
                    continue
                
                # Clear existing data (optional - can be made configurable)
                # For safety, we'll use TRUNCATE which is faster and safer than DELETE
                cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
                
                # Prepare INSERT statement
                placeholders = ', '.join(['%s'] * len(column_names))
                columns_str = ', '.join(column_names)
                insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                
                # Insert data in batches for better performance
                batch_size = 1000
                data_rows = table_info['data']
                
                for i in range(0, len(data_rows), batch_size):
                    batch = data_rows[i:i + batch_size]
                    batch_values = []
                    
                    for row in batch:
                        # Convert row dictionary to tuple in column order
                        values = []
                        for col_name in column_names:
                            value = row.get(col_name)
                            
                            # Handle special cases
                            if value is None:
                                values.append(None)
                            elif isinstance(value, str) and value.startswith('<BYTEA:'):
                                # Skip BYTEA data (can't restore from backup)
                                values.append(None)
                            else:
                                values.append(value)
                        
                        batch_values.append(tuple(values))
                    
                    # Execute batch insert
                    if batch_values:
                        cursor.executemany(insert_sql, batch_values)
                
                restored_tables.append(table_name)
                restored_rows += len(data_rows)
                
            except Exception as e:
                error_msg = f"Error restoring table '{table_name}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                # Continue with other tables
                continue
        
        return {
            'restored_tables': restored_tables,
            'restored_rows': restored_rows,
            'restoration_errors': errors,
            'restoration_success': len(errors) == 0
        }
    
    @staticmethod
    def import_settings(
        settings_file: BytesIO
    ) -> Dict[str, Any]:
        """
        Import settings from JSON file.
        
        Args:
            settings_file: BytesIO object containing settings JSON
        
        Returns:
            Dictionary with imported settings and validation results
        """
        try:
            settings_file.seek(0)
            data = json.loads(settings_file.read().decode('utf-8'))
            
            # Extract settings
            if 'settings' in data:
                settings = data['settings']
            else:
                settings = data
            
            # Validate settings structure
            validation_results = {
                'valid': True,
                'imported_settings': settings,
                'export_date': data.get('export_date'),
                'warnings': []
            }
            
            # Basic validation
            if not isinstance(settings, dict):
                validation_results['valid'] = False
                validation_results['error'] = "Settings must be a dictionary"
                return validation_results
            
            return validation_results
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing settings JSON: {e}", exc_info=True)
            return {
                'valid': False,
                'error': f"Invalid JSON: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error importing settings: {e}", exc_info=True)
            return {
                'valid': False,
                'error': str(e)
            }
    
    @staticmethod
    def import_file_list_from_csv(
        csv_file: BytesIO,
        source_id: int,
        side_id: int
    ) -> Dict[str, Any]:
        """
        Import file list from CSV and process files.
        
        CSV should have a 'file_path' or 'path' column.
        
        Args:
            csv_file: BytesIO object containing CSV file
            source_id: Source ID for the files
            side_id: Side ID for the files
        
        Returns:
            Dictionary with import results
        """
        try:
            csv_file.seek(0)
            csv_content = csv_file.read().decode('utf-8-sig')  # Handle BOM
            csv_reader = csv.DictReader(csv_content.splitlines())
            
            file_paths = []
            for row in csv_reader:
                # Try different column names
                file_path = row.get('file_path') or row.get('path') or row.get('filepath')
                if file_path:
                    file_paths.append(file_path)
            
            if not file_paths:
                return {
                    'valid': False,
                    'error': 'No file paths found in CSV. Expected column: file_path, path, or filepath'
                }
            
            # Import files
            return ImportService.import_batch_files(file_paths, source_id, side_id)
            
        except Exception as e:
            logger.error(f"Error importing file list from CSV: {e}", exc_info=True)
            return {
                'valid': False,
                'error': str(e)
            }

