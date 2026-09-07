"""
Production-Ready Usage Example for Terabyte-Scale Folder Processing

This example demonstrates how to use IntegratedFileReader to process
entire terabyte-scale folders with zero data loss guarantees.
"""

from pipeline.integrated_reader import IntegratedFileReader
import logging

# Configure logging for production monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def process_terabyte_folder(folder_path: str, source_name: str, side_name: str, 
                           checkpoint_file: str = None, max_workers: int = 4):
    """
    Process a terabyte-scale folder with complete data preservation.
    
    Args:
        folder_path: Path to the folder to process (can be terabyte-scale)
        source_name: Source name for database storage (MANDATORY)
        side_name: Side name for database storage (MANDATORY)
        checkpoint_file: Optional checkpoint file path for resume capability
        max_workers: Number of parallel workers (default: 4)
    
    Returns:
        List of processing results
    """
    
    # Create IntegratedFileReader with production settings
    reader = IntegratedFileReader(
        max_workers=max_workers,
        enable_storage=True,  # Enable database storage
        storage_source=source_name,  # MANDATORY: Must be explicitly provided
        storage_side=side_name,  # MANDATORY: Must be explicitly provided
        enable_monitoring=True,  # Enable monitoring for large operations
        use_priority=True,  # Use priority-based scheduling for efficiency
        checkpoint_file=checkpoint_file  # Optional: For resume capability
    )
    
    try:
        # Process the entire folder
        # This will:
        # 1. Discover ALL files (including those with errors)
        # 2. Process each file (with error handling)
        # 3. Store ALL files in database (even with errors)
        # 4. Provide comprehensive statistics
        results = reader.process_folder(folder_path)
        
        # Get processing statistics
        stats = reader.get_statistics()
        storage_stats = reader.get_storage_statistics()
        
        # Display summary
        print("\n" + "="*70)
        print("📊 PROCESSING COMPLETE")
        print("="*70)
        print(f"Total Files Found:      {stats.get('total', 0):,}")
        print(f"Files Processed:        {stats.get('completed', 0):,}")
        print(f"Files Stored:           {storage_stats.get('completed', 0):,}")
        print(f"Duplicate Files:        {storage_stats.get('duplicates', 0):,}")
        print(f"Failed Files:           {stats.get('failed', 0):,}")
        print("="*70)
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error during processing: {e}")
        logging.error(f"Processing failed: {e}", exc_info=True)
        raise
    finally:
        # Cleanup is handled automatically by context manager
        # But we can also call it explicitly if not using context manager
        pass


# Example 1: Basic usage (as shown in documentation)
def example_basic():
    """Basic usage example"""
    reader = IntegratedFileReader(
        max_workers=4,
        enable_storage=True,
        storage_source="your_source",
        storage_side="your_side"
    )
    results = reader.process_folder("/path/to/terabyte/folder")
    return results


# Example 2: Production usage with checkpoint (recommended for large folders)
def example_with_checkpoint():
    """Production usage with checkpoint for resume capability"""
    reader = IntegratedFileReader(
        max_workers=4,
        enable_storage=True,
        storage_source="production_source",
        storage_side="production_side",
        checkpoint_file="checkpoint.json"  # Enables resume on interruption
    )
    results = reader.process_folder("/path/to/terabyte/folder")
    return results


# Example 3: Using as context manager (recommended)
def example_context_manager():
    """Using as context manager for automatic cleanup"""
    with IntegratedFileReader(
        max_workers=4,
        enable_storage=True,
        storage_source="your_source",
        storage_side="your_side",
        checkpoint_file="checkpoint.json"
    ) as reader:
        results = reader.process_folder("/path/to/terabyte/folder")
        
        # Get statistics
        stats = reader.get_statistics()
        storage_stats = reader.get_storage_statistics()
        
        print(f"Processed: {stats.get('completed', 0)} files")
        print(f"Stored: {storage_stats.get('completed', 0)} files")
        
        return results
    # Context manager automatically cleans up resources


# Example 4: Full production setup
def example_production():
    """Full production setup with error handling and monitoring"""
    folder_path = "/path/to/terabyte/folder"
    source_name = "production_source"
    side_name = "production_side"
    checkpoint_file = "checkpoint.json"
    
    try:
        results = process_terabyte_folder(
            folder_path=folder_path,
            source_name=source_name,
            side_name=side_name,
            checkpoint_file=checkpoint_file,
            max_workers=4
        )
        
        print(f"\n✅ Successfully processed {len(results)} files")
        return results
        
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
        print(f"💾 Checkpoint saved - can resume with same checkpoint_file")
        raise
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        print(f"💾 Checkpoint saved - can resume with same checkpoint_file")
        raise


if __name__ == "__main__":
    # Run the production example
    # Replace with your actual paths and source/side names
    example_production()
