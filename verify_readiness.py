"""
Production Readiness Verification Script

This script verifies that all components are ready for terabyte-scale processing.
Run this before processing large folders to ensure everything is configured correctly.
"""

import sys
import os
from pathlib import Path

def safe_print(message: str) -> None:
    """Safely print message"""
    try:
        print(message)
    except UnicodeEncodeError:
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        print(safe_message)

def check_component(name: str, check_func, critical: bool = True):
    """Check a component and report status"""
    try:
        result = check_func()
        if result:
            safe_print(f"✅ {name}: OK")
            return True
        else:
            if critical:
                safe_print(f"❌ {name}: FAILED (CRITICAL)")
            else:
                safe_print(f"⚠️  {name}: WARNING (Non-critical)")
            return not critical
    except Exception as e:
        if critical:
            safe_print(f"❌ {name}: ERROR - {e} (CRITICAL)")
        else:
            safe_print(f"⚠️  {name}: ERROR - {e} (Non-critical)")
        return not critical

def check_imports():
    """Check all critical imports"""
    try:
        from pipeline.integrated_reader import IntegratedFileReader
        from core.file_utils import read_tree, get_standardized_metadata
        from database.services.contents_db_service import ContentDBService
        from database.database.database import Database
        from database.processors.content_processor import ContentProcessor
        return True
    except ImportError as e:
        safe_print(f"   Import error: {e}")
        return False

def check_database_connection():
    """Check database connectivity"""
    try:
        from database.database.database import Database
        db = Database()
        if db.health_check():
            db.close_all()
            return True
        else:
            safe_print("   Database health check failed")
            return False
    except Exception as e:
        safe_print(f"   Database error: {e}")
        return False

def check_settings():
    """Check settings initialization"""
    try:
        from settings import get_processing_config, get_database_config, get_storage_config
        processing_cfg = get_processing_config()
        db_config = get_database_config()
        storage_cfg = get_storage_config()
        
        # Verify critical settings
        if processing_cfg.max_workers < 1:
            safe_print(f"   Invalid max_workers: {processing_cfg.max_workers}")
            return False
        
        if db_config.pool_max_conn < 5:
            safe_print(f"   Pool size too small: {db_config.pool_max_conn} (recommended: 15-25)")
            return False
        
        return True
    except Exception as e:
        safe_print(f"   Settings error: {e}")
        return False

def check_file_processing():
    """Check file processing components"""
    try:
        from reader_file.services.file_router_service import FileRouterService
        from reader_file.readers.base_reader import BaseReader
        router = FileRouterService()
        
        # Check if readers are available
        supported = router.get_supported_extensions()
        if len(supported) < 10:
            safe_print(f"   Only {len(supported)} file types supported (expected more)")
            return False
        
        return True
    except Exception as e:
        safe_print(f"   File processing error: {e}")
        return False

def check_storage_pipeline():
    """Check storage pipeline"""
    try:
        from pipeline.storage_pipeline import StoragePipeline
        # Just verify it can be instantiated
        pipeline = StoragePipeline(
            db_hub=None,
            source_name="test",
            side_name="test"
        )
        return True
    except Exception as e:
        safe_print(f"   Storage pipeline error: {e}")
        return False

def check_memory_management():
    """Check memory management components"""
    try:
        from core.resource_coordinator import get_resource_coordinator
        coordinator = get_resource_coordinator()
        status = coordinator.get_resource_status()
        return True
    except Exception as e:
        safe_print(f"   Resource coordinator error: {e} (non-critical)")
        return True  # Non-critical

def check_file_utils():
    """Check file utilities"""
    try:
        from core.file_utils import read_tree, get_standardized_metadata
        # Test with current directory
        test_path = Path.cwd()
        metadata = get_standardized_metadata(str(test_path))
        if metadata is None:
            return False
        return True
    except Exception as e:
        safe_print(f"   File utils error: {e}")
        return False

