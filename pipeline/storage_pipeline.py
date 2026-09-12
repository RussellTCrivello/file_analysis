
"""
Storage Pipeline - Complete file storage implementation
Handles extraction, tokenization, and database storage
Refactored to use ContentDBService with proper transaction management
Part 1: Core pipeline and text extraction
"""

import logging
import os
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter
import time
from datetime import date

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from Hdg_Err_Ex_Log import (
    handle_error, is_connection_error, is_retryable_error,
    ErrorCategory, ErrorSeverity, format_validation_error
)

logger = logging.getLogger(__name__)


def _parse_file_size_to_bytes(size_value):
    """
    Convert file size to integer bytes.
    Handles both integer bytes and formatted strings like "15.70 KB", "1.5 MB", etc.
    
    Args:
        size_value: File size as int, str, or None
        
    Returns:
        Integer bytes, or 0 if conversion fails
    """
    if size_value is None:
        return 0
    
    # If already an integer, return it
    if isinstance(size_value, int):
        return size_value
    
    # If it's a string, try to parse it
    if isinstance(size_value, str):
        # Remove any whitespace
        size_str = size_value.strip()
        
        # Try to parse as integer first (plain number)
        try:
            return int(float(size_str))
        except (ValueError, TypeError):
            pass
        
        # Try to parse formatted size (e.g., "15.70 KB", "1.5 MB", "500 B")
        import re
        # Match patterns like "15.70 KB", "1.5MB", "500B", "1024"
        match = re.match(r'^([\d.]+)\s*([KMGT]?B?|BYTES?)?$', size_str, re.IGNORECASE)
        if match:
            number = float(match.group(1))
            unit_str = (match.group(2) or '').upper()
            
            # Extract unit letter (K, M, G, T) or empty for bytes
            if unit_str.startswith('K'):
                unit = 'K'
            elif unit_str.startswith('M'):
                unit = 'M'
            elif unit_str.startswith('G'):
                unit = 'G'
            elif unit_str.startswith('T'):
                unit = 'T'
            else:
                unit = ''  # Bytes or no unit specified
            
            multipliers = {
                '': 1,
                'K': 1024,
                'M': 1024 * 1024,
                'G': 1024 * 1024 * 1024,
                'T': 1024 * 1024 * 1024 * 1024
            }
            
            multiplier = multipliers.get(unit, 1)
            return int(number * multiplier)
        
        # If parsing fails, try to get actual file size from path
        return 0
    
    # For other types, try to convert to int
    try:
        return int(size_value)
    except (ValueError, TypeError):
        return 0


