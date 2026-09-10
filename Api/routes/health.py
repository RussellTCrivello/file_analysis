"""Health check endpoint (public, unauthenticated).

Provides a simple liveness/readiness probe for load balancers, monitoring,
and the installer's verification phase.

GET /health → 200 if the app can start, 503 if a critical dependency fails.

Uses a single shared psycopg2 connection (not a pool) for the DB probe —
this is a lightweight connectivity check, not a query workload.  The
connection is created lazily and reused across requests.
"""

from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)

_start_time = time.time()

# Shared health-check connection (lazily created, not a pool).
_health_conn = None


def _get_health_connection():
    """Return a reusable psycopg2 connection for health probes.

    Creates a lightweight single connection (not a pool) that is reused
    across health-check requests.  Reconnects automatically on failure.
    """
    global _health_conn
    if _health_conn is not None:
        try:
            if _health_conn.closed:
                _health_conn = None
            else:
                # Quick liveness probe
                cur = _health_conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                return _health_conn
        except Exception:
            try:
                _health_conn.close()
            except Exception:
                pass
            _health_conn = None

    # Create new connection
    try:
        import psycopg2
        from database import get_db_config
        cfg = get_db_config()
        _health_conn = psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 5432)),
            user=cfg.get("user", "postgres"),
            password=cfg.get("password", ""),
            dbname=cfg.get("database", "analysis"),
            connect_timeout=5,
        )
        return _health_conn
    except Exception:
        _health_conn = None
        raise


@health_bp.route("/health", methods=["GET"])
def health():
    """Liveness + lightweight readiness probe.

    Returns 200 with component status when the app is operational.
    Returns 503 when a critical component is down.
    """
    checks: dict = {}
    all_ok = True

    # Database connectivity — uses a shared lightweight connection,
    # NOT a new Database() pool per request.
    try:
        conn = _get_health_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        all_ok = False

    # Settings system
    try:
        from settings import get_settings

        settings = get_settings()
        _ = settings.version
        checks["settings"] = "ok"
    except Exception as exc:
        checks["settings"] = f"error: {exc.__class__.__name__}"
        all_ok = False

    uptime = int(time.time() - _start_time)
    status_code = 200 if all_ok else 503
    return jsonify({
        "status": "healthy" if all_ok else "degraded",
        "uptime_seconds": uptime,
        "checks": checks,
    }), status_code


def register_health_routes(app):
    """Register the health blueprint on the app."""
    app.register_blueprint(health_bp)
    logger.info("✅ Health check endpoint registered at /health")
