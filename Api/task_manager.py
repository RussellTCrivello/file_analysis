import time
import uuid
import logging
from typing import Dict, Optional, List, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

from concurrency import ThreadManager, ThreadPriority

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    """Task progress information"""
    task_id: str
    status: TaskStatus
    current: int = 0
    total: int = 0
    label: str = ""
    message: str = ""
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    logs: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'current': self.current,
            'total': self.total,
            'label': self.label,
            'message': self.message,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress_percent': (self.current / self.total * 100) if self.total > 0 else 0,
            'logs': self.logs[-50:]  # Last 50 log entries
        }


class FileProcessingTaskManager:
    """
    Manages background file processing tasks with progress tracking.
    Allows multiple tasks to run concurrently without blocking the web interface.
    """
    
    def __init__(self, max_concurrent_tasks: int = 8):
        """
        Initialize task manager.
        
        Args:
            max_concurrent_tasks: Maximum number of concurrent processing tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self._tasks: Dict[str, TaskProgress] = {}
        
        self._thread_manager = ThreadManager()
        self._thread_manager.start_monitoring(interval=2.0)
        
        # Thread-safe locks (still needed for task management)
        import threading
        self._task_lock = threading.Lock()
        self._active_thread_ids: Dict[str, str] = {}  # Map task_id -> thread_id
        self._thread_lock = threading.Lock()
        # Pause control: track paused tasks and their pause events
        self._paused_tasks: Dict[str, threading.Event] = {}
        self._pause_lock = threading.Lock()
        
    def create_task(
        self,
        file_path: str,
        source_id: int,
        side_id: int,
        task_name: Optional[str] = None
    ) -> str:
        """
        Create a new processing task and start it in the background.
        
        Args:
            file_path: Path to file or directory to process
            source_id: Source ID for storage
            side_id: Side ID for storage
            task_name: Optional task name for identification
        
        Returns:
            Task ID for tracking progress
        """
        task_id = str(uuid.uuid4())
        
        # Check if we can start a new task
        with self._thread_lock:
            stats = self._thread_manager.get_statistics()
            active_count = stats.get('running', 0)
            if active_count >= self.max_concurrent_tasks:
                raise RuntimeError(f"Maximum concurrent tasks ({self.max_concurrent_tasks}) reached")
        
        # Create task progress tracker
        progress = TaskProgress(
            task_id=task_id,
            status=TaskStatus.PENDING,
            label="Initializing...",
            message=f"Preparing to process: {file_path}",
            started_at=datetime.now()
        )
        
        with self._task_lock:
            self._tasks[task_id] = progress
        
        thread_name = f"task_{task_id[:8]}_{task_name or 'processing'}"
        thread_id = self._thread_manager.create_thread(
            name=thread_name,
            target=self._process_task,
            args=(task_id, file_path, source_id, side_id, task_name),
            priority=ThreadPriority.NORMAL,
            auto_start=True
        )
        
        with self._thread_lock:
            self._active_thread_ids[task_id] = thread_id
        
        logger.info(f"Created processing task {task_id} for {file_path} (thread: {thread_id})")
        
        return task_id
    
    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """
        Get progress for a task.
        
        Args:
            task_id: Task ID
        
        Returns:
            TaskProgress object or None if task not found
        """
        with self._task_lock:
            return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[TaskProgress]:
        """Get all tasks"""
        with self._task_lock:
            return list(self._tasks.values())
    
    def pause_task(self, task_id: str) -> bool:
        """
        Pause a running task.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if task was paused, False if not found or cannot be paused
        """
        with self._task_lock:
            if task_id not in self._tasks:
                return False
            
            progress = self._tasks[task_id]
            if progress.status not in (TaskStatus.RUNNING, TaskStatus.PENDING):
                return False
            
            # Set status to paused
            progress.status = TaskStatus.PAUSED
            progress.message = "Task paused by user"
            
            # Create or get pause event
            with self._pause_lock:
                if task_id not in self._paused_tasks:
                    self._paused_tasks[task_id] = threading.Event()
                # Set the event to signal pause
                self._paused_tasks[task_id].set()
            
            self._add_task_log(task_id, 'info', 'Task paused by user')
            logger.info(f"Task {task_id} paused")
            return True
    
    def resume_task(self, task_id: str) -> bool:
        """
        Resume a paused task.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if task was resumed, False if not found or cannot be resumed
        """
        with self._task_lock:
            if task_id not in self._tasks:
                return False
            
            progress = self._tasks[task_id]
            if progress.status != TaskStatus.PAUSED:
                return False
            
            # Set status back to running
            progress.status = TaskStatus.RUNNING
            progress.message = "Task resumed by user"
            
            # Clear the pause event to allow processing to continue
            with self._pause_lock:
                if task_id in self._paused_tasks:
                    self._paused_tasks[task_id].clear()
            
            self._add_task_log(task_id, 'info', 'Task resumed by user')
            logger.info(f"Task {task_id} resumed")
            return True
    
    def is_task_paused(self, task_id: str) -> bool:
        """
        Check if a task is currently paused.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if task is paused, False otherwise
        """
        with self._pause_lock:
            if task_id not in self._paused_tasks:
                return False
            return self._paused_tasks[task_id].is_set()
    
    def wait_if_paused(self, task_id: str, timeout: float = 0.1) -> bool:
        """
        Wait if task is paused. This should be called periodically in processing loops.
        
        Args:
            task_id: Task ID
            timeout: Timeout in seconds to check pause status
        
        Returns:
            True if task should continue (not paused or resumed), False if cancelled
        """
        with self._task_lock:
            if task_id not in self._tasks:
                return False
            
            progress = self._tasks[task_id]
            if progress.status == TaskStatus.CANCELLED:
                return False
        
        # Check if paused and wait
        with self._pause_lock:
            if task_id in self._paused_tasks:
                event = self._paused_tasks[task_id]
                if event.is_set():
                    # Task is paused, wait in a loop checking for resume or cancel
                    while event.is_set():
                        # Check for cancellation
                        with self._task_lock:
                            if task_id in self._tasks:
                                if self._tasks[task_id].status == TaskStatus.CANCELLED:
                                    return False
                        
                        # Wait briefly and check again
                        event.wait(timeout=timeout)
        
        return True
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.
        
        Args:
            task_id: Task ID
        
        Returns:
            True if task was cancelled, False if not found or already completed
        """
        with self._task_lock:
            if task_id not in self._tasks:
                return False
            
            progress = self._tasks[task_id]
            if progress.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            
            progress.status = TaskStatus.CANCELLED
            progress.message = "Task cancelled by user"
            progress.completed_at = datetime.now()
            
            # Clear pause event if exists to allow cancellation to proceed
            with self._pause_lock:
                if task_id in self._paused_tasks:
                    self._paused_tasks[task_id].clear()
            
            return True
    
    def _process_task(
        self,
        task_id: str,
        file_path: str,
        source_id: int,
        side_id: int,
        task_name: Optional[str]
    ):
        """
        Process a file in the background.
        This runs in a separate thread and updates progress as it goes.
        """
        try:
            # Update status to running
            with self._task_lock:
                if task_id in self._tasks:
                    self._tasks[task_id].status = TaskStatus.RUNNING
                    self._tasks[task_id].label = "Starting processing..."
                    self._tasks[task_id].message = f"Processing: {file_path}"
            
            # Import here to avoid circular dependencies
            import os
            import sys
            from pathlib import Path
            
            # Add project root to path
            project_root = str(Path(__file__).parent.parent.parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            
            from pipeline.integrated_reader import IntegratedFileReader  
            from core.validation.validation import PathValidator, ValidationError
            from Hdg_Err_Ex_Log import handle_error, ErrorCategory, ErrorSeverity, ErrorContext
            
            # Validate and normalize path
            try:
                normalized_path = file_path.strip().strip('"\'')
                normalized_path = os.path.expanduser(normalized_path)
                normalized_path = os.path.abspath(normalized_path)
                
                if os.path.isfile(normalized_path):
                    validated_path = PathValidator.validate_file_path(normalized_path)
                    is_directory = False
                elif os.path.isdir(normalized_path):
                    validated_path = PathValidator.validate_directory_path(normalized_path)
                    is_directory = True
                else:
                    raise ValidationError(f"Path does not exist: {normalized_path}")
            except ValidationError as e:
                self._update_task_error(task_id, f"Validation error: {str(e)}")
                return
            
            try:



                from database import get_source_by_name, get_side_by_name
                source_info = get_source_by_name(source_id)
                if source_info:
                    source_name = source_info.get('name')
                
                side_info = get_side_by_name(side_id)
                if side_info:
                    side_name = side_info.get('name')
            except Exception as e:
                logger.warning(f"Could not get source/side names: {e}, using defaults")
            
            # Initialize reader with storage enabled
            reader = None
            try:
                reader = IntegratedFileReader(
                    max_workers=self.max_concurrent_tasks,
                    enable_monitoring=True,
                    monitor_interval=2.0,
                    use_priority=True,
                    enable_storage=True,
                    storage_source=source_name,
                    storage_side=side_name
                )
                reader.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize IntegratedFileReader: {e}", exc_info=True)
                self._update_task_error(task_id, f"Failed to initialize reader: {str(e)}")
                return
            
            # Track progress
            file_count = [0]
            last_stats_update = [time.time()]
            STATS_UPDATE_INTERVAL = 1.0  # Update stats every second
            
            def update_progress_from_stats():
                """Update progress from IntegratedFileReader statistics"""
                try:
                    stats = reader.get_statistics()
                    total = stats.get('total', 0)
                    completed = stats.get('completed', 0)
                    failed = stats.get('failed', 0)
                    in_progress = stats.get('in_progress', 0)
                    
                    # Update progress
                    if total > 0:
                        progress_percent = (completed / total * 100) if total > 0 else 0
                        progress_label = f"Processing: {completed}/{total} files ({progress_percent:.1f}%)"
                        if failed > 0:
                            progress_label += f" | Failed: {failed}"
                        if in_progress > 0:
                            progress_label += f" | In Progress: {in_progress}"
                        
                        self._update_task_progress(
                            task_id,
                            current=completed,
                            total=total,
                            label=progress_label,
                            message=f"Completed: {completed}, Failed: {failed}, In Progress: {in_progress}"
                        )
                        
                        # Add log entry periodically
                        current_time = time.time()
                        if current_time - last_stats_update[0] >= STATS_UPDATE_INTERVAL:
                            self._add_task_log(
                                task_id, 
                                'info', 
                                f"Progress: {completed}/{total} files processed ({progress_percent:.1f}%) | Failed: {failed} | In Progress: {in_progress}"
                            )
                            last_stats_update[0] = current_time
                except Exception as e:
                    logger.debug(f"Error updating progress from stats: {e}")
            
            # Process with IntegratedFileReader
            with ErrorContext(
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={"file_path": validated_path, "source_id": source_id, "side_id": side_id}
            ):
                try:
                    monitoring_active = [True]
                    
                    def progress_monitor():
                        """Monitor progress and update task status"""
                        while monitoring_active[0]:
                            if not self.wait_if_paused(task_id, timeout=1.0):
                                break
                            
                            # Check if task is cancelled
                            with self._task_lock:
                                if task_id in self._tasks:
                                    if self._tasks[task_id].status == TaskStatus.CANCELLED:
                                        break
                            
                            # Update progress from reader stats
                            update_progress_from_stats()
                            
                            # Check if reader is complete
                            try:
                                if reader.is_complete():
                                    break
                            except Exception as e:
                                # Log but continue - reader may not have is_complete method
                                logger.debug(f"Error checking reader completion: {e}")
                                pass
                            
                            time.sleep(0.5)  # Check every 0.5 seconds
                    
                    monitor_thread_id = self._thread_manager.create_thread(
                        name=f"monitor_{task_id[:8]}",
                        target=progress_monitor,
                        priority=ThreadPriority.LOW,
                        auto_start=True
                    )
                    
                    # Process file or folder
                    results = []
                    if is_directory:
                        results = reader.process_folder(validated_path)
                    else:
                        result = reader.process_single_file(validated_path)
                        results = [result] if result else []
                    
                    monitoring_active[0] = False
                    try:
                        self._thread_manager.stop_thread(monitor_thread_id, timeout=2.0)
                    except Exception as e:
                        logger.debug(f"Error stopping monitor thread: {e}")
                    
                    # Final progress update
                    stats = reader.get_statistics()
                    final_completed = stats.get('completed', len(results))
                    final_total = stats.get('total', len(results))
                    final_failed = stats.get('failed', 0)
                    
                    # Check for cancellation
                    with self._task_lock:
                        if task_id in self._tasks:
                            if self._tasks[task_id].status == TaskStatus.CANCELLED:
                                self._add_task_log(task_id, 'info', 'Processing cancelled')
                                return
                    
                    # Log final results
                    if results:
                        for result in results:
                            if result:
                                file_name = result.get('Metadata', {}).get('name', 'Unknown')
                                file_path = result.get('Metadata', {}).get('path', '')
                                file_type = result.get('Metadata', {}).get('type', 'Unknown')
                                file_size = result.get('Metadata', {}).get('size_bytes', 0)
                                has_error = bool(result.get('Content', {}).get('error'))
                                
                                log_lines = []
                                log_lines.append(f"File: {file_name}")
                                log_lines.append(f"Path: {file_path}")
                                log_lines.append(f"Type: {file_type}")
                                log_lines.append(f"Size: {file_size:,} bytes")
                                log_lines.append(f"Status: {'Successful' if not has_error else 'Failed'}")
                                log_lines.append(f"Processing Status: {'Completed' if not has_error else 'Failed'}")
                                log_lines.append(f"Storage Status: Stored")
                                
                                self._add_task_log(task_id, 'info' if not has_error else 'error', "\n".join(log_lines))
                    
                except KeyboardInterrupt:
                    # Task was cancelled
                    with self._task_lock:
                        if task_id in self._tasks:
                            if self._tasks[task_id].status == TaskStatus.CANCELLED:
                                self._add_task_log(task_id, 'info', 'Processing cancelled')
                                return
                finally:
                    # Cleanup reader
                    if reader:
                        try:
                            reader.shutdown()
                        except Exception as cleanup_error:
                            logger.warning(f"Error during reader cleanup: {cleanup_error}")
            
            # 🔔 FINAL NOTIFICATION FLUSH: Ensure all notifications are persisted
            try:
                from core.monitoring.notification_service import get_notification_service
                notification_service = get_notification_service()
                pending_count = notification_service.get_pending_count()
                if pending_count > 0:
                    flushed = notification_service.flush_pending_notifications()
                    if flushed > 0:
                        self._add_task_log(task_id, 'info', f"Flushed {flushed} notification(s) to database")
                        logger.info(f"Flushed {flushed} notification(s) after processing completion")
            except Exception as e:
                logger.warning(f"Could not flush notifications after processing: {e}")
            
            # Get final statistics
            try:
                if reader:
                    final_stats = reader.get_statistics()
                    final_completed = final_stats.get('completed', 0)
                    final_total = final_stats.get('total', 0)
                    final_failed = final_stats.get('failed', 0)
                else:
                    final_completed = len(results) if results else 0
                    final_total = final_completed
                    final_failed = 0
            except:
                final_completed = len(results) if results else 0
                final_total = final_completed
                final_failed = 0
            
            # Mark as completed
            completion_message = f"Successfully processed {final_completed} file(s)"
            if final_failed > 0:
                completion_message += f" ({final_failed} failed)"
            
            self._update_task_progress(
                task_id,
                current=final_completed,
                total=final_total if final_total > 0 else final_completed,
                label="Completed",
                message=completion_message
            )
            
            with self._task_lock:
                if task_id in self._tasks:
                    self._tasks[task_id].status = TaskStatus.COMPLETED
                    self._tasks[task_id].completed_at = datetime.now()
                    self._add_task_log(task_id, 'success', f"Processing completed successfully: {final_completed} files processed")
            
            logger.info(f"Task {task_id} completed successfully: {final_completed} files processed")
            
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
            self._update_task_error(task_id, f"Processing error: {str(e)}")
        finally:
            # Clean up thread reference and pause event
            with self._thread_lock:
                thread_id = self._active_thread_ids.pop(task_id, None)
                if thread_id:
                    try:
                        self._thread_manager.stop_thread(thread_id, timeout=5.0)
                    except Exception as e:
                        logger.debug(f"Error stopping thread {thread_id}: {e}")
            with self._pause_lock:
                self._paused_tasks.pop(task_id, None)
    
    def _update_task_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        label: str = "",
        message: str = ""
    ):
        """Update task progress"""
        with self._task_lock:
            if task_id in self._tasks:
                progress = self._tasks[task_id]
                progress.current = current
                progress.total = total
                if label:
                    progress.label = label
                if message:
                    progress.message = message
    
    def _update_task_error(self, task_id: str, error: str):
        """Update task with error"""
        with self._task_lock:
            if task_id in self._tasks:
                progress = self._tasks[task_id]
                progress.status = TaskStatus.FAILED
                progress.error = error
                progress.message = f"Error: {error}"
                progress.completed_at = datetime.now()
                self._add_task_log(task_id, 'error', error)
    
    def _add_task_log(self, task_id: str, log_type: str, message: str):
        """Add log entry to task"""
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id].logs.append({
                    'type': log_type,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
                # Keep only last 1000 log entries
                if len(self._tasks[task_id].logs) > 1000:
                    self._tasks[task_id].logs = self._tasks[task_id].logs[-1000:]
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        Clean up old completed/failed tasks.
        
        Args:
            max_age_hours: Maximum age in hours for tasks to keep
        """
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        
        with self._task_lock:
            tasks_to_remove = []
            for task_id, progress in self._tasks.items():
                if progress.completed_at:
                    task_time = progress.completed_at.timestamp()
                    if task_time < cutoff_time:
                        tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self._tasks[task_id]
                logger.debug(f"Cleaned up old task: {task_id}")
            
            if tasks_to_remove:
                logger.info(f"Cleaned up {len(tasks_to_remove)} old task(s)")


# Global task manager instance
_task_manager: Optional[FileProcessingTaskManager] = None
import threading
_manager_lock = threading.Lock()


def get_task_manager() -> FileProcessingTaskManager:
    """Get or create global task manager instance"""
    global _task_manager
    
    with _manager_lock:
        if _task_manager is None:
            _task_manager = FileProcessingTaskManager(max_concurrent_tasks=5)
        
        return _task_manager

