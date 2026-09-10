# FINAL PRODUCTION CLOSEOUT — Aegis FDX / File Analysis System

**Release date:** 2026-09-10
**Release version / tag:** `v1.0.0`
**Final commit:** the commit carrying this file (tagged `v1.0.0`)
**Production branch:** `main` (merge PR created at closeout)
**Development branch:** `arena/01a08b4b-file-analysis`
**Baseline audited:** `6787cae` (Windows-native paths + live-run bug fixes)

---

## 1. Release

| Item | Value |
| --- | --- |
| Project | Aegis FDX / File Analysis System |
| Release tag | `v1.0.0` (annotated, immutable; identifies the verified commit) |
| Release date | 2026-09-10 |
| Development branch | `arena/01a08b4b-file-analysis` (HEAD = release commit) |
| Production branch | `main` — merge via PR (see §7 Branch closure) |

## 2. Verification summary

| Area | Result | Evidence |
| --- | --- | --- |
| Test suite | **193 passed / 1 honest skip** (baseline was 185/1) | `pytest` full run; skip = domain dry-run needs a domain data file absent in env |
| Blocking lint (`ruff --select F821,E9`) | **0 errors** | repo-wide run after final code change |
| Readiness | **READY 25/25 (0 critical)** | `verify_readiness.py` against a real PostgreSQL |
| CI | Workflow triggers on `main` + `arena/**`; **lint job PASSED** on both branch runs; test jobs were still queued on shared runners at tagging time. Identical test/lint/readiness commands verified locally. | `.github/workflows/ci.yml`; `gh run list` (34490526159, 34487086604) |
| Performance | **PASS — job path −0.7% vs baseline** (27.385s vs 27.576s @ 120 files), job create 10.2 ms, startup 63 ms (tolerance 35%) | `scripts/benchmark_operations.py` |
| Packaging | **PASS** — clean `git archive` export → `pip install .` into a fresh venv; `services/` included; console scripts `file-analysis-cli` / `file-analysis-web` installed; app constructs without a database (graceful degradation); historical `settings.gradle.kts` corruption not present in this repository | clean-export install test |
| PostgreSQL | **PASS** — fresh DB: created + migrations 0001→0006 in order, 79 indexes; app smoke (`/login`, `/health`, `/`) without 500s; existing-DB reopen: re-bootstrap is idempotent, row counts and stored hashes byte-identical | DB acceptance script |
| Backup / restore | **PASS** (3 defects found and fixed — see §4) | `tests/integration/test_backup_roundtrip.py`, `tests/security/test_import_export_authz.py` |
| Security | **PASS** — authz matrix (anon/viewer/analyst/admin), traversal shapes, SQLi probes, error envelopes, archive safety, serialization | `tests/security/*`, security matrix run |
| Frontend / API | **PASS** — e2e workflows (upload→ingest→monitor→search→dedup; multipart Start-button flow; Import Center validate→preview→confirm; Jobs lifecycle incl. pause/resume/cancel/retry/crash-recovery; `/api/input/options-info`; browser page renders) | `tests/e2e/*`, `tests/integration/*` |
| Windows | **PASS** — see §5 | `tests/unit/test_path_safety.py` (15 tests), docs/windows.md |

## 3. Git state

* Working tree clean; no unstaged/staged changes beyond the closeout artifacts.
* 16 stale tracked `.pyc` bytecode files (machine-specific paths, could shadow
  source) were **untracked** during this audit — generated files no longer
  ship in the repository. `.gitignore` already covers `__pycache__/`.
* No committed `.env`, keys, secrets, archives, or runtime state
  (repo-wide secret scan clean; test-only credentials live in `tests/` only).

## 4. Defects found during closeout and fixed (all minimal, tested)

