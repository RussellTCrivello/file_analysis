# Job System

The unified job architecture executes all long-running operations
(ingestion, domain import, backup restore, server batch import). The HTTP
layer only creates and controls jobs; a worker thread runs the operation
through the same service layer the CLI uses.

## Job lifecycle

```
POST /api/input/jobs        (or /api/import/jobs)
        │  validate request server-side (fail fast, no doomed job rows)
        ▼
Persist job (QUEUED)  ──►  worker thread (concurrency-limited)
        │                       │
        ▼                       ▼
    202 + job_id           RUNNING (progress persisted from real
        │                  worker state: files done, phase, current file)
        │                       │
        │        ┌──────────────┼──────────────────┐
        ▼        ▼              ▼                  ▼
   COMPLETED  COMPLETED_    CANCELLED          PAUSED
   (or WITH_  WITH_WARNINGS (cooperative,      (safe boundary;
    WARNINGS)               at file boundary)   resume → new job,
                                                checkpoint skips done work)
```

## Job record

`jobs` table (migration 0006, additive): `job_id`, `job_type`, `status`,
`progress`, `current_phase`, `current_item` (current file), `source`,
`options` (JSONB), `stats` (JSONB), `errors`, `warnings`, `result_summary`,
`created_by`, `created_at/started_at/completed_at`, `cancellation_requested`,
`pause_requested`.

States: `QUEUED → RUNNING → {PAUSED, CANCELLING} → {CANCELLED, COMPLETED,
COMPLETED_WITH_WARNINGS, FAILED}` (see `services/jobs/job_state.py`; illegal
transitions raise).

## Real progress

Progress is computed from the processing engine's live worker stats
(`IntegratedFileReader.get_live_progress()`): total files, completed, failed,
percent, current file, current phase. Nothing is simulated. The engine calls
the job system's progress callback as workers finish each file; the manager
persists (throttled to ~1 s) and publishes to SSE subscribers.

## Events

`job_events` records `JOB_CREATED`, `JOB_STARTED`, `PHASE_*`, `FILE_*`,
`DUPLICATE_DETECTED`, `WARNING`, `ERROR`, `JOB_COMPLETED`, `JOB_CANCELLED`.
Per-file events are **sampled** above `JOBS_EVENT_SAMPLE_THRESHOLD` (default
500) with an explicit WARNING noting the sampling; errors, duplicates and
lifecycle events are always kept. Consumers: `GET /api/jobs/{id}/events`
(polling, works everywhere incl. multi-worker gunicorn) and
`GET /api/jobs/stream` (SSE, single-process; the UI auto-falls back to 2 s
polling).

## Cancellation

Cooperative: `POST /api/jobs/{id}/cancel` sets `cancellation_requested`
(DB) and signals the in-process engine (`request_cancel()`). Workers stop
starting new files; in-flight files finish. Every file storage is its own
transaction, so the database stays consistent.QUEUED jobs are cancelled
immediately.

## Pause / Resume

Pause = cooperative stop at the next file boundary (`PAUSED`). Resume
creates a successor job with identical options; the engine's checkpoint
manager (per source/side/folder hash) skips already-processed files, and
content deduplication (`identity = hash + source + side`) guarantees no
duplicate records even without a checkpoint.

## Retry

`POST /api/jobs/{id}/retry` re-runs a FAILED/CANCELLED/
COMPLETED_WITH_WARNINGS job as a NEW job with identical options. Safety comes
from deduplication + checkpoints; a retry never duplicates database records.

## Crash recovery

On startup / readiness check, `JobManager.recover_stale_jobs()` marks jobs
stuck in RUNNING/CANCELLING beyond `JOBS_STALE_SECONDS` (default 6 h) as
FAILED with an explanatory error - identifiable, never deleted. Already
stored files remain stored; Retry/resume skips them.

## Concurrency limits

`JOBS_MAX_CONCURRENT` (default 2) running jobs; per-job worker threads come
from the engine (`processing.max_workers`, engine clamps to safe values);
database writes are bounded by the engine's storage semaphore (a fraction of
the DB pool). All env-overridable at read time (defaults < settings file <
environment).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `JOBS_MAX_CONCURRENT` | 2 | max simultaneously RUNNING jobs |
| `JOBS_STALE_SECONDS` | 21600 | crash-recovery threshold |
| `JOBS_PROGRESS_INTERVAL` | 1.0 | min seconds between progress persists |
| `JOBS_EVENT_SAMPLE_THRESHOLD` | 500 | per-file event cap before sampling |
| `OPERATIONS_MAX_UPLOAD_MB` | 2048 | upload staging size limit |