class StoragePipeline:
    """
    Orchestrates file storage to database using ContentDBService.
    
    This class has been refactored to align with database design principles:
    - Uses ContentDBService for all database operations
    - Uses transactions for multi-step operations
    - Proper error handling with rollback on failures
    """
    
    # Shared DatabaseHub instance to prevent connection pool exhaustion
    _shared_db_hub = None
    _shared_db_hub_lock = None
    
    def __init__(self, db_hub=None, source_name: str = None, side_name: str = None, db_service=None):
        """
        Initialize storage pipeline
        
        Args:
            db_hub: DatabaseHub instance (optional, kept for backward compatibility)
            source_name: Source name (optional, but must be provided in _store_file_sync if not here)
            side_name: Side name (optional, but must be provided in _store_file_sync if not here)
            db_service: ContentDBService instance (optional, will be created if not provided)
        """
        # Initialize lock for thread-safe singleton access
        if StoragePipeline._shared_db_hub_lock is None:
            import threading
            StoragePipeline._shared_db_hub_lock = threading.Lock()
        
        # Initialize ContentDBService (preferred method)
        if db_service is None:
            from database.services.contents_db_service import ContentDBService
            from database.database.database import Database
            try:
                db = Database()  # Uses connection pooling and environment config
                db_service = ContentDBService(db)
            except Exception as e:
                logger.error(f"Failed to create ContentDBService: {e}")
                raise
        
        self.db_service = db_service
        
        # Keep db_hub for backward compatibility (content processor, etc.)
        # But prefer db_service for database operations
        # NOTE: DatabaseHub may not exist - it's optional for storage functionality
        # Storage works with db_service alone, db_hub is only needed for advanced features
        # CRITICAL FIX: Use shared DatabaseHub instance to prevent connection pool exhaustion
        if db_hub is None:
            # Use singleton pattern to prevent multiple connection pools
            with StoragePipeline._shared_db_hub_lock:
                if StoragePipeline._shared_db_hub is None:
                    try:
                        from database import DatabaseHub
                        from settings import get_storage_config
                        storage_cfg = get_storage_config()
                        StoragePipeline._shared_db_hub = DatabaseHub(db_name=storage_cfg.db_name)
                        logger.info("Created shared DatabaseHub instance for connection pooling")
                    except (ImportError, AttributeError) as e:
                        # DatabaseHub doesn't exist or can't be imported - this is OK
                        # Storage functionality works without it using db_service
                        logger.info(f"DatabaseHub not available (optional): {e}. Storage will work with db_service only.")
                        StoragePipeline._shared_db_hub = None
                    except Exception as e:
                        logger.warning(f"Failed to create DatabaseHub (some features may be limited): {e}")
                        StoragePipeline._shared_db_hub = None
                db_hub = StoragePipeline._shared_db_hub
        
        self.db_hub = db_hub
        
        # Store source and side names (optional in constructor, but mandatory in _store_file_sync)
        # No defaults - source and side must be explicitly provided
        self._source_name = source_name
        self._side_name = side_name
        
        # Statistics (DATA-04: full counter set with consistency relationships:
        # discovered >= completed(stored+duplicates) + failed + skipped;
        # storage failures are tracked separately and never folded into success)
        self.stats = {
            'files_discovered': 0,
            'files_queued': 0,
            'files_started': 0,
            'files_processed': 0,      # completed processing (any outcome)
            'files_stored': 0,
            'files_duplicates': 0,
            'files_failed': 0,
            'files_skipped': 0,
            'files_unsupported': 0,
            'storage_failed': 0,
            'files_extracted': 0,
        }

    def record_discovered(self, count: int = 1) -> None:
        """Record discovered files (called by the discovery phase)."""
        self.stats['files_discovered'] = self.stats.get('files_discovered', 0) + count

    def record_skipped(self, count: int = 1, reason: str = '') -> None:
        """Record skipped files with an optional reason (kept in stats)."""
        self.stats['files_skipped'] = self.stats.get('files_skipped', 0) + count
        if reason:
            skipped = self.stats.setdefault('skip_reasons', {})
            skipped[reason] = skipped.get(reason, 0) + 1

    def get_stats_summary(self) -> Dict[str, Any]:
        """Return stats plus consistency validation (DATA-04)."""
        s = dict(self.stats)
        completed = s.get('files_stored', 0) + s.get('files_duplicates', 0)
        issues = []
        discovered = s.get('files_discovered', 0)
        if discovered:
            if discovered < completed + s.get('files_failed', 0) + s.get('files_skipped', 0):
                issues.append('counter inconsistency: discovered < completed+failed+skipped')
            if discovered != (completed + s.get('files_failed', 0)
                              + s.get('files_skipped', 0) + s.get('files_unsupported', 0)
                              + max(0, discovered - (completed + s.get('files_failed', 0)
                                                     + s.get('files_skipped', 0) + s.get('files_unsupported', 0)))):
                # discovered may exceed the sum while work is in flight; that is
                # not an error - only the '<' case above is a real violation.
                pass
        s['consistency_issues'] = issues
        return s
    
    def _store_file_sync(
        self,
        file_info: Dict[str, Any],
        result: Dict[str, Any],
        source_name: Optional[str] = None,
        side_name: Optional[str] = None,
        parent_path_id: Optional[int] = None,
        hierarchy_path: Optional[str] = None
        ) -> Optional[int]:
        """
        Store single file synchronously with improved error handling
        
        Args:
            file_info: File metadata dictionary
            result: File processing result
            source_name: Source name (overrides constructor default)
            side_name: Side name (overrides constructor default)
            parent_path_id: Parent path ID (for nested files)
            hierarchy_path: Hierarchy path string
        
        Returns:
            Path ID or None if failed
        """
        # Require explicit source/side names (no defaults, no auto-creation)
        # Source and side must be explicitly provided - either in constructor or in this call
        effective_source_name = source_name if source_name is not None else getattr(self, '_source_name', None)
        effective_side_name = side_name if side_name is not None else getattr(self, '_side_name', None)
        
        # CRITICAL: Validate source/side but don't fail - use fallback values to ensure file is stored
        if not effective_source_name:
            logger.error("source_name is MANDATORY - must be explicitly provided. No defaults allowed.")
            # Use fallback to ensure file is still stored with error information
            effective_source_name = "__ERROR_NO_SOURCE__"
            logger.warning(f"Using fallback source name '{effective_source_name}' to ensure file is stored")
        
        if not effective_side_name:
            logger.error("side_name is MANDATORY - must be explicitly provided. No defaults allowed.")
            # Use fallback to ensure file is still stored with error information
            effective_side_name = "__ERROR_NO_SIDE__"
            logger.warning(f"Using fallback side name '{effective_side_name}' to ensure file is stored")
        
        # Get or create source and side using ContentDBService
        # First, try to get existing sources/sides
        all_sources = self.db_service.get_all_sources()
        source_id = None
        for sid, sname in all_sources:
            if sname == effective_source_name:
                source_id = sid
                break
        
        # Create source if it doesn't exist
        if source_id is None:
            try:
                source_id = self.db_service.create_source(
                    name=effective_source_name,
                    country="",
                    job="",
                    importance=1.0
                )
                logger.info(f"Created new source: {effective_source_name} (ID: {source_id})")
            except Exception as e:
                logger.error(f"Failed to create source '{effective_source_name}': {e}")
                # CRITICAL: Don't return None - try to use a fallback source or create with retry
                # Attempt to get/create a fallback source
                try:
                    fallback_source_name = "__FALLBACK_SOURCE__"
                    all_sources = self.db_service.get_all_sources()
                    for sid, sname in all_sources:
                        if sname == fallback_source_name:
                            source_id = sid
                            logger.warning(f"Using fallback source '{fallback_source_name}' (ID: {source_id})")
                            break
                    if source_id is None:
                        source_id = self.db_service.create_source(
                            name=fallback_source_name,
                            country="",
                            job="",
                            importance=0.5
                        )
                        logger.warning(f"Created fallback source '{fallback_source_name}' (ID: {source_id})")
                except Exception as fallback_error:
                    logger.error(f"Failed to create fallback source: {fallback_error}")
                    # Last resort: use first available source or fail gracefully
                    all_sources = self.db_service.get_all_sources()
                    if all_sources:
                        source_id = all_sources[0][0]
                        logger.warning(f"Using first available source (ID: {source_id}) as last resort")
                    else:
                        logger.error("No sources available and cannot create one - file cannot be stored")
                        self.stats['files_failed'] += 1
                        return None
        
        # Get or create side
        all_sides = self.db_service.get_all_sides()
        side_id = None
        for sid, sname in all_sides:
            if sname == effective_side_name:
                side_id = sid
                break
        
        # Create side if it doesn't exist
        if side_id is None:
            try:
                side_id = self.db_service.create_side(
                    name=effective_side_name,
                    importance=1.0
                )
                logger.info(f"Created new side: {effective_side_name} (ID: {side_id})")
            except Exception as e:
                logger.error(f"Failed to create side '{effective_side_name}': {e}")
                # CRITICAL: Don't return None - try to use a fallback side or create with retry
                # Attempt to get/create a fallback side
                try:
                    fallback_side_name = "__FALLBACK_SIDE__"
                    all_sides = self.db_service.get_all_sides()
                    for sid, sname in all_sides:
                        if sname == fallback_side_name:
                            side_id = sid
                            logger.warning(f"Using fallback side '{fallback_side_name}' (ID: {side_id})")
                            break
                    if side_id is None:
                        side_id = self.db_service.create_side(
                            name=fallback_side_name,
                            importance=0.5
                        )
                        logger.warning(f"Created fallback side '{fallback_side_name}' (ID: {side_id})")
                except Exception as fallback_error:
                    logger.error(f"Failed to create fallback side: {fallback_error}")
                    # Last resort: use first available side or fail gracefully
                    all_sides = self.db_service.get_all_sides()
                    if all_sides:
                        side_id = all_sides[0][0]
                        logger.warning(f"Using first available side (ID: {side_id}) as last resort")
                    else:
                        logger.error("No sides available and cannot create one - file cannot be stored")
                        self.stats['files_failed'] += 1
                        return None
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Check database connection health (only if db_hub is available)
                # CRITICAL: Don't fail if connection check fails - retry will handle it
                if self.db_hub:
                    if not self.db_hub._check_connection_health():
                        logger.warning("Database connection unhealthy, attempting reconnect...")
                        if not self.db_hub._reconnect():
                            logger.error("Failed to reconnect to database - will retry in outer loop")
                            # Don't return None here - let retry logic handle it
                            if retry_count >= max_retries:
                                # Only fail after all retries exhausted
                                logger.error("All retries exhausted - cannot store file")
                                self.stats['files_failed'] += 1
                                return None
                            retry_count += 1
                            time.sleep(1.0 * retry_count)
                            continue
                
                # Extract metadata and content (with validation)
                metadata = result.get('Metadata', {})
                if not isinstance(metadata, dict):
                    logger.warning(f"Invalid Metadata type: {type(metadata).__name__}, using empty dict")
                    metadata = {}
                
                content = result.get('Content', {})
                if not isinstance(content, dict):
                    logger.warning(f"Invalid Content type: {type(content).__name__}, using empty dict")
                    content = {}
                
                # Validate required fields - create minimal file_info if missing
                if not file_info or not isinstance(file_info, dict):
                    logger.error("Invalid file_info: must be a non-empty dictionary - creating minimal file_info")
                    # CRITICAL: Create minimal file_info to ensure file can still be stored
                    file_info = {
                        'path': result.get('path', 'unknown'),
                        'name': os.path.basename(result.get('path', 'unknown')),
                        'extension': '',
                        'size': 0
                    }
                    logger.warning(f"Using minimal file_info: {file_info}")
                
                # Check for errors (but ALWAYS store metadata - errors are part of the record)
                has_content_error = bool(content.get('error'))
                if has_content_error:
                    error_msg = content.get('error', 'Unknown error')
                    logger.info(f"File has content error: {error_msg}. Will store metadata and error information.")
                
                # Step 1: Calculate/validate hash (DB-03)
                # Content identity is ALWAYS the streamed SHA-256 of the file
                # bytes. Metadata-derived and time-based fallback hashes were
                # removed: a file that cannot be hashed is a processing
                # FAILURE (counted in stats), never stored under a fake
                # identity.
                # HASH-01: a hash supplied by an upstream producer is only
                # trusted if it is a well-formed digest. Sentinels such as
                # SKIPPED_LARGE_FILE are recomputed here rather than stored.
                from core.hashing import is_valid_digest
                file_hash = metadata.get('hash') or file_info.get('hash')
                file_hash_valid = is_valid_digest(file_hash)
                if not file_hash_valid:
                    from core.hashing import hash_file, HashingError
                    file_path_for_hash = file_info.get('path')
                    if not file_path_for_hash:
                        logger.error("File path is missing from file_info - cannot compute content hash")
                        self.stats['files_failed'] = self.stats.get('files_failed', 0) + 1
                        self.stats.setdefault('storage_failed', 0)
                        self.stats['storage_failed'] = self.stats.get('storage_failed', 0) + 1
                        return None
                    try:
                        file_hash = hash_file(file_path_for_hash)
                        logger.debug("Computed content hash for %s", os.path.basename(file_path_for_hash))
                    except HashingError as hash_exc:
                        logger.error("Hashing failed for %s - refusing to store under a fake identity",
                                     file_path_for_hash)
                        self.stats['files_failed'] = self.stats.get('files_failed', 0) + 1
                        self.stats.setdefault('storage_failed', 0)
                        self.stats['storage_failed'] = self.stats.get('storage_failed', 0) + 1
                        return None

                # Validate hash shape; never replace with a synthetic value.
                if not is_valid_digest(file_hash):
                    logger.error("Invalid hash value %r - refusing to store", file_hash[:16] if file_hash else file_hash)
                    self.stats['files_failed'] = self.stats.get('files_failed', 0) + 1
                    self.stats.setdefault('storage_failed', 0)
                    self.stats['storage_failed'] = self.stats.get('storage_failed', 0) + 1
                    return None
                
                # Step 2: Check for duplicates using ContentDBService
                # Check if hash already exists for this source and side
                hash_exists = self.db_service.hash_exists(file_hash, source_id)
                if hash_exists:
                    # Hash exists - check if it's a duplicate
                    # Note: We can't easily get the path_id from ContentDBService without additional queries
                    # For now, we'll use db_hub if available for duplicate checking, otherwise proceed with storage
                    # (ContentDBService will handle duplicates via database constraints)
                    if self.db_hub:
                        is_duplicate, existing_path_id = self.check_duplicate_for_pipeline(file_hash, source_id, side_id)
                        if is_duplicate:
                            logger.info(
                                f"Duplicate file detected (already processed): {file_info.get('name', 'unknown')} "
                                f"(hash: {file_hash[:16]}..., existing path_id: {existing_path_id})"
                            )
                            self.stats['files_duplicates'] += 1
                            self.stats['files_processed'] += 1
                            return existing_path_id
                    else:
                        # Hash exists but db_hub not available - proceed with storage
                        # ContentDBService will handle duplicates via database constraints or return existing path_id
                        logger.debug(f"Hash exists but cannot check for duplicate path_id (db_hub not available). Proceeding with storage - database will handle duplicates.")
                        # Continue to storage - don't return None
                
                # Step 3: Prepare file metadata for storage
                # Extract file information
                file_name = file_info.get('name', os.path.basename(file_info.get('path', 'unknown')))
                file_path = file_info.get('path', '')
                
                # Get file size and ensure it's an integer (bytes)
                # Try size_bytes first, then size, then get from file system
                file_size = file_info.get('size_bytes') or file_info.get('size') or metadata.get('size_bytes') or metadata.get('size')
                
                # Convert to integer bytes if it's a string
                file_size = _parse_file_size_to_bytes(file_size)
                
                # If still 0, try to get actual file size from file system
                if file_size == 0 and file_path and os.path.exists(file_path):
                    try:
                        file_size = os.path.getsize(file_path)
                    except Exception:
                        file_size = 0
                
                file_type = metadata.get('file_type', file_info.get('extension', 'unknown'))
                
                # Get file creation date from file system (st_ctime)
                # file_date stores the file's creation date, not any other date
                file_date = date.today()  # Default fallback
                if file_path and os.path.exists(file_path):
                    try:
                        from datetime import datetime
                        file_creation_time = os.path.getctime(file_path)
                        file_date = datetime.fromtimestamp(file_creation_time).date()
                    except Exception as e:
                        logger.warning(f"Could not get file creation date for {file_path}: {e}")
                        file_date = date.today()
                
                # Extract text content for processing
                text = None
                if not has_content_error:
                    text = self._extract_text_from_content(content)
                
                # Check if OCR was attempted/successful for images (even if text extraction fails)
                ocr_attempted = content.get('ocr_attempted', False) if isinstance(content, dict) else False
                ocr_successful = content.get('ocr_successful', False) if isinstance(content, dict) else False
                extraction_info = content.get('extraction_info', {}) if isinstance(content, dict) else {}
                has_extracted_text = extraction_info.get('extracted', False) or extraction_info.get('stored', False)
                
                # OPTIMIZED: Use unified ContentProcessor for all extraction (faster, preserves entities)
                content_words = []
                title_words = None
                content_date = None  # Will be extracted from content if dates are mentioned
                
                if text:
                    # PRODUCTION: Handle very large text content (>100MB) with chunked processing
                    # For terabyte-scale files, process text in chunks to prevent memory exhaustion
                    text_len = len(text) if isinstance(text, str) else 0
                    use_chunked_processing = text_len > 100 * 1024 * 1024  # > 100MB
                    
                    if use_chunked_processing:
                        logger.info(f"Large text content detected ({text_len / (1024*1024):.2f}MB), using chunked processing")
                        # Process text in chunks and accumulate words
                        content_words = []
                        chunk_size = 50 * 1024 * 1024  # 50MB chunks
                        try:
                            from database.processors import get_content_processor
                            processor = get_content_processor()
                            
                            # Process in chunks
                            for chunk_start in range(0, text_len, chunk_size):
                                chunk_end = min(chunk_start + chunk_size, text_len)
                                text_chunk = text[chunk_start:chunk_end]
                                
                                # Process chunk
                                chunk_tokens = processor.extract_words_with_punctuation_chunked(text_chunk)
                                chunk_words = [token[0] for token in chunk_tokens if token[0]]
                                content_words.extend(chunk_words)
                                
                                # Log progress for very large files
                                if chunk_start % (chunk_size * 10) == 0:
                                    progress_pct = (chunk_end / text_len) * 100
                                    logger.debug(f"Processed {chunk_end / (1024*1024):.2f}MB / {text_len / (1024*1024):.2f}MB ({progress_pct:.1f}%)")
                            
                            # Extract dates from first chunk (most likely to contain dates)
                            sample_text = text[:min(10 * 1024 * 1024, text_len)]  # First 10MB
                            content_date = self._extract_date_from_text(sample_text, processor)
                        except MemoryError as mem_err:
                            logger.error(f"Memory error during chunked text processing: {mem_err}")
                            # Fallback: process smaller chunks
                            try:
                                chunk_size = 10 * 1024 * 1024  # 10MB chunks
                                processor = get_content_processor()
                                for chunk_start in range(0, text_len, chunk_size):
                                    chunk_end = min(chunk_start + chunk_size, text_len)
                                    text_chunk = text[chunk_start:chunk_end]
                                    chunk_tokens = processor.extract_words_with_punctuation_chunked(text_chunk, chunk_size=5 * 1024 * 1024)
                                    chunk_words = [token[0] for token in chunk_tokens if token[0]]
                                    content_words.extend(chunk_words)
                                content_date = self._extract_date_from_text(text[:min(5 * 1024 * 1024, text_len)], processor)
                            except Exception as fallback_err:
                                logger.error(f"Fallback chunked processing also failed: {fallback_err}")
                                content_words = []
                                content_date = None
                        except Exception as e:
                            logger.warning(f"Chunked content processor extraction failed: {e}")
                            # Fallback: try standard processing with smaller chunk size
                            try:
                                from database.processors import get_content_processor
                                processor = get_content_processor()
                                # Use smaller chunk size for tokenization
                                tokens = processor.extract_words_with_punctuation_chunked(text, chunk_size=5 * 1024 * 1024)
                                content_words = [token[0] for token in tokens if token[0]]
                                content_date = self._extract_date_from_text(text[:min(10 * 1024 * 1024, text_len)], processor)
                            except Exception as fallback_err:
                                logger.error(f"Fallback processing failed: {fallback_err}")
                                content_words = []
                                content_date = None
                    else:
                        # Standard processing for smaller text
                        try:
                            from database.processors import get_content_processor
                            processor = get_content_processor()
                            tokens = processor.extract_words_with_punctuation_chunked(text)
                            # Extract just the words (first element of each token tuple)
                            content_words = [token[0] for token in tokens if token[0]]
                            
                            # Extract dates from content text for content_date field
                            # content_date stores a date mentioned in the content itself
                            content_date = self._extract_date_from_text(text, processor)
                        except Exception as e:
                            logger.warning(f"Content processor extraction failed: {e}")
                            # Fallback only if processor completely fails
                            content_words = []
                            content_date = None
                
                # Set file_status: 'Read' if file contains content OR OCR was successful
                # This ensures images with extracted text are marked as 'Read' even if tokenization fails
                has_content = bool(content_words)
                has_ocr_text = bool(text and text.strip())
                is_read = has_content or (ocr_successful and has_ocr_text) or has_extracted_text
                file_status = 'Read' if is_read else 'Unread'
                
                # Log status determination for debugging
                if ocr_attempted and not is_read:
                    logger.debug(
                        f"[STATUS] File marked as 'Unread' despite OCR attempt - "
                        f"OCR successful: {ocr_successful}, "
                        f"Has text: {has_ocr_text}, "
                        f"Has content_words: {has_content}, "
                        f"Extraction info: {extraction_info}"
                    )
                
                # Extract coordinates from content (GPS coordinates in images or elsewhere)
                coordinates = self._extract_coordinates(content)
                
                # Extract title if available (using same optimized processor)
                title = self._extract_title(result, file_info)
                if title:
                    try:
                        from database.processors import get_content_processor
                        processor = get_content_processor()
                        title_words = processor.extract_words_simple(title)
                    except Exception as e:
                        logger.warning(f"Title extraction failed: {e}")
                        title_words = []
                
                # Step 4: Store document using ContentDBService.process_full_document()
                # This handles hash, path, content, word linking, keywords, and title in a single transaction
                
                # Log what will be stored
                storage_info = []
                storage_info.append(f"File: {file_name}")
                storage_info.append(f"Type: {file_type}")
                storage_info.append(f"Status: {file_status}")
                storage_info.append(f"Content Words: {len(content_words)}")
                if title_words:
                    storage_info.append(f"Title Words: {len(title_words)}")
                if coordinates:
                    storage_info.append(f"GPS Coordinates: {coordinates}")
                if content_date:
                    storage_info.append(f"Content Date: {content_date}")
                
                logger.info(f"[STORAGE] 💾 Storing to database - {' | '.join(storage_info)}")
                
                try:
                    # PRODUCTION: process_full_document uses its own transaction
                    # If it fails, it will rollback and we can retry with a fresh transaction
                    storage_result = self.db_service.process_full_document(
                        hash_value=file_hash,
                        source_id=source_id,
                        side_id=side_id,
                        file_name=file_name,
                        file_path=file_path,
                        file_size=file_size,
                        file_type=file_type,
                        file_status=file_status,
                        file_date=file_date,
                        content_words=content_words,
                        title_words=title_words,
                        coordinates=coordinates,
                        content_date=content_date
                    )
                    
                    # Handle case where storage_result is None
                    # CRITICAL: Try fallback storage method to ensure file metadata is stored
                    if storage_result is None:
                        logger.error(
                            f"process_full_document returned None for file '{file_name}' - "
                            f"transaction may have failed, attempting fallback storage. "
                            f"File: {file_path[:100] if len(file_path) > 100 else file_path}"
                        )
                        # Try to store at least basic metadata using fallback method
                        try:
                            # First, try to get hash_id if it exists
                            hash_id = None
                            try:
                                hash_row = self.db_service.hashs_repo.get_hash_by_value(file_hash)
                                if hash_row:
                                    hash_id = hash_row[0] if isinstance(hash_row, tuple) else hash_row.get('id') if isinstance(hash_row, dict) else hash_row
                            except Exception as hash_err:
                                logger.debug(f"Could not get hash_id for fallback: {hash_err}")
                            
                            # Use direct path insertion as fallback
                            if hash_id:
                                fallback_path_id = self.db_service.paths_repo.insert_path(
                                    file_name=file_name,
                                    file_path=file_path,
                                    file_size=file_size,
                                    file_type=file_type,
                                    file_status='Unread',  # Mark as unread since full processing failed
                                    file_date=file_date,
                                    hash_id=hash_id,
                                    coordinates=None
                                )
                            else:
                                # Try without hash_id (may fail but worth trying)
                                logger.warning("Attempting fallback storage without hash_id")
                                # Create minimal hash first
                                try:
                                    hash_id = self.db_service.hashs_repo.insert_hash(
                                        hash_value=file_hash,
                                        source_id=source_id,
                                        side_id=side_id
                                    )
                                    if hash_id:
                                        fallback_path_id = self.db_service.paths_repo.insert_path(
                                            file_name=file_name,
                                            file_path=file_path,
                                            file_size=file_size,
                                            file_type=file_type,
                                            file_status='Unread',
                                            file_date=file_date,
                                            hash_id=hash_id,
                                            coordinates=None
                                        )
                                    else:
                                        fallback_path_id = None
                                except Exception as hash_create_err:
                                    logger.error(f"Failed to create hash for fallback: {hash_create_err}")
                                    fallback_path_id = None
                            
                            if fallback_path_id:
                                logger.warning(
                                    f"✅ Stored file using fallback method (Path ID: {fallback_path_id}) - "
                                    f"full processing failed but metadata saved. File: {file_name}"
                                )
                                self.stats['files_stored'] += 1
                                self.stats['files_processed'] += 1
                                return fallback_path_id
                            else:
                                logger.error(f"Fallback path insertion returned None for file: {file_name}")
                        except Exception as fallback_error:
                            logger.error(
                                f"Fallback storage failed for file '{file_name}': {fallback_error}. "
                                f"Error type: {type(fallback_error).__name__}"
                            )
                            import traceback
                            logger.debug(f"Fallback error traceback: {traceback.format_exc()}")
                        
                        # If fallback also fails, increment retry count and try again
                        if retry_count < max_retries:
                            retry_count += 1
                            logger.warning(
                                f"Retrying storage for '{file_name}' (attempt {retry_count}/{max_retries})..."
                            )
                            time.sleep(1.0 * retry_count)
                            continue
                        else:
                            logger.error(
                                f"❌ All storage attempts failed for file '{file_name}'. "
                                f"File processed but NOT stored in database. Path: {file_path[:100]}"
                            )
                            self.stats['files_failed'] += 1
                            return None
                    
                    if storage_result.get('success'):
                        path_id = storage_result.get('path_id')
                        hash_id = storage_result.get('hash_id')
                        error_msg = storage_result.get('error')
                        
                        # Check if this is a duplicate
                        if error_msg and 'Duplicate' in error_msg:
                            logger.info(
                                f"[STORAGE] 🔄 Duplicate file detected - "
                                f"path_id={path_id}, hash_id={hash_id}"
                            )
                            self.stats['files_duplicates'] += 1
                            self.stats['files_processed'] += 1
                        else:
                            # Log successful storage with details
                            stored_details = []
                            stored_details.append(f"Path ID: {path_id}")
                            stored_details.append(f"Hash ID: {hash_id}")
                            stored_details.append(f"Status: {file_status}")
                            stored_details.append(f"Words: {len(content_words)}")
                            if coordinates:
                                stored_details.append(f"GPS: {coordinates}")
                            
                            logger.info(
                                f"[STORAGE] ✅ Successfully stored - {' | '.join(stored_details)}"
                            )
                            logger.info(
                                f"Document stored successfully using ContentDBService: "
                                f"path_id={path_id}, hash_id={hash_id}"
                            )
                            # Update statistics
                            self.stats['files_stored'] += 1
                            self.stats['files_processed'] += 1
                        
                        # Build success message
                        file_size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                        is_duplicate = error_msg and 'Duplicate' in error_msg if error_msg else False
                        
                        if is_duplicate:
                            storage_details = [
                                f"⚠️  DUPLICATE FILE DETECTED (already processed)",
                                f"   File: {file_name}",
                                f"   Path ID: {path_id} (existing)",
                                f"   Hash ID: {hash_id}",
                                f"   Source: {effective_source_name} (ID: {source_id})",
                                f"   Side: {effective_side_name} (ID: {side_id})",
                                f"   Hash: {file_hash[:16]}...",
                            ]
                        else:
                            storage_details = [
                                f"✅ FILE SUCCESSFULLY STORED IN DATABASE (using ContentDBService with transactions)",
                                f"   File: {file_name}",
                                f"   Path ID: {path_id}",
                                f"   Hash ID: {hash_id}",
                                f"   Source: {effective_source_name} (ID: {source_id})",
                                f"   Side: {effective_side_name} (ID: {side_id})",
                                f"   Hash: {file_hash[:16]}...",
                            ]
                        
                        if file_size_mb > 0:
                            storage_details.append(f"   Size: {file_size_mb:.2f} MB ({file_size:,} bytes)")
                        
                        if not is_duplicate:
                            storage_details.append(f"   Words: {len(content_words):,}")
                            if title_words:
                                storage_details.append(f"   Title: {len(title_words)} words")
                        storage_details.append(f"   Status: {file_status}")
                        storage_details.append(f"   Database Record: paths.id = {path_id}")
                        
                        success_message = "\n".join(storage_details)
                        logger.info(success_message)
                        print(success_message)
                        
                        return path_id
                    else:
                        error_msg = storage_result.get('error', 'Unknown error')
                        logger.error(f"Failed to store document: {error_msg}")
                        handle_error(
                            Exception(error_msg),
                            category=ErrorCategory.DATABASE,
                            severity=ErrorSeverity.HIGH,
                            context={
                                'operation': 'process_full_document',
                                'file_path': file_path[:100],
                                'file_hash': file_hash[:16] + '...'
                            },
                            suggested_action='Check database connection and constraints'
                        )
                        self.stats['files_failed'] += 1
                        return None
                        
                except Exception as doc_error:
                    error_type = type(doc_error).__name__
                    error_msg = str(doc_error)
                    file_name_display = file_name if 'file_name' in locals() else 'unknown'
                    
                    logger.error(
                        f"❌ Error storing document '{file_name_display}' with ContentDBService: "
                        f"{error_type}: {error_msg}"
                    )
                    
                    # Log more details for debugging
                    import traceback
                    logger.debug(f"Storage error traceback for '{file_name_display}': {traceback.format_exc()}")
                    
                    # Check if it's a connection error that can be retried
                    is_conn_err = is_connection_error(doc_error)
                    if is_conn_err and retry_count < max_retries:
                        retry_count += 1
                        logger.warning(
                            f"Connection error detected, retrying storage for '{file_name_display}' "
                            f"(attempt {retry_count}/{max_retries})..."
                        )
                        time.sleep(1.0 * retry_count)
                        continue
                    
                    handle_error(
                        doc_error,
                        category=ErrorCategory.DATABASE_CONNECTION if is_conn_err else ErrorCategory.DATABASE,
                        severity=ErrorSeverity.HIGH,
                        context={
                            'operation': 'process_full_document',
                            'file_path': file_path[:100] if 'file_path' in locals() else 'unknown',
                            'file_name': file_name_display,
                            'file_hash': file_hash[:16] + '...' if 'file_hash' in locals() else 'unknown',
                            'error_type': error_type,
                            'retry_count': retry_count
                        }
                    )
                    
                    # Only fail if all retries exhausted
                    if retry_count >= max_retries:
                        self.stats['files_failed'] += 1
                        return None
                    else:
                        # Continue to retry
                        retry_count += 1
                        time.sleep(1.0 * retry_count)
                        continue
                
                # OLD CODE BELOW - DEPRECATED: This section is now replaced by ContentDBService.process_full_document()
                # The code above should always return (either path_id or None), so this should never execute
                # Keeping for reference but disabled to prevent errors
                # If execution reaches here, it means the new code path didn't return properly
                logger.error("ERROR: Execution reached deprecated code path. This should not happen.")
                self.stats['files_failed'] += 1
                return None
                
            except Exception as e:
                # Handle any unexpected errors in the main storage flow
                # Use improved error detection from error_handling module
                if is_connection_error(e):
                    # Connection errors - try to reconnect
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.MEDIUM if retry_count < max_retries else ErrorSeverity.HIGH,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action='Attempting to reconnect and retry' if retry_count < max_retries else 'Check database server status'
                    )
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"Attempting to reconnect (attempt {retry_count}/{max_retries})...")
                        if self.db_hub and self.db_hub._reconnect():
                            # Wait a bit before retrying
                            time.sleep(1.0)
                            continue
                        else:
                            logger.error(f"Failed to reconnect, will retry entire operation")
                            time.sleep(2.0 * retry_count)  # Exponential backoff
                            continue
                    
                    handle_error(
                        Exception(f"Failed to reconnect after {retry_count} attempts"),
                        category=ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.HIGH,
                        context={'operation': '_store_file_sync', 'file_path': file_info.get('path', 'unknown')[:100] if file_info else None}
                    )
                    self.stats['files_failed'] += 1
                    return None
                elif is_retryable_error(e) and retry_count < max_retries:
                    # Other retryable errors
                    retry_count += 1
                    wait_time = 1.0 * (2 ** (retry_count - 1))  # Exponential backoff
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE,
                        severity=ErrorSeverity.MEDIUM,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action=f'Retrying operation in {wait_time:.1f}s (attempt {retry_count}/{max_retries})'
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    # Non-retryable errors or max retries reached
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE if not is_connection_error(e) else ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.HIGH,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action='Check error details and database state' if retry_count >= max_retries else None
                    )
                    self.stats['files_failed'] += 1
                    return None
                
                # ========================================================================
                # DEPRECATED CODE PATH - DISABLED
                # This code should NEVER execute. All storage now uses ContentDBService.process_full_document()
                # If execution reaches here, it's a critical bug - the new code path should have returned.
                # ========================================================================
                logger.critical("CRITICAL ERROR: Execution reached deprecated code path at line 750+. This should never happen.")
                logger.critical("The new ContentDBService.process_full_document() code should have returned path_id or None.")
                logger.critical("This deprecated code uses db_hub operations that no longer exist and will cause AttributeError.")
                # Return None immediately to prevent execution of deprecated code
                self.stats['files_failed'] += 1
                return None
                
                # OLD CODE BELOW IS DISABLED - DO NOT UNCOMMENT
                # The code below uses db_hub.path_operations, db_hub.word_operations, etc. which don't exist
                # All storage should use ContentDBService.process_full_document() instead
                """
                # DISABLED OLD CODE - Uncomment only for debugging
                # Step 4: Verify hash exists before proceeding (critical for transaction safety)
                # This ensures hash_id is valid even if there were transaction issues
                hash_verified = False
                hash_verify_attempts = 0
                max_hash_verify_attempts = 3
                
                while hash_verify_attempts < max_hash_verify_attempts and not hash_verified:
                    try:
                        # Verify hash exists in database (get_hash_by_id returns hash string or None)
                        # Use ContentDBService hashs_repo instead of db_hub.hash_operations
                        verified_hash_value = self.db_service.hashs_repo.get_hash_by_id(hash_id) if self.db_service else None
                        if verified_hash_value is None:
                            # Hash doesn't exist, need to recreate it
                            logger.warning(f"Hash ID {hash_id} not found in database, recreating hash...")
                            new_hash_id = self.db_service.create_hash(
                                file_hash, source_id, side_id
                            ) if self.db_service else None
                            if new_hash_id:
                                hash_id = new_hash_id
                                hash_verified = True
                            else:
                                hash_verify_attempts += 1
                                if hash_verify_attempts < max_hash_verify_attempts:
                                    logger.warning(f"Failed to recreate hash, retrying (attempt {hash_verify_attempts}/{max_hash_verify_attempts})...")
                                    time.sleep(0.5 * hash_verify_attempts)
                                    continue
                                else:
                                    error_msg = "Failed to verify or recreate hash after multiple attempts"
                                    handle_error(
                                        Exception(error_msg),
                                        category=ErrorCategory.DATABASE,
                                        severity=ErrorSeverity.HIGH,
                                        context={
                                            'operation': 'verify_hash',
                                            'hash_id': hash_id,
                                            'file_hash': file_hash[:16] + '...'
                                        },
                                        suggested_action='Check database connection and hash table'
                                    )
                                    if retry_count < max_retries:
                                        retry_count += 1
                                        logger.info(f"Retrying entire file storage (attempt {retry_count}/{max_retries})...")
                                        continue
                                    self.stats['files_failed'] += 1
                                    return None
                        else:
                            # Hash exists, verify it matches our file_hash (safety check)
                            if verified_hash_value != file_hash:
                                logger.warning(f"Hash ID {hash_id} exists but hash value mismatch. Expected: {file_hash[:16]}..., Got: {verified_hash_value[:16]}...")
                                # This shouldn't happen, but if it does, recreate hash
                                new_hash_id = self.db_service.create_hash(
                                    file_hash, source_id, side_id
                                )
                                if new_hash_id:
                                    hash_id = new_hash_id
                                    hash_verified = True
                                else:
                                    hash_verify_attempts += 1
                                    if hash_verify_attempts < max_hash_verify_attempts:
                                        continue
                                    else:
                                        self.stats['files_failed'] += 1
                                        return None
                            else:
                                hash_verified = True
                    except Exception as verify_error:
                        hash_verify_attempts += 1
                        if is_connection_error(verify_error):
                            logger.warning(f"Connection error verifying hash, attempting reconnect...")
                            self.db_hub._reconnect()
                        if hash_verify_attempts < max_hash_verify_attempts:
                            logger.warning(f"Error verifying hash, retrying (attempt {hash_verify_attempts}/{max_hash_verify_attempts}): {verify_error}")
                            time.sleep(0.5 * hash_verify_attempts)
                            continue
                        else:
                            error_msg = f"Failed to verify hash after multiple attempts: {verify_error}"
                            handle_error(
                                Exception(error_msg),
                                category=ErrorCategory.DATABASE_CONNECTION if is_connection_error(verify_error) else ErrorCategory.DATABASE,
                                severity=ErrorSeverity.HIGH,
                                context={
                                    'operation': 'verify_hash',
                                    'hash_id': hash_id,
                                    'file_hash': file_hash[:16] + '...'
                                },
                                suggested_action='Check database connection'
                            )
                            if retry_count < max_retries:
                                retry_count += 1
                                logger.info(f"Retrying entire file storage (attempt {retry_count}/{max_retries})...")
                                continue
                            self.stats['files_failed'] += 1
                            return None
                
                if not hash_verified:
                    self.stats['files_failed'] += 1
                    return None
                
                # Step 5: Extract coordinates if available
                coordinates = self._extract_coordinates(content)
                
                # Step 6: Store metadata (with validation and retry)
                path_id = None
                metadata_retry_count = 0
                max_metadata_retries = 2
                
                # Prepare error message if content has errors
                error_message = None
                if has_content_error:
                    error_message = content.get('error', 'Unknown error')
                    if isinstance(error_message, str):
                        # Truncate if too long
                        error_message = error_message[:10000] if len(error_message) > 10000 else error_message
                
                while metadata_retry_count <= max_metadata_retries and path_id is None:
                    try:
                        path_id = self.db_hub.path_operations.store_metadata(
                            file_info, hash_id, file_status='Unread', coordinates=coordinates, error_message=error_message
                        )
                        if not path_id:
                            if metadata_retry_count < max_metadata_retries:
                                metadata_retry_count += 1
                                logger.warning(f"Metadata storage returned None, retrying (attempt {metadata_retry_count}/{max_metadata_retries})...")
                                time.sleep(0.5 * metadata_retry_count)
                                continue
                            else:
                                error_msg = "Failed to store metadata after multiple attempts"
                                handle_error(
                                    Exception(error_msg),
                                    category=ErrorCategory.DATABASE,
                                    severity=ErrorSeverity.HIGH,
                                    context={
                                        'operation': 'store_metadata',
                                        'file_path': file_info.get('path', 'unknown')[:100],
                                        'hash_id': hash_id
                                    },
                                    suggested_action='Check database connection and file_path uniqueness constraint'
                                )
                                if retry_count < max_retries:
                                    retry_count += 1
                                    logger.info(f"Retrying entire file storage (attempt {retry_count}/{max_retries})...")
                                    continue
                                self.stats['files_failed'] += 1
                                return None
                    except Exception as metadata_error:
                        if is_retryable_error(metadata_error) and metadata_retry_count < max_metadata_retries:
                            metadata_retry_count += 1
                            logger.warning(f"Retryable error storing metadata, retrying (attempt {metadata_retry_count}/{max_metadata_retries}): {metadata_error}")
                            # Trigger reconnection if it's a connection error
                            if is_connection_error(metadata_error):
                                logger.warning("Connection error detected, attempting reconnect...")
                                if not self.db_hub._reconnect():
                                    logger.error("Failed to reconnect after metadata error")
                                    # Still continue to retry if we haven't exhausted retries
                                    if metadata_retry_count <= max_metadata_retries:
                                        time.sleep(0.5 * metadata_retry_count)
                                        continue
                            else:
                                time.sleep(0.5 * metadata_retry_count)
                            continue
                        else:
                            handle_error(
                                metadata_error,
                                category=ErrorCategory.DATABASE_CONNECTION if is_connection_error(metadata_error) else ErrorCategory.DATABASE,
                                severity=ErrorSeverity.MEDIUM,
                                context={'operation': 'store_metadata', 'file_path': file_info.get('path', 'unknown')[:100]}
                            )
                            if retry_count < max_retries:
                                retry_count += 1
                                # Try to reconnect before retrying entire operation
                                if is_connection_error(metadata_error):
                                    logger.warning("Connection error in metadata storage, attempting reconnect before full retry...")
                                    self.db_hub._reconnect()
                                continue
                            self.stats['files_failed'] += 1
                            return None
                
                # Step 6: Verify path exists before storing content (critical for transaction safety)
                if path_id:
                    path_verified = False
                    path_verify_attempts = 0
                    max_path_verify_attempts = 3
                    
                    while path_verify_attempts < max_path_verify_attempts and not path_verified:
                        try:
                            # Verify path exists by trying to get it
                            verified_path = self.db_hub.path_operations.get_path_by_id(path_id)
                            if verified_path is None:
                                # Path doesn't exist, need to recreate metadata
                                logger.warning(f"Path ID {path_id} not found in database, recreating metadata...")
                                # Recreate metadata with verified hash_id
                                new_path_id = self.db_hub.path_operations.store_metadata(
                                    file_info, hash_id, file_status='Unread', coordinates=coordinates, error_message=error_message
                                )
                                if new_path_id:
                                    path_id = new_path_id
                                    path_verified = True
                                else:
                                    path_verify_attempts += 1
                                    if path_verify_attempts < max_path_verify_attempts:
                                        logger.warning(f"Failed to recreate path, retrying (attempt {path_verify_attempts}/{max_path_verify_attempts})...")
                                        time.sleep(0.5 * path_verify_attempts)
                                        continue
                                    else:
                                        logger.error(f"Failed to verify or recreate path after multiple attempts, skipping content storage")
                                        path_id = None  # Mark as failed so we skip content storage
                                        break
                            else:
                                path_verified = True
                        except Exception as verify_error:
                            path_verify_attempts += 1
                            if is_connection_error(verify_error):
                                logger.warning(f"Connection error verifying path, attempting reconnect...")
                                self.db_hub._reconnect()
                            if path_verify_attempts < max_path_verify_attempts:
                                logger.warning(f"Error verifying path, retrying (attempt {path_verify_attempts}/{max_path_verify_attempts}): {verify_error}")
                                time.sleep(0.5 * path_verify_attempts)
                                continue
                            else:
                                logger.error(f"Failed to verify path after multiple attempts: {verify_error}, skipping content storage")
                                path_id = None  # Mark as failed so we skip content storage
                                break
                
                # Step 7: Extract and store content (skip if content has errors or path verification failed)
                text = None
                text_length = 0
                content_stored = False
                
                if path_id and not has_content_error:
                    logger.info(f"Extracting text content for path_id {path_id}, file: {file_info.get('path', 'unknown')[:100]}")
                    text = self._extract_text_from_content(content)
                    
                    if text:
                        text_length = len(text)
                        logger.info(f"Extracted {text_length} characters of text for path_id {path_id}")
                        
                        success = self._store_content_pipeline(text, path_id)
                        if success:
                            content_stored = True
                            logger.info(f"Content successfully stored for path_id {path_id} ({text_length} chars)")
                            # Update status to 'Read' (non-critical, so wrap in try-except)
                            try:
                                if not self.db_hub._check_connection_health():
                                    self.db_hub._reconnect()
                                self.db_hub.path_operations.update_file_status(path_id, 'Read')
                            except Exception as status_error:
                                logger.warning(f"Failed to update file status to 'Read' for path_id {path_id}: {status_error}")
                                # Don't fail the operation - file is stored, just status update failed
                        else:
                            logger.warning(f"Content storage failed for path_id {path_id}, but metadata was stored")
                    else:
                        logger.warning(f"No text extracted from content for path_id {path_id}. Content may be empty or binary.")

                else:
                    # File has content error - error message already stored in metadata step
                    logger.info(f"Metadata stored for file with content error, path_id: {path_id}, error: {error_message}")
                
                # Step 8: Title.
                #
                # _store_title_pipeline was removed. It called
                # self.db_hub.word_operations and .title_operations, neither of
                # which exists on DatabaseHub, so it raised AttributeError on
                # every file with a title, logged it, and always returned False.
                # Titles are stored by the content path instead
                # (contents_db_service.create_title_content), which is verified
                # to write titles_content rows. Keeping the local so the
                # "Stored Components" report below is unchanged in shape.
                title = self._extract_title(result, file_info)
                title_stored = False
                
                self.stats['files_stored'] += 1
                self.stats['files_processed'] += 1
                
                # ========== STORAGE COMPLETE - CLEAR SUCCESS MESSAGE ==========
                # This message appears AFTER all storage operations are complete
                file_name = file_info.get('name', 'unknown')
                file_path = file_info.get('path', 'unknown')
                file_size = file_info.get('size_bytes', 0)
                file_size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                
                # Build comprehensive storage confirmation message
                storage_details = []
                storage_details.append(f"✅ FILE SUCCESSFULLY STORED IN DATABASE")
                storage_details.append(f"   File: {file_name}")
                storage_details.append(f"   Path ID: {path_id}")
                storage_details.append(f"   Source: {effective_source_name} (ID: {source_id})")
                storage_details.append(f"   Side: {effective_side_name} (ID: {side_id})")
                storage_details.append(f"   Hash: {file_hash[:16]}...")
                
                if file_size_mb > 0:
                    storage_details.append(f"   Size: {file_size_mb:.2f} MB ({file_size:,} bytes)")
                
                # Indicate what was stored
                stored_components = ["Metadata"]
                if content_stored and text:
                    stored_components.append(f"Content ({text_length:,} chars)")
                elif path_id and not has_content_error:
                    stored_components.append("Content (empty)")
                if title_stored:
                    stored_components.append("Title")
                if has_content_error:
                    stored_components.append("Error Information")
                
                storage_details.append(f"   Stored Components: {', '.join(stored_components)}")
                storage_details.append(f"   Status: {'Read' if content_stored and text else 'Unread'}")
                storage_details.append(f"   Database Record: paths.id = {path_id}")
                
                # Log the complete message
                success_message = "\n".join(storage_details)
                logger.info(success_message)
                print(success_message)  # Also print to console for visibility
                
                return path_id
                """  # End of disabled old code block
                
            except Exception as e:
                # Use improved error detection from error_handling module
                if is_connection_error(e):
                    # Connection errors - try to reconnect
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.MEDIUM if retry_count < max_retries else ErrorSeverity.HIGH,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action='Attempting to reconnect and retry' if retry_count < max_retries else 'Check database server status'
                    )
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"Attempting to reconnect (attempt {retry_count}/{max_retries})...")
                        if self.db_hub._reconnect():
                            # Wait a bit before retrying
                            time.sleep(1.0)
                            continue
                        else:
                            logger.error(f"Failed to reconnect, will retry entire operation")
                            time.sleep(2.0 * retry_count)  # Exponential backoff
                            continue
                    
                    handle_error(
                        Exception(f"Failed to reconnect after {retry_count} attempts"),
                        category=ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.HIGH,
                        context={'operation': '_store_file_sync', 'file_path': file_info.get('path', 'unknown')[:100] if file_info else None}
                    )
                    self.stats['files_failed'] += 1
                    return None
                elif is_retryable_error(e) and retry_count < max_retries:
                    # Other retryable errors
                    retry_count += 1
                    wait_time = 1.0 * (2 ** (retry_count - 1))  # Exponential backoff
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE,
                        severity=ErrorSeverity.MEDIUM,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action=f'Retrying operation in {wait_time:.1f}s (attempt {retry_count}/{max_retries})'
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    # Non-retryable errors or max retries reached
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE if not is_connection_error(e) else ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.HIGH,
                        context={
                            'operation': '_store_file_sync',
                            'file_path': file_info.get('path', 'unknown')[:100] if file_info else None,
                            'retry_count': retry_count,
                            'max_retries': max_retries
                        },
                        suggested_action='Check error details and database state' if retry_count >= max_retries else None
                    )
                    self.stats['files_failed'] += 1
                    return None
        
        # If we get here, all retries failed
        self.stats['files_failed'] += 1
        return None
    
    def check_duplicate_for_pipeline(self, file_hash: str, source_id: Optional[int] = None, side_id: Optional[int] = None) -> Tuple[bool, Optional[int]]:
        """
        Check if file hash already exists.
        
        Uses ContentDBService for hash checking, with fallback to db_hub if available.
        """
        # Source and side IDs are MANDATORY - must be explicitly provided
        if source_id is None or side_id is None:
            logger.error("source_id and side_id are MANDATORY for hash checking - no defaults allowed")
            return False, None
        
        # Try using ContentDBService first
        try:
            hash_exists = self.db_service.hash_exists(file_hash, source_id)
            if hash_exists:
                # Hash exists, check for duplicate path using hashs_repo
                try:
                    path_id = self.db_service.hashs_repo.check_duplicate(file_hash, source_id, side_id)
                    if path_id:
                        return True, path_id
                    # Hash exists but no path_id found - might be from different side
                    return True, None
                except Exception as repo_error:
                    logger.warning(f"Error checking duplicate with hashs_repo: {repo_error}")
                    return True, None  # Hash exists but can't determine path_id
            return False, None
        except Exception as e:
            logger.warning(f"Error checking hash with ContentDBService: {e}")
            # Try direct hashs_repo access as fallback
            try:
                if self.db_service.hashs_repo.hash_exists(file_hash, source_id, side_id):
                    path_id = self.db_service.hashs_repo.check_duplicate(file_hash, source_id, side_id)
                    return True, path_id if path_id else None
            except Exception as repo_error:
                logger.warning(f"Fallback hash check also failed: {repo_error}")
            return False, None
    
    def _extract_coordinates(self, content: Dict) -> Optional[str]:
        """
        Extract GPS coordinates from content
        
        Handles multiple coordinate formats:
        - Direct location dict with coordinates string
        - Location dict with latitude/longitude floats
        - Coordinates in metadata
        """
        try:
            # Check for location data in images (from EXIF GPS data)
            location = content.get('location')
            if location and isinstance(location, dict):
                # Try coordinates string first (format: "lat, lon")
                coords = location.get('coordinates')
                if coords:
                    return str(coords)
                
                # Try latitude/longitude floats
                lat = location.get('latitude')
                lon = location.get('longitude')
                if lat is not None and lon is not None:
                    try:
                        return f"{float(lat):.6f}, {float(lon):.6f}"
                    except (ValueError, TypeError):
                        pass
            
            # Check for coordinates in metadata
            coords = content.get('coordinates')
            if coords:
                return str(coords)
            
            # Check for GPS coordinates in metadata
            gps = content.get('gps')
            if gps and isinstance(gps, dict):
                lat = gps.get('latitude')
                lon = gps.get('longitude')
                if lat is not None and lon is not None:
                    try:
                        return f"{float(lat):.6f}, {float(lon):.6f}"
                    except (ValueError, TypeError):
                        pass
        
        except Exception as e:
            logger.debug(f"Error extracting coordinates: {e}")
        
        return None
    
    def _extract_date_from_text(self, text: str, processor) -> Optional[date]:
        """
        Extract the first date mentioned in content text.
        
        content_date stores a date mentioned in the content itself.
        If no date is mentioned, it will be empty (None).
        
        Args:
            text: Text content to search for dates
            processor: ContentProcessor instance with date patterns
        
        Returns:
            date object if date found, None otherwise
        """
        if not text or not processor:
            return None
        
        try:
            from datetime import datetime
            
            # Extract dates using ContentProcessor patterns
            dates_found = []
            
            # Try ISO date pattern first (most reliable)
            for match in processor.patterns['date_iso'].finditer(text):
                date_str = match.group(0)
                try:
                    # Parse ISO format: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
                    date_str_clean = date_str.replace('/', '-').replace('.', '-')
                    parts = date_str_clean.split('-')
                    if len(parts) == 3:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        parsed_date = date(year, month, day)
                        dates_found.append(parsed_date)
                        break  # Use first valid date found
                except (ValueError, IndexError):
                    continue
            
            # If no ISO date found, try comprehensive date pattern
            if not dates_found:
                for match in processor.patterns['date'].finditer(text):
                    date_str = match.group(0)
                    try:
                        # Try to parse various date formats
                        # Remove common separators and try parsing
                        date_str_clean = date_str.strip()
                        
                        # Try ISO format first
                        if '/' in date_str_clean or '-' in date_str_clean or '.' in date_str_clean:
                            # Try to extract YYYY-MM-DD format
                            import re
                            iso_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', date_str_clean)
                            if iso_match:
                                year = int(iso_match.group(1))
                                month = int(iso_match.group(2))
                                day = int(iso_match.group(3))
                                parsed_date = date(year, month, day)
                                dates_found.append(parsed_date)
                                break
                        
                        # Try parsing with dateutil if available (handles more formats)
                        try:
                            from dateutil import parser
                            parsed_date = parser.parse(date_str_clean, fuzzy=False).date()
                            dates_found.append(parsed_date)
                            break
                        except ImportError:
                            # dateutil not available, skip
                            pass
                        except (ValueError, TypeError):
                            # Parsing failed, continue
                            continue
                    except (ValueError, IndexError, TypeError):
                        continue
            
            # Return first valid date found, or None
            return dates_found[0] if dates_found else None
            
        except Exception as e:
            logger.debug(f"Error extracting date from text: {e}")
            return None
    
    def _extract_title(self, result: Dict, file_info: Dict) -> str:
        """Extract title from result or filename"""
        # Try to get title from content
        content = result.get('Content', {})
        
        # Check various title fields
        title = (content.get('title') or
                content.get('subject') or
                content.get('name') or
                file_info.get('name', 'untitled'))
        
        if isinstance(title, list):
            title = title[0] if title else 'untitled'
        
        return str(title)
    
    def _extract_text_from_content(self, content: Dict) -> str:
        """
        Extract text from content dictionary (all types)
        PRESERVES SPATIAL ORDER through structured extraction based on location
        
        ORGANIZATION STRATEGY:
        - Content is extracted in spatial order: top-to-bottom, left-to-right
        - Table/Excel cells are separated by TAB characters (\t) for clear parsing
        - This enables accurate display reconstruction of tables with proper column boundaries
        - Headers and metadata use pipe (|) or newline separators
        - All content remains text-based for storage compatibility
        - Spatial coordinates are used when available to ensure proper reading order
        
        Args:
            content: Content dictionary from file processing
        
        Returns:
            Combined text string in spatial order with organized delimiters
        """
        text_parts = []
        
        try:
            # Use ordered list to preserve document structure and spatial location
            # Format: (spatial_position, type, index, text, coordinates)
            # spatial_position: numeric value for sorting (page_number * 1000000 + y_coord * 1000 + x_coord)
            # coordinates: optional dict with x, y, width, height for spatial reference
            ordered_content = []
            
            # 1. IMAGES (OCR text only - no metadata)
            # Store ONLY the OCR text, preserving formatting
            # Detect images by checking for OCR-related keys (ocr_attempted, ocr_successful, ocr_language)
            is_image_content = (
                'ocr_attempted' in content or 
                'ocr_successful' in content or 
                'ocr_language' in content or
                'extraction_info' in content
            )
            
            if is_image_content:
                # Extract ONLY the OCR text - no metadata
                img_text = content.get('text', '')
                ocr_coords_data = None
                
                if 'ocr_coordinates' in content and isinstance(content['ocr_coordinates'], list):
                    ocr_coords_data = content['ocr_coordinates']
                
                # Get extraction info for logging
                extraction_info = content.get('extraction_info', {})
                ocr_attempted = content.get('ocr_attempted', False)
                ocr_successful = content.get('ocr_successful', False)
                ocr_language = content.get('ocr_language', 'unknown')
                
                # Store OCR text if extracted (formatting preserved)
                if img_text and img_text.strip():
                    text_to_store = img_text.rstrip()
                    text_length = len(text_to_store)
                    word_count = len(text_to_store.split())
                    coord_count = len(ocr_coords_data) if ocr_coords_data else 0
                    
                    logger.info(
                        f"[STORAGE] 📝 Image OCR Content - "
                        f"Extracted: {text_length} chars, {word_count} words | "
                        f"Coordinates: {coord_count} words | "
                        f"Language: {ocr_language} | "
                        f"Attempted: {ocr_attempted} | "
                        f"Successful: {ocr_successful}"
                    )
                    
                    # Store only OCR text (no metadata)
                    ordered_content.append((0, 'direct_text', 0, text_to_store, ocr_coords_data))
                else:
                    # Log why no text was stored
                    reason = extraction_info.get('reason', 'unknown')
                    error = extraction_info.get('error', '')
                    skipped = extraction_info.get('skipped', False)
                    
                    if skipped:
                        logger.info(
                            f"[STORAGE] ⚠️  Image OCR Content - Skipped: {extraction_info.get('skip_reason', 'unknown')}"
                        )
                    elif error:
                        logger.warning(
                            f"[STORAGE] ⚠️  Image OCR Content - Error: {error}"
                        )
                    else:
                        logger.info(
                            f"[STORAGE] ⚠️  Image OCR Content - No text extracted | "
                            f"Attempted: {ocr_attempted} | "
                            f"Successful: {ocr_successful} | "
                            f"Reason: {reason}"
                        )
            
            # 2. EXTRACTED IMAGES (from Office docs)
            if 'extracted_images' in content:
                for idx, img in enumerate(content.get('extracted_images', [])):
                    if isinstance(img, dict) and 'text' in img:
                        # Spatial position based on image index (maintains extraction order)
                        spatial_pos = 1000000 + idx * 1000
                        ordered_content.append((spatial_pos, 'extracted_image', idx, img['text'], None))
            
            # 3. EMAIL CONTENT (from email_content key - processed by _process_email_result)
            if 'email_content' in content:
                email_data = content['email_content']
                
                # Single message dict
                if isinstance(email_data, dict):
                    msg_text = self._extract_email_message_text(email_data)
                    if msg_text:
                        # Email messages at position 2000000 (maintains chronological order)
                        ordered_content.append((2000000, 'email_message', 0, msg_text, None))
                    else:
                        # Log if message has no extractable text (helps diagnose PST issues)
                        logger.debug(f"Email message has no extractable text: {email_data.get('subject', 'N/A')[:500]}")
                
                # Multiple messages list (PST/MBOX files)
                elif isinstance(email_data, list):
                    messages_processed = 0
                    messages_with_content = 0
                    for idx, msg in enumerate(email_data):
                        messages_processed += 1
                        msg_text = self._extract_email_message_text(msg)
                        if msg_text:
                            # Maintain message order: 2000000 + index * 100
                            spatial_pos = 2000000 + idx * 100
                            ordered_content.append((spatial_pos, 'email_message', idx, msg_text, None))
                            messages_with_content += 1
                        else:
                            # Log if message has no extractable text
                            logger.debug(f"Email message {idx} has no extractable text: {msg.get('subject', 'N/A')[:500]}")
                    
                    # Log summary for PST/MBOX files
                    if messages_processed > 0:
                        logger.info(f"Processed {messages_processed} email messages, {messages_with_content} with content")
            
            # 4. EMAIL MESSAGE (direct from email readers - EML/MSG single message)
            if 'message' in content and isinstance(content['message'], dict):
                msg_text = self._extract_email_message_text(content['message'])
                if msg_text:
                    ordered_content.append((2000000, 'email_message', 0, msg_text, None))
            
            # 5. EMAIL MESSAGES (from messages key - MBOX/PST multiple messages)
            if 'messages' in content and isinstance(content['messages'], list):
                for idx, msg in enumerate(content['messages']):
                    msg_text = self._extract_email_message_text(msg)
                    if msg_text:
                        # Maintain message order: 2000000 + index * 100
                        spatial_pos = 2000000 + idx * 100
                        ordered_content.append((spatial_pos, 'email_message', idx, msg_text, None))
            
            # 6. PDF PAGES
            if 'pages' in content and isinstance(content['pages'], list):
                # Extract PDF metadata first (if available)
                pdf_metadata_parts = []
                if 'num_pages' in content:
                    pdf_metadata_parts.append(f"Total Pages: {content['num_pages']}")
                if 'is_encrypted' in content and content['is_encrypted']:
                    pdf_metadata_parts.append("Encrypted: Yes")
                if 'ocr_used' in content:
                    pdf_metadata_parts.append(f"OCR Used: {'Yes' if content['ocr_used'] else 'No'}")
                if 'ocr_languages' in content:
                    pdf_metadata_parts.append(f"OCR Languages: {', '.join(content['ocr_languages'])}")
                if 'metadata' in content and isinstance(content['metadata'], dict):
                    meta = content['metadata']
                    if meta.get('title'):
                        pdf_metadata_parts.append(f"Title: {meta['title']}")
                    if meta.get('author'):
                        pdf_metadata_parts.append(f"Author: {meta['author']}")
                    if meta.get('subject'):
                        pdf_metadata_parts.append(f"Subject: {meta['subject']}")
                    if meta.get('creator'):
                        pdf_metadata_parts.append(f"Creator: {meta['creator']}")
                    if meta.get('producer'):
                        pdf_metadata_parts.append(f"Producer: {meta['producer']}")
                
                if pdf_metadata_parts:
                    # Metadata at position 0 (before all pages)
                    ordered_content.append((0, 'pdf_metadata', 0, '\n'.join(pdf_metadata_parts), None))
                
                # Sort pages by page_number to ensure correct order
                sorted_pages = sorted(
                    [p for p in content['pages'] if isinstance(p, dict)],
                    key=lambda x: x.get('page_number', 0)
                )
                
                for page in sorted_pages:
                    # Extract page text - handle None, empty strings, and ensure string type
                    page_text = page.get('text')
                    if page_text is None:
                        page_text = ""
                    else:
                        page_text = str(page_text)
                    
                    # Extract page metadata
                    page_meta_parts = []
                    page_number = page.get('page_number', 0)
                    if page_number:
                        page_meta_parts.append(f"Page {page_number}")
                    
                    method = page.get('method', '')
                    if method:
                        page_meta_parts.append(f"Method: {method}")
                    
                    text_length = page.get('text_length', 0)
                    if text_length:
                        page_meta_parts.append(f"Length: {text_length} chars")
                    
                    error = page.get('error')
                    if error:
                        page_meta_parts.append(f"Error: {error}")
                    
                    # Combine page metadata with text
                    if page_meta_parts:
                        page_header = ' | '.join(page_meta_parts) + '\n'
                        page_text = page_header + page_text
                    
                    # Calculate spatial position: page_number * 1000000 ensures pages are ordered
                    # This ensures pages are processed in order (1, 2, 3, ...)
                    spatial_position = page_number * 1000000 if page_number else 3000000
                    
                    # Include all pages (even empty ones) to preserve page order
                    # Format: (spatial_position, type, index, text, coordinates)
                    ordered_content.append((spatial_position, 'pdf_page', page_number, page_text, None))
            
            # 7. EXCEL/ODS SHEETS
            if 'sheets' in content and isinstance(content['sheets'], dict):
                # Process sheets in order (preserve sheet order from document)
                sheet_items = list(content['sheets'].items())
                for sheet_idx, (sheet_name, sheet_data) in enumerate(sheet_items):
                    if isinstance(sheet_data, dict):
                        # Extract sheet name and metadata as header
                        sheet_header_parts = []
                        if sheet_name:
                            sheet_header_parts.append(f"Sheet: {sheet_name}")
                        
                        # Add metadata if available
                        if 'max_row' in sheet_data:
                            sheet_header_parts.append(f"Rows: {sheet_data['max_row']}")
                        if 'max_column' in sheet_data:
                            sheet_header_parts.append(f"Columns: {sheet_data['max_column']}")
                        
                        sheet_header = '\n'.join(sheet_header_parts) + '\n' if sheet_header_parts else ""
                        
                        # Extract headers if available
                        # Use tab delimiter for clear column separation (easier to parse for display)
                        headers_text = ""
                        if 'headers' in sheet_data and isinstance(sheet_data['headers'], list):
                            header_cells = [str(h) if h is not None else '' for h in sheet_data['headers']]
                            headers_text = '\t'.join(header_cells) + '\n'
                        
                        # Extract data if available - ensure row order is preserved
                        sheet_text = ""
                        if 'data' in sheet_data:
                            sheet_text = self._extract_sheet_text(sheet_data['data'])
                        
                        # Combine all parts
                        combined_sheet_text = sheet_header + headers_text + sheet_text
                        
                        # Calculate spatial position: 4000000 + sheet_index * 10000
                        # This ensures sheets are processed in order, and rows within sheets maintain order
                        spatial_position = 4000000 + sheet_idx * 10000
                        
                        # Include all sheets (even empty ones) to preserve sheet order
                        # Format: (spatial_position, type, index, text, coordinates)
                        ordered_content.append((spatial_position, 'excel_sheet', sheet_idx, combined_sheet_text, None))
            
            # 7.5. WORD DOCUMENT ELEMENTS (in original order - paragraphs and tables interleaved)
            # This preserves the exact location of text, tables, and other elements as they appear in the document
            if 'elements' in content and isinstance(content['elements'], list):
                # Process elements in their original document order
                for element in content['elements']:
                    if not isinstance(element, dict):
                        continue
                    
                    element_type = element.get('type', '')
                    element_position = element.get('position', 0)
                    
                    if element_type == 'paragraph':
                        para_text = element.get('text', '')
                        style = element.get('style', '')
                        
                        # Add style information if not Normal
                        if style and style != 'Normal':
                            para_text = f"[Style: {style}] {para_text}"
                        
                        # Calculate spatial position: 5000000 + position * 10
                        # This ensures paragraphs appear in document order
                        spatial_position = 5000000 + element_position * 10
                        ordered_content.append((spatial_position, 'word_paragraph', element.get('index', 0), para_text, None))
                    
                    elif element_type == 'table':
                        table_number = element.get('table_number', 0)
                        table_header_parts = [f"Table {table_number}"]
                        
                        # Extract rows if available
                        table_text = ""
                        if 'rows' in element and isinstance(element['rows'], list):
                            table_text = self._extract_table_text(element['rows'])
                        
                        table_header = ' | '.join(table_header_parts) + '\n' if table_header_parts else ""
                        combined_table_text = table_header + table_text if table_text else table_header
                        
                        # Calculate spatial position: 5000000 + position * 10 + 1
                        # Tables get position + 1 to appear after paragraphs at same position
                        spatial_position = 5000000 + element_position * 10 + 1
                        ordered_content.append((spatial_position, 'word_table', table_number - 1, combined_table_text, None))
            
            # 8. TABLES (legacy format - for backward compatibility)
            if 'tables' in content and isinstance(content['tables'], list) and 'elements' not in content:
                for idx, table in enumerate(content['tables']):
                    if isinstance(table, dict):
                        # Extract table caption/title and number if available
                        table_header_parts = []
                        table_number = table.get('table_number', idx + 1)
                        table_header_parts.append(f"Table {table_number}")
                        
                        if 'caption' in table:
                            table_header_parts.append(f"Caption: {table['caption']}")
                        elif 'title' in table:
                            table_header_parts.append(f"Title: {table['title']}")
                        
                        table_header = ' | '.join(table_header_parts) + '\n' if table_header_parts else ""
                        
                        # Extract rows if available
                        if 'rows' in table:
                            table_text = self._extract_table_text(table['rows'])
                            combined_table_text = table_header + table_text if table_text else table_header
                            # Include all tables (even empty ones) to preserve table order
                            spatial_position = 5000000 + idx * 10000
                            ordered_content.append((spatial_position, 'table', idx, combined_table_text, None))
                        elif table_header.strip():
                            # Table exists but has no rows - still include header
                            spatial_position = 5000000 + idx * 10000
                            ordered_content.append((spatial_position, 'table', idx, table_header, None))
            
            # 9. POWERPOINT/ODP SLIDES
            if 'slides' in content and isinstance(content['slides'], list):
                # Extract total slides count if available
                if 'total_slides' in content:
                    ordered_content.append((6000000, 'slides_metadata', 0, f"Total Slides: {content['total_slides']}", None))
                
                for slide_idx, slide in enumerate(content['slides']):
                    if not isinstance(slide, dict):
                        continue
                    
                    slide_number = slide.get('slide_number', slide_idx + 1)
                    
                    # Process slide elements in their original order (if available)
                    if 'elements' in slide and isinstance(slide['elements'], list):
                        # New format: elements are ordered by spatial position
                        for element in slide['elements']:
                            if not isinstance(element, dict):
                                continue
                            
                            element_type = element.get('type', '')
                            element_position = element.get('position', 0)
                            
                            # Calculate spatial position: slide_number * 100000 + element_position * 100
                            spatial_position = 6000000 + slide_number * 100000 + element_position * 100
                            
                            if element_type == 'text' or element_type == 'text_frame':
                                text_content = element.get('text', '')
                                if text_content:
                                    ordered_content.append((spatial_position, 'slide_text', slide_idx, text_content, None))
                            
                            elif element_type == 'table':
                                table_number = element.get('table_number', 0)
                                table_header = f"Table {table_number}\n"
                                
                                table_text = ""
                                if 'rows' in element and isinstance(element['rows'], list):
                                    table_text = self._extract_table_text(element['rows'])
                                
                                combined_table_text = table_header + table_text if table_text else table_header
                                # Tables get +1 to appear after text at same position
                                ordered_content.append((spatial_position + 1, 'slide_table', slide_idx, combined_table_text, None))
                            
                            elif element_type == 'image':
                                image_name = element.get('image_name', '')
                                image_text = f"[Image: {image_name}]"
                                # Images get +2 to appear after tables at same position
                                ordered_content.append((spatial_position + 2, 'slide_image', slide_idx, image_text, None))
                    
                    # Legacy format: extract from texts array (for backward compatibility)
                    else:
                        slide_header_parts = [f"Slide {slide_number}"]
                        slide_texts = []
                        
                        if 'title' in slide:
                            slide_texts.append(f"Title: {slide['title']}")
                        if 'texts' in slide:
                            slide_texts.extend(str(t) for t in slide['texts'] if t)
                        if 'text' in slide:
                            slide_texts.append(str(slide['text']))
                        if 'notes' in slide:
                            slide_texts.append(f"Notes: {slide['notes']}")
                        
                        slide_header = ' | '.join(slide_header_parts) + '\n' if slide_header_parts else ""
                        slide_text = '\n'.join(slide_texts) if slide_texts else ""
                        combined_slide_text = slide_header + slide_text
                        
                        # Spatial position for legacy format
                        spatial_position = 6000000 + slide_number * 100000
                        ordered_content.append((spatial_position, 'slide', slide_idx, combined_slide_text, None))
            
            # 10. WORD/ODT PARAGRAPHS (legacy format - only if elements not available)
            if 'paragraphs' in content and 'elements' not in content:
                paragraphs = content['paragraphs']
                
                # List of paragraph dicts
                if isinstance(paragraphs, list):
                    for idx, para in enumerate(paragraphs):
                        if isinstance(para, dict):
                            para_text = para.get('text', '')
                            # Extract paragraph style if available
                            style = para.get('style', '')
                            if style and style != 'Normal':
                                para_text = f"[Style: {style}] {para_text}"
                        else:
                            para_text = str(para)
                        
                        # Include all paragraphs (even empty ones) to preserve document structure
                        # Empty paragraphs represent spacing/formatting in the document
                        if para_text is not None:
                            spatial_position = 5000000 + idx * 10
                            ordered_content.append((spatial_position, 'paragraph', idx, para_text, None))
                
                # Also handle paragraphs as simple list of strings (from DOC files)
                elif isinstance(paragraphs, list) and paragraphs and isinstance(paragraphs[0], str):
                    for idx, para_text in enumerate(paragraphs):
                        if para_text is not None:
                            spatial_position = 5000000 + idx * 10
                            ordered_content.append((spatial_position, 'paragraph', idx, str(para_text), None))
            
            # 11. DIRECT TEXT CONTENT (from text files, DOC files, etc.)
            if 'content' in content:
                direct_content = content['content']
                if isinstance(direct_content, str):
                    # Add text file statistics if available
                    stats_parts = []
                    if 'line_count' in content:
                        stats_parts.append(f"Lines: {content['line_count']}")
                    if 'character_count' in content:
                        stats_parts.append(f"Characters: {content['character_count']}")
                    if 'word_count' in content:
                        stats_parts.append(f"Words: {content['word_count']}")
                    if 'non_empty_lines' in content:
                        stats_parts.append(f"Non-empty Lines: {content['non_empty_lines']}")
                    if 'encoding_used' in content:
                        stats_parts.append(f"Encoding: {content['encoding_used']}")
                    
                    if stats_parts:
                        stats_header = ' | '.join(stats_parts) + '\n'
                        direct_content = stats_header + direct_content
                    
                    if direct_content.strip():
                        ordered_content.append((8, 'direct_content', 0, direct_content))
            
            # 12. LINES (from text files)
            if 'lines' in content and isinstance(content['lines'], list):
                # Include all lines (even empty ones) to preserve file structure
                lines_text = '\n'.join(str(line) for line in content['lines'])
                ordered_content.append((9, 'lines', 0, lines_text))
            
            # 13. READABLE CONTENT (ICS files)
            if 'readable_content' in content:
                readable = content['readable_content']
                if isinstance(readable, str) and readable.strip():
                    ordered_content.append((10, 'readable_content', 0, readable))
            
            # 13b. ICS EVENTS, TODOS, JOURNALS (structured data)
            if 'events' in content and isinstance(content['events'], list):
                for idx, event in enumerate(content['events']):
                    if isinstance(event, dict):
                        event_parts = []
                        if event.get('summary'):
                            event_parts.append(f"Event: {event['summary']}")
                        if event.get('description'):
                            event_parts.append(f"Description: {event['description']}")
                        if event.get('location'):
                            event_parts.append(f"Location: {event['location']}")
                        if event.get('dtstart'):
                            event_parts.append(f"Start: {event['dtstart']}")
                        if event.get('dtend'):
                            event_parts.append(f"End: {event['dtend']}")
                        if event.get('organizer'):
                            event_parts.append(f"Organizer: {event['organizer']}")
                        if event.get('attendee'):
                            event_parts.append(f"Attendees: {', '.join(event['attendee'])}")
                        if event_parts:
                            ordered_content.append((10, 'ics_event', idx, '\n'.join(event_parts)))
            
            if 'todos' in content and isinstance(content['todos'], list):
                for idx, todo in enumerate(content['todos']):
                    if isinstance(todo, dict):
                        todo_parts = []
                        if todo.get('summary'):
                            todo_parts.append(f"Todo: {todo['summary']}")
                        if todo.get('description'):
                            todo_parts.append(f"Description: {todo['description']}")
                        if todo.get('due'):
                            todo_parts.append(f"Due: {todo['due']}")
                        if todo.get('status'):
                            todo_parts.append(f"Status: {todo['status']}")
                        if todo_parts:
                            ordered_content.append((10, 'ics_todo', idx, '\n'.join(todo_parts)))
            
            if 'journals' in content and isinstance(content['journals'], list):
                for idx, journal in enumerate(content['journals']):
                    if isinstance(journal, dict):
                        journal_parts = []
                        if journal.get('summary'):
                            journal_parts.append(f"Journal: {journal['summary']}")
                        if journal.get('description'):
                            journal_parts.append(f"Description: {journal['description']}")
                        if journal_parts:
                            ordered_content.append((10, 'ics_journal', idx, '\n'.join(journal_parts)))
            
            # 14. JSON/YAML DATA (convert to text)
            if 'data' in content:
                import json
                try:
                    data_text = json.dumps(content['data'], indent=2)
                    if data_text.strip():
                        ordered_content.append((11, 'json_data', 0, data_text))
                except:
                    pass
            
            # 15. EBOOK CHAPTERS
            if 'chapters' in content and isinstance(content['chapters'], list):
                # Extract e-book metadata first (if available)
                ebook_meta_parts = []
                if 'title' in content:
                    ebook_meta_parts.append(f"Title: {content['title']}")
                if 'author' in content:
                    ebook_meta_parts.append(f"Author: {content['author']}")
                if 'publisher' in content:
                    ebook_meta_parts.append(f"Publisher: {content['publisher']}")
                if 'language' in content:
                    ebook_meta_parts.append(f"Language: {content['language']}")
                if 'date' in content:
                    ebook_meta_parts.append(f"Date: {content['date']}")
                if 'description' in content:
                    ebook_meta_parts.append(f"Description: {content['description']}")
                if 'subject' in content:
                    ebook_meta_parts.append(f"Subject: {content['subject']}")
                if 'chapter_count' in content:
                    ebook_meta_parts.append(f"Chapters: {content['chapter_count']}")
                if 'total_words' in content:
                    ebook_meta_parts.append(f"Total Words: {content['total_words']}")
                
                if ebook_meta_parts:
                    ordered_content.append((12, 'ebook_metadata', 0, '\n'.join(ebook_meta_parts)))
                
                for idx, chapter in enumerate(content['chapters']):
                    if isinstance(chapter, dict):
                        # Extract chapter title if available
                        chapter_header_parts = []
                        chapter_id = chapter.get('id', f"Chapter {idx + 1}")
                        chapter_header_parts.append(f"Chapter ID: {chapter_id}")
                        
                        if 'title' in chapter:
                            chapter_header_parts.append(f"Title: {chapter['title']}")
                        elif 'name' in chapter:
                            chapter_header_parts.append(f"Name: {chapter['name']}")
                        
                        if 'length' in chapter:
                            chapter_header_parts.append(f"Length: {chapter['length']} chars")
                        if 'word_count' in chapter:
                            chapter_header_parts.append(f"Words: {chapter['word_count']}")
                        
                        chapter_header = ' | '.join(chapter_header_parts) + '\n\n' if chapter_header_parts else ""
                        
                        # Extract chapter text
                        chapter_text = chapter.get('text', '')
                        if chapter_text is not None:
                            combined_chapter_text = chapter_header + str(chapter_text)
                            # Include all chapters (even empty ones) to preserve chapter order
                            ordered_content.append((12, 'chapter', idx, combined_chapter_text))
                        elif chapter_header.strip():
                            # Chapter exists but has no text - still include header
                            ordered_content.append((12, 'chapter', idx, chapter_header))
            
            # 16. HTML TEXT CONTENT
            if 'text_content' in content:
                html_parts = []
                
                # Extract HTML title if available
                if 'title' in content:
                    html_parts.append(f"Title: {content['title']}")
                
                # Extract headings if available
                if 'headings' in content and isinstance(content['headings'], dict):
                    headings = content['headings']
                    if headings.get('h1'):
                        html_parts.append(f"H1: {' | '.join(headings['h1'])}")
                    if headings.get('h2'):
                        html_parts.append(f"H2: {' | '.join(headings['h2'])}")
                    if headings.get('h3'):
                        html_parts.append(f"H3: {' | '.join(headings['h3'])}")
                
                # Extract links if available
                if 'links' in content and isinstance(content['links'], list):
                    link_texts = []
                    for link in content['links'][:20]:  # Limit to first 20 links
                        if isinstance(link, dict):
                            href = link.get('href', '')
                            text = link.get('text', '')
                            if href:
                                link_texts.append(f"{text} -> {href}")
                    if link_texts:
                        html_parts.append(f"Links ({len(content['links'])} total):\n" + '\n'.join(link_texts))
                
                # Extract images if available
                if 'images' in content and isinstance(content['images'], list):
                    image_texts = []
                    for img in content['images'][:20]:  # Limit to first 20 images
                        if isinstance(img, dict):
                            src = img.get('src', '')
                            alt = img.get('alt', '')
                            if src:
                                image_texts.append(f"Image: {alt or 'No alt'} -> {src}")
                    if image_texts:
                        html_parts.append(f"Images ({len(content['images'])} total):\n" + '\n'.join(image_texts))
                
                # Add main text content
                html_text = content['text_content']
                if isinstance(html_text, str) and html_text.strip():
                    html_header = '\n'.join(html_parts) + '\n\n--- Content ---\n' if html_parts else ''
                    ordered_content.append((13, 'html_text', 0, html_header + html_text))
            
            # 17. CSV ROWS
            if 'rows' in content and isinstance(content['rows'], list):
                csv_text = self._extract_csv_text(content['rows'], content.get('headers', []))
                if csv_text:
                    ordered_content.append((14, 'csv_rows', 0, csv_text))
            
            # 18. DATABASE SCHEMA AND DATA
            if 'tables' in content and isinstance(content['tables'], list) and content.get('format') == 'SQLite':
                # This is a database file
                db_meta_parts = []
                if 'sqlite_version' in content:
                    db_meta_parts.append(f"SQLite Version: {content['sqlite_version']}")
                if 'table_count' in content:
                    db_meta_parts.append(f"Tables: {content['table_count']}")
                
                if db_meta_parts:
                    ordered_content.append((15, 'database_metadata', 0, '\n'.join(db_meta_parts)))
                
                for idx, table in enumerate(content['tables']):
                    if isinstance(table, dict):
                        table_parts = []
                        table_name = table.get('name', f"Table {idx + 1}")
                        table_parts.append(f"Table: {table_name}")
                        
                        if 'column_count' in table:
                            table_parts.append(f"Columns: {table['column_count']}")
                        if 'row_count' in table:
                            table_parts.append(f"Rows: {table['row_count']}")
                        
                        table_header = ' | '.join(table_parts) + '\n'
                        
                        # Extract column names
                        if 'columns' in table and isinstance(table['columns'], list):
                            col_names = [col.get('name', '') for col in table['columns'] if isinstance(col, dict)]
                            if col_names:
                                table_header += f"Columns: {', '.join(col_names)}\n"
                        
                        # Extract sample data
                        if 'sample_data' in table and isinstance(table['sample_data'], list):
                            sample_rows = []
                            for row in table['sample_data'][:10]:  # Limit to first 10 rows
                                if isinstance(row, (list, tuple)):
                                    # Use tab delimiter for clear cell separation (easier to parse for display)
                                    row_cells = [str(cell) if cell is not None else '' for cell in row]
                                    sample_rows.append('\t'.join(row_cells))
                            if sample_rows:
                                table_header += '\nSample Data:\n' + '\n'.join(sample_rows)
                        
                        ordered_content.append((15, 'database_table', idx, table_header))
            
            # Sort by: spatial_position → type → index (preserves spatial and structural order)
            # This ensures content is extracted in the correct spatial order:
            # - Pages are ordered by page number
            # - Sheets are ordered by sheet index
            # - Within each element, content maintains its original location-based order
            ordered_content.sort(key=lambda x: (
                x[0] if len(x) > 0 and isinstance(x[0], (int, float)) else 0,  # spatial_position
                x[1] if len(x) > 1 else '',  # type
                x[2] if len(x) > 2 and isinstance(x[2], (int, float)) else 0  # index
            ))
            
            # Combine all text in order (4th element is the text)
            text_parts = [item[3] if len(item) > 3 else '' for item in ordered_content]
            
            # Join with double newline for readability
            combined_text = '\n\n'.join(text_parts)
            
            # Log extraction summary for debugging
            if ordered_content:
                content_types = {}
                for item in ordered_content:
                    content_type = item[1]
                    content_types[content_type] = content_types.get(content_type, 0) + 1
                logger.info(f"Extracted content: {len(ordered_content)} items, types: {content_types}, total length: {len(combined_text)} chars")
            
            # Return text (preserve leading/trailing whitespace if it's meaningful)
            # Only strip if the entire text is whitespace
            if combined_text.strip():
                return combined_text
            else:
                # If all whitespace, return empty string
                return ""

        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""
        
    def _extract_email_message_text(self, msg: Dict) -> str:
        """Extract text from email message dict - comprehensive extraction"""
        parts = []
        
        # Add message index if available (for MBOX/PST)
        if 'message_index' in msg:
            parts.append(f"Message #{msg['message_index']}")
        
        # Add metadata fields
        if msg.get('from'):
            parts.append(f"From: {msg['from']}")
        if msg.get('to'):
            parts.append(f"To: {msg['to']}")
        if msg.get('subject'):
            parts.append(f"Subject: {msg['subject']}")
        if msg.get('date'):
            parts.append(f"Date: {msg['date']}")
        if msg.get('cc'):
            parts.append(f"CC: {msg['cc']}")
        if msg.get('bcc'):
            parts.append(f"BCC: {msg['bcc']}")
        if msg.get('message_id'):
            parts.append(f"Message-ID: {msg['message_id']}")
        
        # Add attachment info if available
        if 'attachment_count' in msg:
            parts.append(f"Attachments: {msg['attachment_count']}")
        if 'has_attachments' in msg and msg['has_attachments']:
            if 'attachments_folder' in msg:
                parts.append(f"Attachments Folder: {msg['attachments_folder']}")
        
        # Add source filepath if available
        if 'source_filepath' in msg:
            parts.append(f"Source: {msg['source_filepath']}")
        
        # Add content/body - check multiple possible keys
        content = msg.get('content') or msg.get('body') or msg.get('text') or ''
        if content:
            # Ensure content is a string
            if not isinstance(content, str):
                content = str(content)
            # Only add content section if content is not empty
            if content.strip():
                parts.append('\n--- Message Content ---\n' + content)
            else:
                # Log empty content for debugging
                logger.debug(f"Message has empty content field: {msg.get('subject', 'N/A')[:50]}")
        else:
            # Log if no content field found at all
            logger.debug(f"Message has no content field: {msg.get('subject', 'N/A')[:50]}")
        
        return '\n'.join(parts)
    
    def _extract_sheet_text(self, data: List[List]) -> str:
        """
        Extract text from Excel/ODS sheet data - comprehensive extraction
        Uses tab delimiters for clear cell separation to enable accurate display
        """
        text_parts = []
        
        if not data:
            return ""
        
        for row in data:
            # Handle both list of cells and other formats
            if isinstance(row, (list, tuple)):
                # Filter out None values and convert to strings
                # Use tab delimiter for clear cell separation (easier to parse for display)
                row_cells = [str(cell) if cell is not None else '' for cell in row]
                # Join with tab character for explicit cell boundaries
                row_text = '\t'.join(row_cells)
            else:
                # Single value row
                row_text = str(row) if row is not None else ""
            
            # Include all rows (even empty ones) to preserve structure
            text_parts.append(row_text)
        
        return '\n'.join(text_parts)
    
    def _extract_table_text(self, rows: List[List]) -> str:
        """
        Extract text from table rows
        Uses tab delimiters for clear cell separation to enable accurate display
        """
        return self._extract_sheet_text(rows)
    
    def _extract_csv_text(self, rows: List[List], headers: List) -> str:
        """
        Extract text from CSV data
        Uses tab delimiters for clear cell separation to enable accurate display
        """
        text_parts = []
        
        if headers:
            # Use tab delimiter for clear column separation
            header_cells = [str(h) if h is not None else '' for h in headers]
            text_parts.append('\t'.join(header_cells))
        
        for row in rows:
            # Use tab delimiter for clear cell separation
            row_cells = [str(cell) if cell is not None else '' for cell in row]
            row_text = '\t'.join(row_cells)
            if row_text.strip():
                text_parts.append(row_text)
        
        return '\n'.join(text_parts)
    
    def _store_content_pipeline(self, text: str, path_id: int) -> bool:
        """
        Process and store text content with punctuation preservation
        
        Args:
            text: Extracted text
            path_id: Path ID
        
        Returns:
            Success status
        """
        try:
            # Check if db_hub is available (required for this method)
            if not self.db_hub:
                logger.error("db_hub is required for _store_content_pipeline but is None")
                return False
            
            # OPTIMIZED: Use global singleton ContentProcessor
            from database.processors import get_content_processor
            processor = get_content_processor()
            tokens = processor.extract_words_with_punctuation_chunked(text)
            
            # CRITICAL: Allow empty files to be stored - they should still have metadata stored
            if not tokens:
                logger.info("No tokens extracted from text - file may be empty or binary, but metadata will be stored")
                # Return True to indicate metadata storage succeeded, even if content is empty
                # The calling code will still store the file metadata
                return True  # Changed from False to True - empty files should still be considered "stored"
            
            # Step 2: Extract unique words
            words = set(token[0] for token in tokens)
            
            # Step 3: Check connection health before database operations
            if not self.db_hub._check_connection_health():
                logger.warning("Database connection unhealthy before storing content, attempting reconnect...")
                if not self.db_hub._reconnect():
                    logger.error("Failed to reconnect, cannot store content")
                    return False
            
            # Step 4: Get/create word IDs (batch operation)
            # Wrap in try-except to handle connection errors that might occur between check and use
            try:
                word_id_map = self.db_hub.word_operations.get_word_ids(list(words))
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as conn_error:
                # Connection was closed between check and use - reconnect and retry
                logger.warning(f"Connection error during get_word_ids, reconnecting: {conn_error}")
                if self.db_hub._reconnect():
                    # Recreate word_operations with fresh connection
                    self.db_hub._word_operations = None
                    word_id_map = self.db_hub.word_operations.get_word_ids(list(words))
                else:
                    logger.error("Failed to reconnect after connection error")
                    return False
            
            # Step 4: Insert missing words
            missing_words = [w for w in words if w not in word_id_map]
            if missing_words:
                try:
                    new_word_ids = self.db_hub.word_operations.batch_insert_words(missing_words)
                    if new_word_ids:
                        word_id_map.update(new_word_ids)
                    else:
                        # If batch insert failed, try to get IDs again (they might have been inserted by another process)
                        logger.warning(f"Batch insert returned no IDs, retrying get_word_ids for {len(missing_words)} words")
                        retry_ids = self.db_hub.word_operations.get_word_ids(missing_words)
                        word_id_map.update(retry_ids)
                except (psycopg2.InterfaceError, psycopg2.OperationalError) as conn_error:
                    # Connection error - reconnect and retry
                    logger.warning(f"Connection error during batch_insert_words, reconnecting: {conn_error}")
                    if self.db_hub._reconnect():
                        self.db_hub._word_operations = None
                        # Try to get IDs (might have been inserted by another process)
                        try:
                            retry_ids = self.db_hub.word_operations.get_word_ids(missing_words)
                            word_id_map.update(retry_ids)
                        except Exception as retry_error:
                            logger.error(f"Error retrying get_word_ids after reconnect: {retry_error}")
                            return False
                    else:
                        logger.error("Failed to reconnect after connection error in batch_insert_words")
                        return False
                except Exception as e:
                    logger.error(f"Error inserting missing words: {e}")
                    # Try to get IDs anyway (might have been inserted by another process)
                    try:
                        retry_ids = self.db_hub.word_operations.get_word_ids(missing_words)
                        word_id_map.update(retry_ids)
                    except Exception as retry_error:
                        logger.error(f"Error retrying get_word_ids: {retry_error}")
                        return False
            
            # Step 5: Get/create punctuation IDs (batch operation)
            all_punctuation = []
            # Handle both 4-element (legacy) and 5-element (with position) token formats
            for token in tokens:
                if len(token) == 4:
                    # Legacy format: (word, punct_before, punct_after, spacing)
                    _, punct_before, punct_after, spacing = token
                elif len(token) == 5:
                    # New format with position: (word, punct_before, punct_after, spacing, char_position)
                    _, punct_before, punct_after, spacing, _ = token
                else:
                    logger.warning(f"Unexpected token format with {len(token)} elements, skipping")
                    continue
                
                if punct_before:
                    all_punctuation.append(punct_before)
                if punct_after:
                    all_punctuation.append(punct_after)
                if spacing:
                    all_punctuation.append(spacing)
            
            punctuation_id_map = {}
            if all_punctuation:
                try:
                    punctuation_id_map = self.db_hub.punctuation_operations.get_or_create_punctuation_ids_batch(
                        all_punctuation
                    )
                except (psycopg2.InterfaceError, psycopg2.OperationalError) as conn_error:
                    # Connection error - reconnect and retry
                    logger.warning(f"Connection error during get_or_create_punctuation_ids_batch, reconnecting: {conn_error}")
                    if self.db_hub._reconnect():
                        self.db_hub._punctuation_operations = None
                        punctuation_id_map = self.db_hub.punctuation_operations.get_or_create_punctuation_ids_batch(
                            all_punctuation
                        )
                    else:
                        logger.error("Failed to reconnect after connection error in punctuation operations")
                        return False
            
            # Step 6: Create token tuples with IDs and positions
            token_tuples = []
            word_counts = Counter()
            
            # Handle both 4-element (legacy) and 5-element (with position) token formats
            for token in tokens:
                if len(token) == 4:
                    # Legacy format: (word, punct_before, punct_after, spacing)
                    word, punct_before, punct_after, spacing = token
                    char_position = None
                elif len(token) == 5:
                    # New format with position: (word, punct_before, punct_after, spacing, char_position)
                    word, punct_before, punct_after, spacing, char_position = token
                else:
                    logger.warning(f"Unexpected token format with {len(token)} elements, skipping")
                    continue
                
                word_id = word_id_map.get(word)
                if word_id:
                    punct_before_id = punctuation_id_map.get(punct_before) if punct_before else None
                    punct_after_id = punctuation_id_map.get(punct_after) if punct_after else None
                    spacing_id = punctuation_id_map.get(spacing) if spacing else None
                    
                    # Create token tuple with position (5 elements)
                    token_tuples.append((
                        word_id,
                        punct_before_id,
                        punct_after_id,
                        spacing_id,
                        char_position  # Character position in original text
                    ))
                    
                    # Count word frequency
                    word_counts[word_id] += 1
            
            # Step 7: Store content (compressed chunks) with retry and reconnection
            if not token_tuples:
                logger.warning("No token tuples to store")
                return False
            
            content_retry_count = 0
            max_content_retries = 2
            content_stored = False
            
            while content_retry_count <= max_content_retries and not content_stored:
                try:
                    # Check connection health before operation
                    if not self.db_hub._check_connection_health():
                        logger.warning("Database connection unhealthy before storing content, attempting reconnect...")
                        if not self.db_hub._reconnect():
                            logger.error("Failed to reconnect to database for content storage")
                            if content_retry_count < max_content_retries:
                                content_retry_count += 1
                                time.sleep(0.5 * content_retry_count)
                                continue
                            return False
                    
                    content_ids = self.db_hub.content_operations.store_text_content_with_punctuation(
                        token_tuples, path_id
                    )
                    
                    if content_ids:
                        content_stored = True
                    else:
                        if content_retry_count < max_content_retries:
                            content_retry_count += 1
                            logger.warning(f"Content storage returned no IDs, retrying (attempt {content_retry_count}/{max_content_retries})...")
                            time.sleep(0.5 * content_retry_count)
                            continue
                        else:
                            logger.error("Failed to store content - no content IDs returned after retries")
                            return False
                except Exception as e:
                    if is_retryable_error(e) and content_retry_count < max_content_retries:
                        content_retry_count += 1
                        logger.warning(f"Retryable error storing content, retrying (attempt {content_retry_count}/{max_content_retries}): {e}")
                        # Trigger reconnection if it's a connection error
                        if is_connection_error(e):
                            logger.warning("Connection error detected in content storage, attempting reconnect...")
                            try:
                                # Try to rollback any failed transaction before reconnecting
                                if hasattr(self.db_hub, '_connection') and self.db_hub._connection:
                                    try:
                                        if not self.db_hub._connection.closed:
                                            self.db_hub._connection.rollback()
                                    except Exception:
                                        pass  # Ignore rollback errors
                            except Exception:
                                pass  # Ignore errors during rollback attempt
                            
                            if not self.db_hub._reconnect():
                                logger.error("Failed to reconnect after content error")
                        time.sleep(0.5 * content_retry_count)
                        continue
                    else:
                        logger.error(f"Error storing content: {e}")
                        return False
            
            # Step 8: Store word frequencies (with retry and reconnection)
            if word_counts:
                word_freq_retry_count = 0
                max_word_freq_retries = 2
                word_freq_success = False
                
                while word_freq_retry_count <= max_word_freq_retries and not word_freq_success:
                    try:
                        # Check connection health before operation
                        if not self.db_hub._check_connection_health():
                            logger.warning("Database connection unhealthy before storing word frequencies, attempting reconnect...")
                            if not self.db_hub._reconnect():
                                logger.error("Failed to reconnect to database for word frequencies")
                                if word_freq_retry_count < max_word_freq_retries:
                                    word_freq_retry_count += 1
                                    time.sleep(0.5 * word_freq_retry_count)
                                    continue
                                break
                        
                        success = self.db_hub.word_operations.store_word_frequencies(path_id, dict(word_counts))
                        if success:
                            word_freq_success = True
                        else:
                            if word_freq_retry_count < max_word_freq_retries:
                                word_freq_retry_count += 1
                                logger.warning(f"Word frequencies storage returned False, retrying (attempt {word_freq_retry_count}/{max_word_freq_retries})...")
                                time.sleep(0.5 * word_freq_retry_count)
                                continue
                            else:
                                logger.warning(f"Failed to store word frequencies for path_id {path_id} after {max_word_freq_retries} attempts, but content was stored")
                                break
                    except Exception as e:
                        if is_retryable_error(e) and word_freq_retry_count < max_word_freq_retries:
                            word_freq_retry_count += 1
                            logger.warning(f"Retryable error storing word frequencies, retrying (attempt {word_freq_retry_count}/{max_word_freq_retries}): {e}")
                            # Trigger reconnection if it's a connection error
                            if is_connection_error(e):
                                try:
                                    # Try to rollback any failed transaction before reconnecting
                                    if hasattr(self.db_hub, '_connection') and self.db_hub._connection:
                                        try:
                                            if not self.db_hub._connection.closed:
                                                self.db_hub._connection.rollback()
                                        except Exception:
                                            pass  # Ignore rollback errors
                                except Exception:
                                    pass  # Ignore errors during rollback attempt
                                
                                if not self.db_hub._reconnect():
                                    logger.error("Failed to reconnect after word frequencies error")
                            time.sleep(0.5 * word_freq_retry_count)
                            continue
                        else:
                            logger.error(f"Error storing word frequencies: {e}")
                            # Don't fail the whole operation if word frequencies fail
                            break
            
            return True
            
        except Exception as e:
            logger.error(f"Error in content storage pipeline: {e}", exc_info=True)
            return False
        
    def get_statistics(self) -> Dict[str, int]:
        """Get pipeline statistics"""
        return self.stats.copy()
    
    def verify_file_stored(self, path_id: int) -> Optional[Dict[str, Any]]:
        """
        Verify that a file was successfully stored in the database.
        Returns detailed information about the stored file.
        
        Args:
            path_id: Path ID returned from store_file_complete or _store_file_sync
        
        Returns:
            Dictionary with file storage details, or None if not found
        """
        if not path_id:
            return None
        
        try:
            # Get path metadata using ContentDBService
            path_info = self.db_service.paths_repo.get_file_by_id(path_id) if self.db_service else None
            if not path_info:
                return None
            
            # Convert path_info to dict if it's a tuple/row
            if isinstance(path_info, tuple):
                # Assume standard path table structure: (id, file_name, file_path, file_size, file_type, file_status, file_date, hash_id, source_id, side_id, ...)
                path_info = {
                    'id': path_info[0] if len(path_info) > 0 else None,
                    'file_name': path_info[1] if len(path_info) > 1 else None,
                    'file_path': path_info[2] if len(path_info) > 2 else None,
                    'file_size': path_info[3] if len(path_info) > 3 else None,
                    'file_type': path_info[4] if len(path_info) > 4 else None,
                    'file_status': path_info[5] if len(path_info) > 5 else None,
                    'file_date': path_info[6] if len(path_info) > 6 else None,
                    'hash_id': path_info[7] if len(path_info) > 7 else None,
                    'source_id': path_info[8] if len(path_info) > 8 else None,
                    'side_id': path_info[9] if len(path_info) > 9 else None,
                }
            elif not isinstance(path_info, dict):
                # If it's some other type, try to convert
                logger.warning(f"Unexpected path_info type: {type(path_info)}, attempting to convert")
                path_info = {'id': path_id} if path_info else None
                if not path_info:
                    return None
            
            # Get hash information
            hash_id = path_info.get('hash_id')
            hash_value = None
            if hash_id:
                # Use ContentDBService hashs_repo instead of db_hub.hash_operations
                hash_value = self.db_service.hashs_repo.get_hash_by_id(hash_id) if self.db_service else None
            
            # Check if content was stored using ContentDBService
            content_exists = False
            content_length = 0
            try:
                # Use ContentDBService to get content word IDs (indicates content exists)
                content_word_ids = self.db_service.get_content_word_ids(path_id) if self.db_service else []
                if content_word_ids:
                    content_exists = True
                    content_length = len(content_word_ids)  # Number of word IDs in content
            except Exception as content_error:
                logger.debug(f"Error checking content existence: {content_error}")
                pass
            
            # Build verification result
            verification = {
                'stored': True,
                'path_id': path_id,
                'file_name': path_info.get('file_name'),
                'file_path': path_info.get('file_path'),
                'file_size': path_info.get('file_size'),
                'file_type': path_info.get('file_type'),
                'file_status': path_info.get('file_status'),
                'file_date': str(path_info.get('file_date')) if path_info.get('file_date') else None,
                'date_creation': str(path_info.get('date_creation')) if path_info.get('date_creation') else None,
                'hash_id': hash_id,
                'hash_value': hash_value[:32] + '...' if hash_value and len(hash_value) > 32 else hash_value,
                'content_stored': content_exists,
                'content_length': content_length,
                'coordinates': path_info.get('coordinates')
            }
            
            return verification
        except Exception as e:
            logger.error(f"Error verifying file storage: {e}")
            return None
    
    def store_file_complete(
        self,
        file_info: Dict[str, Any],
        result: Dict[str, Any],
        parent_path_id: Optional[int] = None,
        hierarchy_path: Optional[str] = None,
        use_async: bool = False,
        source_name: Optional[str] = None,
        side_name: Optional[str] = None
         ) -> Optional[int]:
        """
        Store file with complete processing (wrapper for _store_file_sync)
        
        Args:
            file_info: File metadata dictionary
            result: File processing result
            parent_path_id: Parent path ID (for nested files)
            hierarchy_path: Hierarchy path string
            use_async: Whether to use async storage (currently not implemented, always sync)
            source_name: Source name (optional, overrides constructor default)
            side_name: Side name (optional, overrides constructor default)
        
        Returns:
            Path ID or None if failed
        """
        # Validate inputs
        if not isinstance(file_info, dict):
            logger.error(f"Invalid file_info type: {type(file_info).__name__}, expected dict")
            return None
        
        if not isinstance(result, dict):
            logger.error(f"Invalid result type: {type(result).__name__}, expected dict")
            return None

        # DATA-04: count unsupported file types so the statistics service
        # reflects reality (previously files_unsupported was never wired up).
        if result.get('error') and 'Unsupported file type' in str(result.get('error')):
            self.stats['files_unsupported'] = self.stats.get('files_unsupported', 0) + 1

        # Currently only sync is supported
        return self._store_file_sync(
            file_info, 
            result, 
            source_name=source_name,
            side_name=side_name,
            parent_path_id=parent_path_id, 
            hierarchy_path=hierarchy_path
        )
    
    def shutdown(self):
        """Shutdown storage pipeline and cleanup resources"""
        # Close database connection if needed
        # Currently db_hub is managed externally, so just log
        logger.info("Storage pipeline shutdown")