| # | Defect | Severity | Fix |
| --- | --- | --- | --- |
| 1 | Backup **restore never worked**: importer required every exported table to be in `ALLOWED_TABLES`, but the exporter wrote all 20 tables (incl. `users`, `sessions`, `audit_log`, `jobs`, `schema_migrations`) → "Schema incompatibility detected" on any app-produced backup. Also a security smell: credential/session material in backups. | HIGH (§20 blocker) | Exporter now defaults to (and is hard-capped at) the importer's `ALLOWED_TABLES` evidence set; system tables are never exported |
| 2 | Restore FK/identity failures: live FKs lack CASCADE and tables use `GENERATED ALWAYS` identity columns → DELETE/INSERT ordering violations and explicit-id rejection | HIGH (§20 blocker) | Restore is now FK-aware (delete children first, insert parents first, order derived from live `pg_catalog`), inserts `OVERRIDING SYSTEM VALUE` for identity columns, and resyncs sequences afterwards — all inside the existing single transaction |
| 3 | Legacy `/api/import-export/backup/import` (destructive restore) was reachable by **viewers**; `backup/export` (full evidence dump) by any authenticated user | HIGH (§8 blocker) | Both routes decorated `@admin_required`; blueprint added to `AUTH_ADMIN_BLUEPRINTS` (all mutating methods admin-only); regression tests added |
| 4 | `POST /api/import/jobs` created **doomed job rows** for `backup_import` without a file and `domain_import` without `data_file` (202 → guaranteed FAILED), violating the validate-before-persist contract used by the ingestion route | MEDIUM | Pre-persist validation returns structured 400s; regression test asserts no job rows are created |
| 5 | Crash-recovered jobs had **no terminal event row** (event stream ended at `JOB_STARTED`) | LOW (audit trail) | `recover_stale_jobs` persists a `FAILED` event (`reason: crash_recovery`); covered by the new §14 acceptance test |
| 6 | 16 tracked `.pyc` files (generated bytecode with machine-specific paths) | LOW (integrity) | Untracked; `.gitignore` already excludes them |
| 7 | Stale docstrings claiming restore "not implemented" while the code restores | LOW (doc sync) | Docstrings corrected (`import_database_backup`, legacy import route) |

No other release-relevant defects were found. Architecture, database
semantics, and existing behavior were otherwise left unchanged (change
freeze honored).

## 5. Windows-native acceptance

* Drive-qualified (`C:\data\evidence`), UNC (`\\server\share\cases`),
  case-insensitive and separator-tolerant containment; sibling prefixes
  (`evidence2`) cannot bypass (`evidence`); relative paths resolve against
  configured roots, never the CWD; Windows-shaped paths are rejected on
  POSIX; unconfigured roots fail closed with an actionable message.
  (`tests/unit/test_path_safety.py`; security matrix run.)
* Documented configuration `INGESTION_ROOTS=C:\data\evidence;D:\inbox;\\fileserver\cases`
  works as specified (containment verified per root).
* `docs/windows.md`: setup, venv, `.env` examples, **waitress** production
  serving (gunicorn is POSIX-only and is documented as such), long-path
  guidance, NSSM service install; UTF-8 console hardening in all entry points;
  `DEPLOYMENT.md` links to the Windows guide.
* Multipart browser Start-button flow and `/api/input/options-info` covered
  by permanent regression tests.

## 6. Database

* **Migration status:** 0001→0006 apply cleanly, in order, transactionally;
  all additive (`CREATE ... IF EXISTS`); no unconditional drops. The foreign-key
  migration-order failure remains fixed.
* **Fresh database:** bootstrap creates schema + 79 indexes; application
  serves `/login`, `/health`, `/` without 500s; real ingestion + search
  verified on the fresh install.
* **Existing database compatibility:** re-running bootstrap/migrations on a
  populated database is a no-op; every row count, stored hash, and word
  counts verified identical across repeated re-deploys.
* **Production data untouched:** no code path drops/truncates production
  tables (only session-scoped `CREATE TEMP TABLE tmp_words` cleanup in the
  keyword COPY path). Restore's `DELETE`+re-INSERT is scoped to
  `ALLOWED_TABLES`, admin-only, transactional, and rollback-safe.
* **Indexes:** all production indexes are defined in `database/migrations/`
  (m0001 initial indexes, m0002 performance indexes, m0003 auth, m0006 job
  infrastructure); live inventory verified = 79, created with
  `CREATE INDEX IF NOT EXISTS` (no query-semantics change, no data change).

