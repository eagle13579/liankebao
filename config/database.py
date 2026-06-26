"""
Dual database configuration — SQLite (development) / PostgreSQL (production) auto-switch.

Usage:
    from config.database import get_database_url, get_engine

    engine = get_engine()
    # engine is a SQLAlchemy Engine pointing to the correct backend.

Environment variable:
    PG_URL   PostgreSQL connection URI (e.g. postgresql://user:pass@host:5432/dbname)
             If not set, the config falls back to SQLite (suitable for local dev / CI).
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
# Default SQLite database lives next to this config file:  config/../data/
# Override with SQLITE_PATH if you want a custom location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_DIR = PROJECT_ROOT / "data"
DEFAULT_SQLITE_PATH = DEFAULT_SQLITE_DIR / "chainkefull.db"


def get_database_url() -> str:
    """
    Return the active database URL.

    Priority:
        1. PG_URL environment variable  → PostgreSQL (production / staging)
        2. SQLITE_PATH env var           → Custom SQLite location
        3. Default                        → data/chainkefull.db in project root

    Returns
    -------
    str
        SQLAlchemy-compatible database URL.
    """
    pg_url = os.environ.get("PG_URL", "").strip()

    if pg_url:
        # Ensure the scheme is understood by SQLAlchemy if the user only
        # supplied a bare connection string without "postgresql://"
        if not pg_url.startswith("postgresql"):
            pg_url = "postgresql://" + pg_url
        return pg_url

    # ── Fallback: SQLite ──────────────────────────────────────────────
    sqlite_path = os.environ.get("SQLITE_PATH", "").strip()
    if sqlite_path:
        sqlite_file = Path(sqlite_path)
    else:
        sqlite_file = DEFAULT_SQLITE_PATH

    sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    # Use the URI form (with check_same_thread=False) so that async / web
    # frameworks won't complain about reusing the same engine across threads.
    return f"sqlite:///{sqlite_file.resolve()}?check_same_thread=False"


def is_postgres() -> bool:
    """Return True when PG_URL is set (i.e. the active backend is PostgreSQL)."""
    return bool(os.environ.get("PG_URL", "").strip())


def is_dev() -> bool:
    """Return True when no PG_URL is set (SQLite is used, i.e. local dev)."""
    return not is_postgres()


# ── SQLAlchemy convenience helpers ────────────────────────────────────────
# These are safe to call even if SQLAlchemy is not installed — they are only
# evaluated when actually invoked.

def create_engine(**kwargs):
    """
    Build a SQLAlchemy Engine from the resolved database URL.

    Extra keyword arguments are forwarded to sqlalchemy.create_engine().
    """
    from sqlalchemy import create_engine as _sa_create_engine

    url = get_database_url()
    engine_kwargs = {}

    if is_postgres():
        # PostgreSQL sane defaults
        engine_kwargs.setdefault("pool_size", 10)
        engine_kwargs.setdefault("max_overflow", 20)
        engine_kwargs.setdefault("pool_pre_ping", True)
        # Allow the caller to override these via **kwargs
        engine_kwargs.update(kwargs)
        return _sa_create_engine(url, **engine_kwargs)
    else:
        # SQLite: single-writer, so pool_size=1 is safest
        engine_kwargs.setdefault("pool_size", 1)
        engine_kwargs.setdefault("max_overflow", 0)
        engine_kwargs.update(kwargs)
        return _sa_create_engine(url, **engine_kwargs)


def get_engine(**kwargs):
    """Alias for create_engine()."""
    return create_engine(**kwargs)


# ── Session helper ─────────────────────────────────────────────────────────

def create_session(**engine_kwargs):
    """
    Return a new sqlalchemy.orm.sessionmaker bound to the active database.
    """
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(**engine_kwargs)
    return sessionmaker(bind=engine)


# ── Quick self-test when run directly ──────────────────────────────────────

if __name__ == "__main__":
    print(f"PG_URL  set?  {'yes' if is_postgres() else 'no'}")
    print(f"Backend       {'PostgreSQL' if is_postgres() else 'SQLite'}")
    print(f"Database URL  {get_database_url()}")
