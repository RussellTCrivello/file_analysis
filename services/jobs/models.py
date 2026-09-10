"""Serialization helpers for job records returned by the API."""
from typing import Any, Dict


def job_to_api(job: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a jobs-table row for JSON responses (client-safe)."""
    if job is None:
        return {}
    stats = job.get("stats") or {}
    return {
        "job_id": job.get("job_id"),
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "progress": job.get("progress"),
        "current_phase": job.get("current_phase"),
        "current_item": job.get("current_item"),
        "source": job.get("source"),
        "created_by": job.get("created_by"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "cancellation_requested": job.get("cancellation_requested"),
        "pause_requested": job.get("pause_requested"),
        "statistics": {
            "files_discovered": stats.get("total_files") or stats.get("files_discovered"),
            "files_processed": stats.get("files_done") or stats.get("files_processed"),
            "files_succeeded": stats.get("files_completed") or stats.get("files_stored"),
            "files_failed": stats.get("files_failed"),
            "files_skipped": stats.get("files_skipped"),
            "duplicates": stats.get("files_duplicates") or stats.get("duplicates"),
            "bytes_processed": stats.get("bytes_processed") or stats.get("estimated_bytes"),
        },
        "result_summary": job.get("result_summary"),
    }