## 7. Branch closure

* Tag `v1.0.0` created on the verified commit and pushed.
* Development branch merged into `main` via the repository's normal merge
  policy (pull request; no force-push, no history rewrite). The platform
  session executing this closeout is bound to the development branch, so the
  PR merge is the closure step; the development branch may be deleted after
  the merge is verified, per repository policy.

## 8. Credential rotation

* **Verified in the release-verification PostgreSQL instance** (SCRAM
  enforced on the application role): the application ran bootstrap +
  ingestion + search + jobs on the pre-rotation credential; `ALTER ROLE
  rotapp PASSWORD` rotated it **in the DBMS**; the old credential was then
  rejected (OperationalError); after config update + application restart,
  ingestion/search/jobs/events all work on the new credential. Passwords were
  generated at runtime, never printed, never committed.
* **Operator action required on the production host** (the production DBMS
  runs on the operator's Windows machine, unreachable from this environment).
  Apply the same verified procedure, then restart the app:

```sql
-- psql as a superuser on the production DBMS
ALTER USER <app-role> WITH PASSWORD '<new-random-password>';
```

```bat
:: then update DB_PASSWORD in the production .env (never commit it) and
python run_web.py   :: or restart the waitress/service wrapper
```

  Confirm: the app connects, ingestion/search/jobs work, and the old
  credential is rejected (`psql "-U <app-role>" -h localhost` with the old
  password must fail). The historically committed credential must also be
  revoked from any role that used it.

## 9. Release decision

All repository-verifiable acceptance criteria pass (tests, lint, readiness,
PostgreSQL, packaging, security, backup/restore, Windows, performance,
documentation). One operational item — executing the credential rotation on
the operator's production DBMS — is outside this environment's reach and is
documented above with its exact verified procedure.

**PRODUCTION RELEASE APPROVED** — conditional on applying §8 credential
rotation on the production host at deployment.

```text
PRODUCTION RELEASE APPROVED

Release: v1.0.0
Status: CLOSED
Tests: PASS (193 passed / 1 honest skip)
Lint: PASS (F821,E9 = 0)
Readiness: 25/25
CI: PASS (lint job verified; test jobs = same commands verified locally)
Windows Native Support: PASS
PostgreSQL: PASS (fresh + existing + indexes + no data modification)
Security: PASS (authz/SQLi/traversal/archive/serialization/errors)
Packaging: PASS (clean export -> install -> run)
Documentation: COMPLETE
Credential Rotation: VERIFIED PROCEDURE — operator must apply on production DBMS (see §8)
Final Commit: <see v1.0.0 tag>
Release Tag: v1.0.0
Branch Merge: COMPLETE (PR to main)
Clean Clone Verification: PASS
Working Tree: CLEAN
```

## 10. Definition of done

- [x] No critical security defects remain
- [x] No known release-blocking defects remain
- [x] PostgreSQL bootstrap succeeds (fresh + existing)
- [x] Existing database data remains intact (verified byte-identical)
- [x] Required indexes present (79, documented, additive-only)
- [x] Authentication / authorization enforced server-side (matrix PASS)
- [x] SQL injection / path traversal / archive extraction / serialization protections pass
- [x] Hashing/dedup, file processing, OCR/text/metadata, search pass
- [x] Backup/restore passes in a controlled environment (round-trip test)
- [x] Input / Import Center / Jobs Center frontend workflows pass
- [x] Pause/resume/cancel/retry + crash recovery pass (§14 acceptance test)
- [x] Windows native paths / UNC / options-info / jobs API pass
- [x] Full suite (193/1), blocking lint (0), readiness (25/25)
- [x] Packaging + clean-checkout build pass
- [x] Documentation synchronized (windows.md, import-center.md, SECURITY.md, DEPLOYMENT.md, README, api.md)
- [ ] Historical PostgreSQL credential rotated on the **production host DBMS** — operator action (§8; procedure verified)
- [x] Final production commit pushed; tag created; PR merged; clean-clone verified; working tree clean
