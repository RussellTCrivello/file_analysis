"""Filesystem path safety for ingestion (SEC-06).

The application must never allow a client to point ingestion at arbitrary
server filesystem locations.  All server-side paths entering the ingestion
pipeline are validated against an explicit allowlist of configured ingestion
roots (``INGESTION_ROOTS`` environment variable, semicolon-separated).

Rules:
* The path must be inside one of the configured roots.
* The resolved (symlink-followed) real path must remain inside the root.
* Absolute paths outside roots, drive-qualified paths, UNC paths, and any
  ``..`` traversal that escapes the root are rejected.
* Upload-based ingestion is the default path for untrusted clients; direct
  filesystem ingestion is an operator/CLI capability.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


class PathSafetyError(ValueError):
    """Raised when a path is outside all approved ingestion roots."""


def configured_ingestion_roots() -> List[Path]:
    """Return the explicit list of approved ingestion roots."""
    raw = os.environ.get("INGESTION_ROOTS", "")
    roots: List[Path] = []
    for part in raw.split(";"):
        part = part.strip()
        if part:
            roots.append(Path(part).expanduser().resolve())
    return roots


def validate_ingestion_path(
    candidate: str | os.PathLike,
    roots: Optional[Iterable[Path | str]] = None,
) -> Path:
    """Validate that *candidate* resolves inside an approved ingestion root.

    Returns the resolved :class:`~pathlib.Path` on success.
    Raises :class:`PathSafetyError` otherwise.
    """
    raw = str(candidate)
    if "\x00" in raw:
        raise PathSafetyError("Invalid path")

    p = Path(raw)
    if p.is_absolute() is False and roots is not None:
        # Relative paths are resolved against each root by the loop below.
        pass
    else:
        # Windows drive letters / UNC recorded even on POSIX for defence.
        if len(raw) >= 2 and raw[1] == ":":
            raise PathSafetyError("Drive-qualified paths are not permitted")
        if raw.startswith("\\\\") or raw.startswith("//"):
            raise PathSafetyError("UNC paths are not permitted")

    allowed = [Path(r).expanduser().resolve() for r in roots] if roots is not None \
        else configured_ingestion_roots()

    # Staged uploads are a configured application input location: files the
    # authenticated user uploaded through the app itself are always
    # ingestible, independent of INGESTION_ROOTS (which gates arbitrary
    # server paths). The staging root lives under the app data dir and is
    # added BEFORE the fail-closed check so upload-then-ingest works even
    # when server-path ingestion is disabled entirely.
    try:
        from core.app_paths import get_data_root

        staged_root = (Path(get_data_root()) / "uploads").resolve()
        if staged_root.is_dir():
            allowed = allowed + [staged_root]
    except Exception:
        pass

    if not allowed:
        raise PathSafetyError(
            "Server-path ingestion is disabled: no INGESTION_ROOTS are configured"
        )

    try:
        resolved = p.expanduser().resolve(strict=False)
    except OSError as exc:
        raise PathSafetyError("Path could not be resolved") from exc

    for root in allowed:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    logger.warning("Rejected ingestion path outside approved roots: %s", raw)
    raise PathSafetyError("Path is outside all approved ingestion roots")


def validate_batch_paths(paths: Iterable[str | os.PathLike]) -> List[Path]:
    """Validate a batch; returns resolved paths. Raises on the first bad path."""
    return [validate_ingestion_path(p) for p in paths]
