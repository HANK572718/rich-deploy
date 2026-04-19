"""SQLAlchemy engine and session factory for rich_deploy."""

import sys
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import Session

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .models import Base

_CONFIG_PATH = Path(__file__).parent.parent.parent / "rich_deploy.toml"
_DEFAULT_URL = "sqlite:///db/registry.db"

_engine = None


def _load_db_url() -> str:
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open("rb") as f:
            config = tomllib.load(f)
        return config.get("database", {}).get("url", _DEFAULT_URL)
    return _DEFAULT_URL


def get_engine():
    """Return the shared SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        url = _load_db_url()
        _engine = _create_engine(url, echo=False)
    return _engine


def init_db() -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(get_engine())


@contextmanager
def get_session():
    """Yield a SQLAlchemy Session and commit/rollback automatically."""
    session = Session(get_engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
