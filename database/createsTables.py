"""Deprecated module - retained only to fail loudly if still referenced.

The original ``createsTables.py`` executed DDL at import time against a
hardcoded ``postgres / <redacted credential>`` localhost database.  That violated:

* SEC-07  (hardcoded credentials)
* ARCH-03 (import-time side effects: DDL on import)
* DB-01   (competing schema creation paths)

The single authoritative schema bootstrap is now::

    from database.bootstrap import bootstrap_database
    from settings.config import get_db_config
    report = bootstrap_database(get_db_config())

or via CLI: ``python -m database.bootstrap`` / ``scripts/initialize_db.py``.

If your code imports names from this module, update it to use the bootstrap
or the repositories.  Importing this module raises ImportError so the failure
is visible in development and tests rather than silently corrupting installs.
"""

REPLACED_BY = "database.bootstrap"  # documented replacement


def __getattr__(name):
    raise ImportError(
        "database.createsTables was removed. Schema creation is handled by "
        "database.bootstrap.bootstrap_database (versioned migrations). "
        f"Attempted to access removed symbol: {name!r}"
    )
