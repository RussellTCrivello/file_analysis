"""API-01: Shared Flask-Limiter instance.

Created here (not in the app factory) so blueprints can decorate routes with
``@limiter.limit`` at import time without circular imports; the app factory
calls ``limiter.init_app(app)``. Default limits apply to every route; stricter
per-route limits are declared on login, search, import/export and admin
mutations. In multi-process deployments set RATELIMIT_STORAGE_URI (e.g.
redis://...) so counters are shared.
"""
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    default_limits=["600 per hour", "60 per minute"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
