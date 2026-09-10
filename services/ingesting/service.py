"""Ingestion service: the engine behind the Input UI, the jobs API and the
CLI compatibility layer.

Wraps the existing processing engine (``pipeline.integrated_reader.
IntegratedFileReader``) with:

* request validation + path-safety enforcement (SEC-06);
* dry-run discovery (no database writes);
* cooperative cancel/pause wiring into the engine;
* real progress callbacks (never fake percentages);
* structured results.

No argparse / input() / print / exit codes — that belongs to adapters.
"""
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.path_safety import (
    configured_ingestion_roots,
    validate_ingestion_path,
)
from services.ingesting.options import IngestionOptions, IngestionRequest  # noqa: F401


class IngestionValidationError(ValueError):
    """Raised for invalid requests; ``str(exc)`` is client-safe."""


@dataclass
class IngestionResult:
    """Structured outcome of one ingestion execution."""

    success: bool
    cancelled: bool = False
    paused: bool = False
    dry_run: bool = False
    stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "cancelled": self.cancelled,
            "paused": self.paused,
            "dry_run": self.dry_run,
            "stats": self.stats,
            "warnings": self.warnings[:200],
            "errors": self.errors[:200],
            "result_summary": {
                "files_total": self.stats.get("files_total"),
                "files_stored": self.stats.get("files_stored"),
                "files_duplicates": self.stats.get("files_duplicates"),
                "files_failed": self.stats.get("files_failed"),
                "files_skipped": self.stats.get("files_skipped"),
            },
        }


class _ControlRequested(Exception):
    """Internal: cooperative cancel/pause hit during engine execution."""

    def __init__(self, paused: bool):
        super().__init__("pause" if paused else "cancel")
        self.paused = paused