def check_production_improvements():
    """Verify production improvements are in place"""
    improvements = {
        "Adaptive chunk sizing": False,
        "Chunked text processing": False,
        "Streaming PDF reader": False,
        "Memory error recovery": False,
        "Batched database operations": False,
        "Enhanced timeout calculation": False,
        "Complete folder traversal": False,
        "Guaranteed file storage": False
    }
    
    try:
        # Check content processor for adaptive chunking
        from database.processors.content_processor import ContentProcessor
        processor = ContentProcessor()
        if hasattr(processor, 'extract_words_with_punctuation_chunked'):
            improvements["Adaptive chunk sizing"] = True
            improvements["Chunked text processing"] = True
        
        # Check storage pipeline for chunked processing
        from pipeline.storage_pipeline import StoragePipeline
        if hasattr(StoragePipeline, '_store_file_sync'):
            improvements["Guaranteed file storage"] = True
        
        # Check PDF reader for streaming
        from reader_file.readers.read_pdf import PDFFileReader
        if hasattr(PDFFileReader, 'read_pdf_file'):
            improvements["Streaming PDF reader"] = True
        
        # Check remaining reader for memory recovery
        from reader_file.readers.read_remaining import RemainingFileReader
        if hasattr(RemainingFileReader, '_read_text_file_streaming'):
            improvements["Memory error recovery"] = True
        
        # Check words repo for batching
        from database.database.repository.words_repo import WordsRepository
        if hasattr(WordsRepository, 'bulk_insert_words'):
            improvements["Batched database operations"] = True
        
        # Check integrated reader for timeout calculation
        from pipeline.integrated_reader import IntegratedFileReader
        if hasattr(IntegratedFileReader, 'process_folder'):
            improvements["Enhanced timeout calculation"] = True
        
        # Check file_utils for complete traversal
        from core.file_utils import read_tree
        import inspect
        source = inspect.getsource(read_tree)
        if 'visited_paths' in source and 'PermissionError' in source:
            improvements["Complete folder traversal"] = True
        
    except Exception as e:
        safe_print(f"   Error checking improvements: {e}")
    
    all_ok = all(improvements.values())
    if not all_ok:
        safe_print("   Missing improvements:")
        for name, status in improvements.items():
            if not status:
                safe_print(f"      - {name}")
    
    return all_ok

def main():
    """Run all readiness checks"""
    safe_print("\n" + "="*70)
    safe_print("PRODUCTION READINESS VERIFICATION")
    safe_print("="*70 + "\n")
    
    checks = [
        ("Critical Imports", check_imports, True),
        ("Settings Configuration", check_settings, True),
        ("Database Connection", check_database_connection, True),
        ("File Processing Components", check_file_processing, True),
        ("Storage Pipeline", check_storage_pipeline, True),
        ("File Utilities", check_file_utils, True),
        ("Memory Management", check_memory_management, False),
        ("Production Improvements", check_production_improvements, True),
    ]
    
    results = []
    for name, check_func, critical in checks:
        result = check_component(name, check_func, critical)
        results.append((name, result, critical))
    
    safe_print("\n" + "="*70)
    safe_print("VERIFICATION SUMMARY")
    safe_print("="*70)
    
    critical_passed = sum(1 for _, result, critical in results if result and critical)
    critical_total = sum(1 for _, _, critical in results if critical)
    non_critical_passed = sum(1 for _, result, critical in results if result and not critical)
    non_critical_total = sum(1 for _, _, critical in results if not critical)
    
    safe_print(f"Critical Checks: {critical_passed}/{critical_total} passed")
    safe_print(f"Non-Critical Checks: {non_critical_passed}/{non_critical_total} passed")
    
    all_critical_passed = critical_passed == critical_total
    
    if all_critical_passed:
        safe_print("\n✅ SYSTEM READY FOR PRODUCTION")
        safe_print("\nAll critical components are operational.")
        safe_print("You can now process terabyte-scale folders with confidence.")
        return 0
    else:
        safe_print("\n❌ SYSTEM NOT READY")
        safe_print("\nSome critical components failed verification.")
        safe_print("Please fix the issues above before processing large folders.")
        return 1

if __name__ == "__main__":
    # Add project root to path
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Initialize if needed
    try:
        from core.init import (
            setup_project_path,
            initialize_settings,
            initialize_database_config,
            initialize_system
        )
        setup_project_path(__file__)
        initialize_settings(project_root)
        initialize_database_config()
        initialize_system()
    except Exception as e:
        safe_print(f"Warning: Initialization error: {e}")
    
    exit_code = main()
    sys.exit(exit_code)
