"""Unit + security tests: ingestion path safety (SEC-06)."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.path_safety import (
    PathSafetyError,
    validate_ingestion_path,
    validate_batch_paths,
    configured_ingestion_roots,
)


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    r1 = tmp_path / "ingest1"
    r2 = tmp_path / "ingest2"
    r1.mkdir()
    r2.mkdir()
    monkeypatch.setenv("INGESTION_ROOTS", f"{r1};{r2}")
    return r1, r2


def test_roots_from_environment(roots):
    r1, r2 = roots
    assert configured_ingestion_roots() == [r1.resolve(), r2.resolve()]


def test_no_roots_configured_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("INGESTION_ROOTS", raising=False)
    with pytest.raises(PathSafetyError):
        validate_ingestion_path("/etc/passwd")


def test_path_inside_root_accepted(roots, tmp_path):
    r1, _ = roots
    f = r1 / "data.txt"
    f.write_text("x")
    assert validate_ingestion_path(f) == f.resolve()


def test_path_outside_roots_rejected(roots, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    with pytest.raises(PathSafetyError):
        validate_ingestion_path(outside)


def test_etc_passwd_rejected(roots):
    with pytest.raises(PathSafetyError):
        validate_ingestion_path("/etc/passwd")


def test_traversal_escaping_root_rejected(roots):
    r1, _ = roots
    with pytest.raises(PathSafetyError):
        validate_ingestion_path(str(r1 / ".." / ".." / "etc" / "passwd"))


def test_drive_qualified_rejected(roots):
    with pytest.raises(PathSafetyError):
        validate_ingestion_path("C:\\Windows\\evil.txt")


def test_unc_path_rejected(roots):
    with pytest.raises(PathSafetyError):
        validate_ingestion_path("\\\\server\\share\\x")


def test_nul_byte_rejected(roots):
    with pytest.raises(PathSafetyError):
        validate_ingestion_path("good\x00bad")


def test_batch_validation(roots, tmp_path):
    r1, _ = roots
    good = r1 / "a.txt"
    good.write_text("x")
    assert len(validate_batch_paths([good])) == 1
    with pytest.raises(PathSafetyError):
        validate_batch_paths([good, "/etc/passwd"])
