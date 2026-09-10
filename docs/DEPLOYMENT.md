# Deployment Guide

## 1. Prerequisites

* Python 3.10+
* PostgreSQL 12+ (any standard install; no required extensions — `pg_trgm`
  was removed)
* A service account with a rotated, non-default password

## 2. Fresh install (verified by tests/e2e + verify_readiness.py)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env: DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD, FLASK_SECRET_KEY,
#            FLASK_ENV=production, APP_DATA_DIR (writable, outside the repo)

.venv/bin/python run_cli.py init-admin      # or set APP_ADMIN_USERNAME/APP_ADMIN_PASSWORD
.venv/bin/python verify_readiness.py        # must print READINESS: READY (exit 0)
```

`bootstrap_database` runs automatically on first app start (or explicitly via
the readiness check): it creates the database if missing and applies all
versioned migrations in order. No SQL scripts need manual execution; nothing
is created at import time; the application never requires the current working
directory to be the repo root (`APP_DATA_DIR` anchors all runtime state).

## 3. Environment variables

| Variable | Purpose |
|---|---|
| `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD` | database connection (override settings file at read time) |
| `FLASK_SECRET_KEY` | session signing key (required in production) |
| `FLASK_ENV=production`, `FLASK_DEBUG=0` | production mode; debug refused in production |
| `APP_DATA_DIR` | runtime data root (uploads, logs, settings store) |
| `INGESTION_ROOTS` | semicolon-separated allowlist of server dirs eligible for batch import; **empty = server-path import disabled** |
| `RATELIMIT_STORAGE_URI` | e.g. `redis://…` for multi-process rate limiting |

## 4. Running

```bash
# WSGI (recommended): gunicorn with multiple workers
.venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 "apps.web.app:create_app()"

# Development only
.venv/bin/python run_web.py
```

## 5. Operations checklist

* Backups: nightly `pg_dump -Fc`, restore drill quarterly (docs/DATABASE.md).
* Secrets: rotate the historically committed PostgreSQL credential; store
  secrets in the environment/secret manager, never in the repo.
* Logs: check `APP_DATA_DIR/logs/`; client errors carry correlation ids
  (`ERR-…`) that map to server-side detail.
* Upgrades: deploy → `bootstrap_database` applies pending migrations in
  order, each transactional → `verify_readiness.py` gates the release.
* Monitoring: `/health` endpoint; error dashboard is admin-only.