class IngestionService:
    """Runs ingestion requests against the shared processing engine."""

    MAX_FILE_PATHS = 5000

    def __init__(self, reader_factory: Optional[Callable[..., Any]] = None):
        # Injectable for tests; production uses the real engine.
        self._reader_factory = reader_factory

    # ------------------------------------------------------------------
    # Validation (spec sections 16/23): all request input is untrusted.
    # ------------------------------------------------------------------
    def validate(self, request: IngestionRequest) -> IngestionRequest:
        if not isinstance(request, IngestionRequest):
            raise IngestionValidationError("Invalid request type")
        if bool(request.path) == bool(request.file_paths):
            raise IngestionValidationError(
                "Provide exactly one of 'path' or 'file_paths'"
            )
        if not (request.source or "").strip() or not (request.side or "").strip():
            raise IngestionValidationError(
                "source and side are mandatory - no defaults are allowed"
            )
        request.options = request.options.sanitized() if request.options else IngestionOptions()

        paths: List[str] = []
        if request.path:
            paths = [request.path]
        else:
            if not isinstance(request.file_paths, list):
                raise IngestionValidationError("file_paths must be a list")
            if len(request.file_paths) > self.MAX_FILE_PATHS:
                raise IngestionValidationError(
                    f"Too many file paths (max {self.MAX_FILE_PATHS})"
                )
            paths = [str(p) for p in request.file_paths]
        if not paths:
            raise IngestionValidationError("No paths provided")

        validated: List[str] = []
        for raw in paths:
            try:
                resolved = validate_ingestion_path(raw)
            except Exception as exc:
                # Fail closed: without configured roots or with a bad path,
                # server-side access is denied (SEC-06).
                raise IngestionValidationError(
                    f"Path not allowed: {Path(str(raw)).name}"
                ) from exc
            if not resolved.exists():
                raise IngestionValidationError(
                    f"Path does not exist: {Path(str(raw)).name}"
                )
            validated.append(str(resolved))
        # Second pass invariants that don't need per-path errors surfaced.
        if request.path:
            request.path = validated[0]
        else:
            request.file_paths = validated
        request.source = request.source.strip()
        request.side = request.side.strip()
        return request

    # ------------------------------------------------------------------
    # Discovery / dry run (spec section 8): no DB writes, real numbers.
    # ------------------------------------------------------------------
    def discover(self, request: IngestionRequest) -> Dict[str, Any]:
        """Walk the requested paths and report what *would* be processed."""
        roots = configured_ingestion_roots()
        target = Path(request.path) if request.path else None
        files: List[Dict[str, Any]] = []
        if target and target.is_file():
            files = [self._file_entry(target)]
        elif target:
            files = self._walk(target, recursive=request.recursive)
        else:
            for p in request.file_paths:
                fp = Path(p)
                if fp.is_file():
                    files.append(self._file_entry(fp))
                elif fp.is_dir():
                    files.extend(self._walk(fp, recursive=request.recursive))

        try:
            from reader_file.services.file_router_service import FileRouterService

            supported = {
                str(e).lower().lstrip(".")
                for e in (FileRouterService().get_supported_extensions() or set())
            }
        except Exception:
            supported = set()

        eligible, unsupported = [], 0
        total_bytes = 0
        for f in files:
            ext = (f.get("extension") or "").lower().lstrip(".")
            if ext and ext not in supported:
                unsupported += 1
                continue
            eligible.append(f)
            total_bytes += f.get("size_bytes") or 0

        return {
            "files_discovered": len(files),
            "files_eligible": len(eligible),
            "files_unsupported": unsupported,
            "estimated_bytes": total_bytes,
            "sample_files": [
                {"path": f["path"], "size": f.get("size_bytes")}
                for f in eligible[:20]
            ],
            "ingestion_roots_configured": bool(roots),
            "dry_run": True,
        }

    @staticmethod
    def _file_entry(p: Path) -> Dict[str, Any]:
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        return {
            "path": str(p),
            "name": p.name,
            "extension": p.suffix.lower(),
            "size_bytes": size,
            "type": "FILE",
        }

    def _walk(self, root: Path, recursive: bool) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            entries = list(os.scandir(root))
        except OSError:
            return out
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    out.append(self._file_entry(Path(entry.path)))
                elif entry.is_dir(follow_symlinks=False) and recursive:
                    out.extend(self._walk(Path(entry.path), recursive=True))
            except OSError:
                continue
        return out

    # ------------------------------------------------------------------
    # Execution. Called by the JobManager worker thread (or the CLI
    # adapter in compatibility mode). Reports real progress via callback.
    # ------------------------------------------------------------------
    def run(
        self,
        request: IngestionRequest,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
        pause_cb: Optional[Callable[[], bool]] = None,
        engine_cb: Optional[Callable[[Any], None]] = None,
    ) -> IngestionResult:
        request = self.validate(request)
        result = IngestionResult(
            success=False, dry_run=request.dry_run,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        if request.dry_run:
            result.stats = self.discover(request)
            result.success = True
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        IntegratedFileReader = self._reader_factory or self._default_reader_factory
        reader = self._make_reader(IntegratedFileReader, request)
        try:
            if engine_cb is not None:
                try:
                    engine_cb(reader)
                except Exception:
                    pass
            reader.progress_callback = self._wrap_progress(progress_cb)
            # Poll control flags from a background sentinel so a cancel
            # request lands even while the engine waits on worker threads.
            sentinel_stop = threading.Event()

            def _sentinel():
                while not sentinel_stop.wait(0.5):
                    try:
                        if cancel_cb and cancel_cb():
                            reader.request_cancel()
                        if pause_cb and pause_cb():
                            reader.request_pause()
                    except Exception:
                        continue

            sentinel = threading.Thread(target=_sentinel, name="job-control-sentinel", daemon=True)
            sentinel.start()
            try:
                if request.path:
                    target = Path(request.path)
                    if target.is_file():
                        result.stats["files_total"] = 1
                        res = reader.process_single_file(request.path)
                        result.results = [res] if res else []
                    else:
                        result.results = reader.process_folder(request.path) or []
                else:
                    result.results = self._run_file_list(reader, request)
            finally:
                sentinel_stop.set()

            # Outcome
            cancelled = reader.is_cancel_requested()
            paused = (not cancelled) and reader.is_pause_requested()
            result.cancelled = cancelled
            result.paused = paused
            result.stats.update(self._collect_stats(reader, result.results))
            result.success = not cancelled and not paused
            if cancelled:
                result.warnings.append("Job cancelled by request; files already stored remain in the database")
            if paused:
                result.warnings.append("Job paused at a safe boundary; resume to continue")
        except _ControlRequested as ctrl:
            result.cancelled = not ctrl.paused
            result.paused = ctrl.paused
            result.warnings.append(
                "Job paused at a safe boundary" if ctrl.paused
                else "Job cancelled by request"
            )
        except Exception as exc:
            # Surface a sanitized message; full detail goes to server logs.
            from core.errors import client_safe_message

            result.errors.append(client_safe_message(exc, subsystem="services.ingesting"))
        finally:
            try:
                reader.__exit__(None, None, None)
            except Exception:
                pass
            result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    # ------------------------------------------------------------------
    def _make_reader(self, factory, request: IngestionRequest):
        import inspect

        opts = request.options
        workers = opts.max_workers or 0
        kwargs: Dict[str, Any] = {
            "enable_storage": True,
            "storage_source": request.source,
            "storage_side": request.side,
        }
        if workers:
            kwargs["max_workers"] = workers
        if opts.enable_monitoring is not None:
            kwargs["enable_monitoring"] = bool(opts.enable_monitoring)
        try:
            sig = inspect.signature(factory)
            if "checkpoint_file" in sig.parameters:
                kwargs["checkpoint_file"] = self._checkpoint_file(request)
        except (TypeError, ValueError):
            pass
        return factory(**kwargs)

    @staticmethod
    def _checkpoint_file(request: IngestionRequest) -> Optional[str]:
        """Checkpoint policy -> concrete file (mirrors the CLI's scheme)."""
        import hashlib

        policy = request.options.checkpoint if request.options else "auto"
        if policy == "off" or not request.path:
            return None
        try:
            from core.app_paths import get_checkpoints_dir

            ckpt_dir = get_checkpoints_dir()
        except Exception:
            ckpt_dir = Path("data/checkpoints")
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(str(Path(request.path).resolve()).encode()).hexdigest()[:16]
        path = ckpt_dir / f"checkpoint_{digest}_{request.source}_{request.side}.json"
        if policy == "fresh" and path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        return str(path)

    def _run_file_list(self, reader, request: IngestionRequest) -> List[Dict[str, Any]]:
        """Process an explicit file list through the engine workers."""
        files = []
        for p in request.file_paths:
            fp = Path(p)
            files.append({
                "path": str(fp),
                "name": fp.name,
                "extension": fp.suffix.lower(),
                "size_bytes": fp.stat().st_size if fp.exists() else 0,
                "type": "FILE",
            })
        reader._set_current(phase="Processing files")
        results: List[Dict[str, Any]] = []
        # Single worker per file keeps per-file results identical to the
        # engine's own semantics; concurrency comes from the engine's batch
        # path for folder jobs and from job-level concurrency for lists.
        for file_info in files:
            if reader._control_requested():
                break
            reader._set_current(file_path=file_info["path"])
            res = reader.process_single_file(file_info["path"])
            if res:
                results.append(res)
            reader._notify_progress()
        reader._processing_stats["total"] = len(files)
        reader._processing_stats["completed"] = len(results)
        return results

    def _wrap_progress(self, cb):
        if cb is None:
            return None

        def _cb(snapshot):
            cb(snapshot)

        return _cb

    @staticmethod
    def _default_reader_factory(**kwargs):
        from pipeline.integrated_reader import IntegratedFileReader

        return IntegratedFileReader(**kwargs)

    @staticmethod
    def _collect_stats(reader, results) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        try:
            live = reader.get_live_progress()
            stats.update({
                "files_total": live.get("total_files"),
                "files_processed": live.get("files_done"),
                "files_succeeded": live.get("files_completed"),
                "files_failed": live.get("files_failed"),
            })
        except Exception:
            pass
        try:
            storage = reader.get_storage_statistics() or {}
            stats.update({
                "files_stored": storage.get("completed", 0),
                "files_duplicates": storage.get("duplicates", 0),
                "storage_failed": storage.get("failed", 0),
            })
        except Exception:
            pass
        if results:
            bytes_total = 0
            for r in results:
                if isinstance(r, dict):
                    try:
                        bytes_total += int(r.get("file_size") or 0)
                    except (TypeError, ValueError):
                        pass
            stats["bytes_processed"] = bytes_total
        return stats
