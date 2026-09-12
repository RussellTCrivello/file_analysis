"""
File Router Service - Routes files to appropriate readers
Aligned with database design principles (similar to ContentDBService)

This service manages file routing and processing, following the same
design pattern as the database layer.
"""

import os
import threading
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Set

parent_dir = Path(__file__).parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import logging
logger = logging.getLogger(__name__)

# Import from parent directory (core, Hdg_Err_Ex_Log are in parent)
import sys
from pathlib import Path

# Ensure parent directory is in path for imports
parent_dir = Path(__file__).parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from core.file_utils import (
    read_tree,
    create_standardized_result
)

from core.time_utils import (
    print_execution_time,
    calculate_file_processing_metrics
)

from Hdg_Err_Ex_Log.logging_utils import (
    record_command_line_action,
)

from .file_reader_service import FileReaderService

MAX_RECURSION_DEPTH = 5


class FileRouterService:
    """
    Service class that routes files to appropriate readers and handles processing.
    
    Follows database design principles (similar to ContentDBService):
    - Class-based design (all functions within classes)
    - Manages file routing and processing
    - Handles extracted files (archives, emails)
    - Provides unified interface
    - Consistent error handling
    - Resource management
    """
    
    def __init__(self, file_reader_service: Optional[FileReaderService] = None):
        """
        Initialize file router service.
        
        Args:
            file_reader_service: Optional FileReaderService instance
        """
        self.file_reader_service = file_reader_service or FileReaderService()
        self._extraction_lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_supported_extensions(self) -> Set[str]:
        """Return all supported extensions, derived from registered readers.

        READER-01: the single authoritative extension list is the union of
        what the registered readers actually declare - fixing the
        readiness-check interface mismatch (the router previously did not
        expose this at all while verify_readiness.py called it).
        """
        return self.file_reader_service.get_supported_extensions()

    def process_file(
        self,
        file_info: Dict[str, Any],
        collect: bool = True,
        depth: int = 0,
        storage_source: Optional[str] = None,
        storage_side: Optional[str] = None,
        storage_pipeline: Optional[Any] = None,
        store_result: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single file using appropriate reader.

        DATA-01: when ``store_result`` is False the caller (the storage
        pipeline owner, IntegratedFileReader) persists the top-level file
        itself; the router then only persists child artifacts (extracted
        archive members, email messages/attachments). This removes the
        historical double-store of the same file.

        Args:
            file_info: Dictionary containing file information
            collect: Whether to collect results
            depth: Current recursion depth
            storage_source: Optional storage source name
            storage_side: Optional storage side name
            storage_pipeline: Optional storage pipeline instance
            store_result: Whether to persist the top-level file result

        Returns:
            Dictionary with processing result or None
        """
        if depth > MAX_RECURSION_DEPTH:
            file_path = file_info.get('path', 'unknown')
            self.logger.warning(f"Maximum recursion depth ({MAX_RECURSION_DEPTH}) exceeded for: {file_path}")
            
            result = create_standardized_result(
                file_path,
                {"error": f"Maximum recursion depth ({MAX_RECURSION_DEPTH}) exceeded"},
                0
            )
            # Store even if recursion depth exceeded
            if store_result:
                self._store_result_if_enabled(
                    file_info,
                    result,
                    storage_source,
                    storage_side,
                    storage_pipeline
                )
            return result
        
        if file_info.get('type') != 'FILE':
            return None
        
        file_path = file_info.get('path')
        declared_extension = self.file_reader_service.normalize_extension(
            file_info.get('extension')
        )

        start_time = time.time()

        # DETECT-01: identify the file from its CONTENT first and fall back to
        # the declared extension. A missing or lying extension is no longer
        # fatal - magic-byte inspection decides the processing path, so an
        # extensionless ZIP is still extracted and a misnamed PDF still gets
        # PDF treatment.
        reader, detection = self.file_reader_service.resolve_reader_for_file(
            file_path,
            declared_extension
        )
        effective_extension = detection['effective_extension']

        if detection['extension_mismatch']:
            self.logger.warning(
                "Extension/content mismatch for %s: %s",
                file_path,
                detection['detection_note']
            )

        # Hand the verified type to the reader so its internal format dispatch
        # uses content evidence rather than the filename.
        routed_file_info = dict(file_info)
        routed_file_info['effective_extension'] = effective_extension

        content_data = None

        try:
            if reader:
                # Use reader to read file
                content_data = print_execution_time(
                    f"Reading file: {os.path.basename(file_path)}",
                    reader.read_file,
                    routed_file_info
                )

                # Handle special cases (archives, emails) that return extraction paths
                if content_data and isinstance(content_data, dict):
                    extraction_path = content_data.get("extraction_path")
                    email_result = content_data

                    # Handle archive extraction. Keyed on the resolved reader
                    # rather than an extension set, so compound extensions
                    # (.tar.gz) and content-detected archives both recurse.
                    if extraction_path and reader is self.file_reader_service.archive_reader:
                        content_data = self._process_extracted_files(
                            extraction_path,
                            'archive',
                            file_path,
                            collect,
                            depth,
                            use_parallel=True,
                            storage_source=storage_source,
                            storage_side=storage_side,
                            storage_pipeline=storage_pipeline
                        )

                    # Handle email extraction
                    elif reader is self.file_reader_service.email_reader:
                        content_data = self._process_email_result(
                            email_result,
                            file_path,
                            collect,
                            depth,
                            storage_source=storage_source,
                            storage_side=storage_side,
                            storage_pipeline=storage_pipeline
                        )
            else:
                # Unrecognized file type
                processing_time = time.time() - start_time
                result = create_standardized_result(
                    file_path,
                    {
                        "error": f"Unsupported file type: {effective_extension or 'unknown'}",
                        "type_detection": detection
                    },
                    processing_time
                )
                # Store even if file type is unsupported
                if store_result:
                    self._store_result_if_enabled(
                        file_info,
                        result,
                        storage_source,
                        storage_side,
                        storage_pipeline
                    )
                return result
                
        except Exception as e:
            error_str = str(e).lower()
            # Suppress verbose tesseract errors
            if 'tesseract' in error_str and ('not installed' in error_str or 'not in your path' in error_str):
                self.logger.debug(f"Tesseract not available for {file_path}, skipping OCR")
                content_data = {"error": "OCR unavailable (tesseract not installed)"}
            else:
                self.logger.error(f"Error processing {file_path}: {str(e)}")
                content_data = {"error": str(e)}
        
        if content_data is None:
            processing_time = time.time() - start_time
            result = create_standardized_result(
                file_path,
                {"error": "File processing returned no content"},
                processing_time
            )
            # Store even if there's an error
            if store_result:
                self._store_result_if_enabled(
                    file_info,
                    result,
                    storage_source,
                    storage_side,
                    storage_pipeline
                )
            return result
        
        processing_time = time.time() - start_time
        result = create_standardized_result(file_path, content_data, processing_time)

        # Provenance: keep a record of HOW the file was identified so the
        # decision survives into storage and is visible during review.
        if isinstance(result.get('Content'), dict):
            result['Content'].setdefault('type_detection', detection)

        # Calculate and display file processing metrics
        calculate_file_processing_metrics(file_info, result)
        
        # Store the result automatically if storage is enabled
        # (skipped when the caller owns persistence for the top-level file)
        if store_result:
            self._store_result_if_enabled(
                file_info,
                result,
                storage_source,
                storage_side,
                storage_pipeline
            )

        return result
    
    def process_file_list(
        self,
        list_tree: List[Dict[str, Any]],
        collect: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Process a list of files.
        
        Args:
            list_tree: List of file information dictionaries
            collect: Whether to collect results
        
        Returns:
            List of processing results
        """
        results = []
        
        for file_info in list_tree:
            if 'extension' in file_info and file_info.get('type') == 'FILE':
                result = self.process_file(
                    file_info,
                    collect=collect,
                    depth=0
                )
                if result is not None:
                    results.append(result)
        
        return results
    
    def _process_extracted_files(
        self,
        extraction_path: str,
        extraction_type: str,
        parent_file: str,
        collect: bool,
        depth: int,
        use_parallel: bool = True,
        storage_source: Optional[str] = None,
        storage_side: Optional[str] = None,
        storage_pipeline: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Process extracted files from archives or emails.
        
        Args:
            extraction_path: Path to extracted files directory
            extraction_type: Type of extraction (e.g., 'archive', 'email_attachment')
            parent_file: Path to parent file
            collect: Whether to collect results
            depth: Current recursion depth
            use_parallel: Whether to use parallel processing
            storage_source: Optional storage source name
            storage_side: Optional storage side name
        
        Returns:
            Dictionary with extraction results
        """
        # Ensure only one thread processes each extraction at a time
        with self._extraction_lock:
            self.logger.info(f"{'─'*70}")
            self.logger.info(f"📦 PROCESSING EXTRACTED FILES FROM {extraction_type.upper()}")
            self.logger.info(f"{'─'*70}")
            self.logger.info(f"Source:        {os.path.basename(parent_file)}")
            self.logger.info(f"Location:      {extraction_path}")
            if use_parallel:
                self.logger.info(f"Mode:          PARALLEL (fast)")
            else:
                self.logger.info(f"Mode:          SEQUENTIAL")
        
        # Record extraction start
        record_command_line_action(
            "EXTRACTION_START",
            f"Processing extracted files from {extraction_type}",
            {
                "extraction_type": extraction_type,
                "parent_file": parent_file,
                "extraction_path": extraction_path,
                "depth": depth,
                "parallel": use_parallel
            }
        )
        
        tree = read_tree(extraction_path)
        file_list = [item for item in tree if item.get('type') == 'FILE']
        
        print(f"Total Files:   {len(file_list)}")
        print(f"{'─'*70}\n")
        
        if not file_list:
            record_command_line_action(
                "EXTRACTION_COMPLETE",
                f"No files extracted from {extraction_type}",
                {
                    "extraction_type": extraction_type,
                    "parent_file": parent_file,
                    "extracted_files_count": 0
                }
            )
            return {
                f"{extraction_type}_info": {
                    "extraction_path": extraction_path,
                    "extracted_files_count": 0
                },
                "extracted_files": []
            }
        
        # Check system load before using parallel processing
        system_overloaded = False
        try:
            from core.resource_coordinator import get_resource_coordinator
            coordinator = get_resource_coordinator()
            if coordinator._system_overload:
                system_overloaded = True
                self.logger.warning(
                    "System is overloaded. Using sequential processing for extracted files "
                    "to prevent freezing and thread conflicts."
                )
        except Exception as e:
            self.logger.debug(f"Could not check system load: {e}")
        
        # Use parallel processing if enabled AND system is not overloaded
        # Also disable parallel for nested extractions (extracted files from extracted files)
        # to prevent thread conflicts
        if use_parallel and len(file_list) > 1 and not system_overloaded and depth < 2:
            try:
                from pipeline.integrated_reader import IntegratedFileReader
                
                self.logger.info(f"🚀 Using parallel processing for {len(file_list)} extracted files...")
                
                if not storage_source or not storage_side:
                    self.logger.error(
                        "❌ Source and side are MANDATORY for storing extracted files. "
                        f"Source: {storage_source}, Side: {storage_side}. "
                        "Extracted files will be processed but NOT stored in database."
                    )
                    enable_storage_for_extracted = False
                else:
                    enable_storage_for_extracted = True
                    self.logger.info(
                        f"✅ Storage enabled for extracted files: Source='{storage_source}', Side='{storage_side}'"
                    )
                
                # Reduce workers for extracted files to prevent overload
                max_workers = min(4, max(2, len(file_list) // 10 + 1))
                
                # IntegratedFileReader creates its own storage_pipeline internally
                # We just need to pass storage_source and storage_side
                reader_kwargs = {
                    'max_workers': max_workers,
                    'enable_monitoring': False,
                    'use_priority': True,
                    'enable_storage': enable_storage_for_extracted,
                    'storage_source': storage_source,
                    'storage_side': storage_side
                }
                
                with IntegratedFileReader(**reader_kwargs) as reader:
                    extracted_results_raw = reader.process_folder(extraction_path)
                    
                    if enable_storage_for_extracted:
                        storage_stats = reader.get_storage_statistics()
                        stored_count = storage_stats.get('completed', 0)
                        duplicates_count = storage_stats.get('duplicates', 0)
                        failed_count = storage_stats.get('failed', 0)
                        
                        if stored_count > 0:
                            self.logger.info(
                                f"✅ Stored {stored_count} extracted files to database during parallel processing "
                                f"(duplicates: {duplicates_count}, failed: {failed_count})"
                            )
                        elif failed_count > 0:
                            self.logger.warning(
                                f"⚠ {failed_count} extracted files failed to store during parallel processing. "
                                f"Check logs for details."
                            )
                        else:
                            self.logger.warning(
                                f"⚠ No extracted files were stored during parallel processing. "
                                f"Total processed: {len(extracted_results_raw)}. "
                                f"Check if storage_source and storage_side are correct."
                            )
                
                extracted_results = []
                for r in extracted_results_raw:
                    if r and isinstance(r, dict) and r.get("Metadata"):
                        extracted_results.append(r)
                    elif r is None:
                        self.logger.warning(f"⚠ Warning: Got None result for a file during parallel processing.")
                
                if len(extracted_results) < len(file_list):
                    missing_count = len(file_list) - len(extracted_results)
                    self.logger.warning(f"⚠ Warning: Only collected {len(extracted_results)}/{len(file_list)} results. {missing_count} files may not have been processed or stored.")
                
                successful_extractions = 0
                failed_extractions = 0
                for result in extracted_results:
                    content = result.get("Content", {})
                    if content and not content.get("error"):
                        successful_extractions += 1
                    else:
                        failed_extractions += 1
                
                print(f"\n✓ Completed parallel processing {len(extracted_results)}/{len(file_list)} files\n")
                
                success_rate = (len(extracted_results) / len(file_list) * 100) if file_list else 0.0
                record_command_line_action(
                    "EXTRACTION_COMPLETE",
                    f"Completed parallel processing extracted files from {extraction_type}",
                    {
                        "extraction_type": extraction_type,
                        "parent_file": parent_file,
                        "extraction_path": extraction_path,
                        "total_files": len(file_list),
                        "processed_files": len(extracted_results),
                        "successful": successful_extractions,
                        "failed": failed_extractions,
                        "success_rate": f"{success_rate:.1f}%",
                        "parallel": True
                    }
                )
                
                return {
                    f"{extraction_type}_info": {
                        "extraction_path": extraction_path,
                        "total_files": len(file_list),
                        "processed_files": len(extracted_results),
                        "success_rate": f"{success_rate:.1f}%" if file_list else "0%",
                        "parallel_processing": True
                    },
                    "extracted_files": extracted_results
                }
                
            except Exception as e:
                self.logger.warning(f"⚠ Parallel processing failed, falling back to sequential: {e}")
                # Fall through to sequential processing
        
        # Sequential processing (fallback or when use_parallel=False)
        # Priority order: 1) All other files (highest), 2) PDFs (medium), 3) Images (lowest)
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg', '.ico', '.heic', '.heif'}
        pdf_extensions = {'.pdf'}
        
        priority_files = []  # All files except images and PDFs (highest priority)
        pdf_files = []  # PDFs (second-to-last priority)
        image_files = []  # Images (lowest priority)
        
        for file_info in file_list:
            file_path = file_info.get('path', '')
            if isinstance(file_path, str):
                file_ext = os.path.splitext(file_path)[1].lower()
            else:
                file_ext = ''
            
            # Separate by priority: images last, PDFs second-to-last, everything else first
            if file_ext in image_extensions:
                image_files.append(file_info)
            elif file_ext in pdf_extensions:
                pdf_files.append(file_info)
            else:
                priority_files.append(file_info)
        
        print(f"  📄 Priority files: {len(priority_files)}")
        print(f"  📑 PDF files: {len(pdf_files)} (will be processed second-to-last)")
        print(f"  🖼️  Image files: {len(image_files)} (will be processed last)")
        
        extracted_results = []
        successful_extractions = 0
        failed_extractions = 0
        
        # PHASE 1: Process all priority files (non-image, non-PDF) first
        if priority_files:
            print(f"\n📄 PHASE 1: Processing {len(priority_files)} priority files...")
            for idx, file_info in enumerate(priority_files, 1):
                file_name = file_info.get('name', 'unknown')
                print(f"Processing: {idx}/{len(priority_files)} - {file_name}", end='\r')
                
                record_command_line_action(
                    "EXTRACTED_FILE_PROCESSING",
                    f"Processing extracted file {idx}/{len(priority_files)}: {file_name}",
                    {
                        "extraction_type": extraction_type,
                        "parent_file": parent_file,
                        "file_name": file_name,
                        "file_path": file_info.get('path', 'unknown'),
                        "progress": f"{idx}/{len(priority_files)}",
                        "phase": 1
                    }
                )
                
                result = self.process_file(
                    file_info,
                    collect=collect,
                    depth=depth + 1,
                    storage_source=storage_source,
                    storage_side=storage_side,
                    storage_pipeline=storage_pipeline
                )
                
                if result:
                    extracted_results.append(result)
                    content = result.get("Content", {})
                    
                    # Check if file was stored successfully
                    path_id = result.get("database_path_id")
                    if not path_id and storage_pipeline:
                        # File was processed but not stored - log warning
                        self.logger.warning(
                            f"⚠ Extracted file '{file_name}' was processed but NOT stored in database. "
                            f"Check storage_source and storage_side are provided."
                        )
                    
                    if content and not content.get("error"):
                        successful_extractions += 1
                    else:
                        failed_extractions += 1
                else:
                    self.logger.warning(f"⚠ Extracted file '{file_name}' processing returned None")
                    failed_extractions += 1
            
            print(f"\n✅ PHASE 1 complete: {len(priority_files)} priority files processed")
        
        # PHASE 2: Process all PDF files only after priority files are completely done
        if pdf_files:
            print(f"\n📑 PHASE 2: Processing {len(pdf_files)} PDF files (after priority files are complete)...")
            for idx, file_info in enumerate(pdf_files, 1):
                file_name = file_info.get('name', 'unknown')
                print(f"Processing: {idx}/{len(pdf_files)} - {file_name}", end='\r')
                
                record_command_line_action(
                    "EXTRACTED_FILE_PROCESSING",
                    f"Processing extracted file {idx}/{len(pdf_files)}: {file_name}",
                    {
                        "extraction_type": extraction_type,
                        "parent_file": parent_file,
                        "file_name": file_name,
                        "file_path": file_info.get('path', 'unknown'),
                        "progress": f"{idx}/{len(pdf_files)}",
                        "phase": 2
                    }
                )
                
                result = self.process_file(
                    file_info,
                    collect=collect,
                    depth=depth + 1,
                    storage_source=storage_source,
                    storage_side=storage_side,
                    storage_pipeline=storage_pipeline
                )
                
                if result:
                    extracted_results.append(result)
                    content = result.get("Content", {})
                    
                    # Check if file was stored successfully
                    path_id = result.get("database_path_id")
                    if not path_id and storage_pipeline:
                        # File was processed but not stored - log warning
                        self.logger.warning(
                            f"⚠ Extracted PDF file '{file_name}' was processed but NOT stored in database. "
                            f"Check storage_source and storage_side are provided."
                        )
                    
                    if content and not content.get("error"):
                        successful_extractions += 1
                    else:
                        failed_extractions += 1
                else:
                    self.logger.warning(f"⚠ Extracted PDF file '{file_name}' processing returned None")
                    failed_extractions += 1
            
            print(f"\n✅ PHASE 2 complete: {len(pdf_files)} PDF files processed")
        
        # PHASE 3: Process all image files only after PDFs are completely done
        if image_files:
            print(f"\n🖼️  PHASE 3: Processing {len(image_files)} image files (after all other files are complete)...")
            for idx, file_info in enumerate(image_files, 1):
                file_name = file_info.get('name', 'unknown')
                print(f"Processing: {idx}/{len(image_files)} - {file_name}", end='\r')
                
                record_command_line_action(
                    "EXTRACTED_FILE_PROCESSING",
                    f"Processing extracted file {idx}/{len(image_files)}: {file_name}",
                    {
                        "extraction_type": extraction_type,
                        "parent_file": parent_file,
                        "file_name": file_name,
                        "file_path": file_info.get('path', 'unknown'),
                        "progress": f"{idx}/{len(image_files)}",
                        "phase": 3
                    }
                )
                
                result = self.process_file(
                    file_info,
                    collect=collect,
                    depth=depth + 1,
                    storage_source=storage_source,
                    storage_side=storage_side,
                    storage_pipeline=storage_pipeline
                )
                
                if result:
                    extracted_results.append(result)
                    content = result.get("Content", {})
                    
                    # Check if file was stored successfully
                    path_id = result.get("database_path_id")
                    if not path_id and storage_pipeline:
                        # File was processed but not stored - log warning
                        self.logger.warning(
                            f"⚠ Extracted image file '{file_name}' was processed but NOT stored in database. "
                            f"Check storage_source and storage_side are provided."
                        )
                    
                    if content and not content.get("error"):
                        successful_extractions += 1
                    else:
                        failed_extractions += 1
                else:
                    self.logger.warning(f"⚠ Extracted image file '{file_name}' processing returned None")
                    failed_extractions += 1
            
            print(f"\n✅ PHASE 3 complete: {len(image_files)} image files processed")
        
        total_files = len(priority_files) + len(pdf_files) + len(image_files)
        print(f"\n✓ Completed processing {len(extracted_results)}/{total_files} files\n")
        
        success_rate = (len(extracted_results) / total_files * 100) if total_files > 0 else 0.0
        record_command_line_action(
            "EXTRACTION_COMPLETE",
            f"Completed processing extracted files from {extraction_type}",
            {
                "extraction_type": extraction_type,
                "parent_file": parent_file,
                "extraction_path": extraction_path,
                "total_files": total_files,
                "processed_files": len(extracted_results),
                "priority_files": len(priority_files),
                "pdf_files": len(pdf_files),
                "image_files": len(image_files),
                "successful": successful_extractions,
                "failed": failed_extractions,
                "success_rate": f"{success_rate:.1f}%",
                "three_phase_processing": True,
                "extracted_files": [
                    {
                        "file_path": r.get("File_Path", "unknown"),
                        "success": not bool(r.get("Content", {}).get("error")),
                        "processing_time": r.get("Processing_Time", 0)
                    }
                    for r in extracted_results
                ]
            }
        )
        
        return {
            f"{extraction_type}_info": {
                "extraction_path": extraction_path,
                "total_files": total_files,
                "processed_files": len(extracted_results),
                "priority_files": len(priority_files),
                "pdf_files": len(pdf_files),
                "image_files": len(image_files),
                "success_rate": f"{success_rate:.1f}%" if total_files > 0 else "0%",
                "three_phase_processing": True
            },
            "extracted_files": extracted_results
        }
    
    def _process_email_result(
        self,
        email_result: Dict[str, Any],
        file_path: str,
        collect: bool,
        depth: int,
        storage_source: Optional[str] = None,
        storage_side: Optional[str] = None,
        storage_pipeline: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Process email results with message content and attachments separated.
        
        Args:
            email_result: Email extraction result
            file_path: Path to email file
            collect: Whether to collect results
            depth: Current recursion depth
            storage_source: Optional storage source name
            storage_side: Optional storage side name
            storage_pipeline: Optional storage pipeline instance
        
        Returns:
            Dictionary with email processing results
        """
        if not email_result or (isinstance(email_result, dict) and email_result.get("error")):
            return email_result
        
        message_content = email_result.get("message") or email_result.get("messages")
        extraction_path = email_result.get("extraction_path")
        has_attachments = email_result.get("has_attachments", False)
        
        message_count = 0
        if message_content:
            if isinstance(message_content, list):
                message_count = len(message_content)
            elif isinstance(message_content, dict):
                message_count = 1
        
        final_result = {
            "email_content": message_content,
            "email_metadata": {
                "source": file_path,
                "attachment_count": email_result.get("attachment_count", 0),
                "has_attachments": has_attachments,
                "message_count": message_count
            }
        }
        
        # STEP 1: SAVE ALL MESSAGES TO DATABASE FIRST
        if message_content and storage_pipeline and storage_source and storage_side:
            try:
                import os
                
                if message_count > 1:
                    self.logger.info(f"💾 Saving {message_count} email messages to database BEFORE processing attachments...")
                else:
                    self.logger.info(f"💾 Saving email message to database BEFORE processing attachments...")
                
                message_result = create_standardized_result(
                    file_path,
                    {"email_content": message_content},
                    0
                )
                
                file_info = {
                    "path": file_path,
                    "name": os.path.basename(file_path),
                    "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
                }
                
                message_path_id = storage_pipeline._store_file_sync(
                    file_info,
                    message_result,
                    source_name=storage_source,
                    side_name=storage_side
                )
                
                if message_path_id:
                    if message_count > 1:
                        self.logger.info(f"✓ All {message_count} email messages stored to database (Path ID: {message_path_id}) before processing attachments")
                    else:
                        self.logger.info(f"✓ Email message stored to database (Path ID: {message_path_id}) before processing attachments")
                    final_result["email_metadata"]["message_path_id"] = message_path_id
                else:
                    self.logger.warning("⚠ Failed to store email message(s) to database before processing attachments")
            except Exception as e:
                self.logger.error(f"Error storing email message(s) to database: {e}")
        elif message_content and (not storage_pipeline or not storage_source or not storage_side):
            if message_count > 1:
                self.logger.warning(f"⚠ Cannot save {message_count} email messages: storage not configured")
            else:
                self.logger.warning(f"⚠ Cannot save email message: storage not configured")
        
        # STEP 2: PROCESS ATTACHMENTS (ONLY AFTER ALL MESSAGES ARE SAVED)
        if has_attachments and extraction_path and os.path.exists(extraction_path):
            print(f"\n📎 Processing email attachments from: {os.path.basename(file_path)}")
            self.logger.info(f"📎 Processing attachments from extracted folder: {extraction_path}")
            
            attachments_result = self._process_extracted_files(
                extraction_path,
                'email_attachment',
                file_path,
                collect,
                depth,
                use_parallel=True,
                storage_source=storage_source,
                storage_side=storage_side,
                storage_pipeline=storage_pipeline
            )
            
            final_result["attachments"] = attachments_result
        else:
            final_result["attachments"] = {
                "email_attachment_info": {
                    "extraction_path": extraction_path or "N/A",
                    "extracted_files_count": 0
                },
                "extracted_files": []
            }
        
        return final_result
    
    def _get_archive_extensions(self) -> set:
        """Get set of archive extensions"""
        archive_reader = self.file_reader_service.archive_reader
        if archive_reader:
            return archive_reader.get_supported_extensions()
        return set()
    
    def _get_email_extensions(self) -> set:
        """Get set of email extensions"""
        email_reader = self.file_reader_service.email_reader
        if email_reader:
            return email_reader.get_supported_extensions()
        return set()
    
    def _store_result_if_enabled(
        self,
        file_info: Dict[str, Any],
        result: Dict[str, Any],
        storage_source: Optional[str],
        storage_side: Optional[str],
        storage_pipeline: Optional[Any]
    ) -> Optional[int]:
        """
        Store file result to database if storage is enabled.
        
        This method automatically stores all read content to the database
        following the same pattern as IntegratedFileReader.
        
        Args:
            file_info: Dictionary containing file information
            result: Processing result dictionary
            storage_source: Optional storage source name
            storage_side: Optional storage side name
            storage_pipeline: Optional storage pipeline instance
        
        Returns:
            Path ID if stored successfully, None otherwise
        """
        # Only store if storage_pipeline and both source/side are provided
        if not storage_pipeline or not storage_source or not storage_side:
            return None
        
        try:
            # Ensure result is a dictionary
            if not isinstance(result, dict):
                self.logger.warning(f"Invalid result type for storage: {type(result).__name__}, expected dict. Creating error result.")
                result = create_standardized_result(
                    file_info.get('path', 'unknown'),
                    {"error": f"Invalid result type: {type(result).__name__}"},
                    0
                )
            
            # ALWAYS attempt to store, even if file has errors
            # This ensures metadata and error information is preserved
            path_id = storage_pipeline._store_file_sync(
                file_info,
                result,
                source_name=storage_source,
                side_name=storage_side
            )
            
            if path_id:
                # Add path_id to result for reference
                if not result.get('database_path_id'):
                    result['database_path_id'] = path_id
                
                file_name = file_info.get('name', os.path.basename(file_info.get('path', 'unknown')))
                self.logger.info(f"✅ Stored: {file_name} → Database (Path ID: {path_id})")
                return path_id
            else:
                # Storage failed - log error
                file_name = file_info.get('name', os.path.basename(file_info.get('path', 'unknown')))
                self.logger.error(f"❌ STORAGE FAILED: '{file_name}' was NOT stored in database")
                self.logger.error(f"   File path: {file_info.get('path', 'unknown')}")
                return None
                
        except Exception as e:
            file_name = file_info.get('name', os.path.basename(file_info.get('path', 'unknown')))
            self.logger.error(f"Error storing file '{file_name}' to database: {e}")
            return None


# Create singleton instance for backward compatibility
_file_router_service = FileRouterService()


def get_file_router_service() -> FileRouterService:
    """Get the singleton FileRouterService instance"""
    return _file_router_service
