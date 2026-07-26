"""Database engine, session factory, and the declarative base.

Everything is driven by the single `DATABASE_URL` setting, so moving from
SQLite to PostgreSQL or MySQL is a configuration change rather than a code
change:

    sqlite:///./stock_research.db
    postgresql+psycopg://user:password@localhost:5432/stockresearch
    mysql+pymysql://user:password@localhost:3306/stockresearch

The only engine-specific code is the SQLite `check_same_thread` argument, which
is applied conditionally below.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def _engine_kwargs() -> dict[str, Any]:
    """Engine options, including the SQLite-only threading argument."""
    kwargs: dict[str, Any] = {
        # Verify a pooled connection is alive before handing it out. Matters for
        # server-based databases whose connections can be dropped while idle.
        "pool_pre_ping": True,
        "future": True,
    }
    if settings.is_sqlite:
        # SQLite defaults to rejecting use of a connection from a thread other
        # than the one that created it. FastAPI runs sync endpoints in a thread
        # pool, so that default has to be relaxed.
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed.

    Usage:
        @router.get("/things")
        def list_things(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables.

    Models are imported here rather than at module scope so that importing
    `app.database` does not pull in the whole model package, and so the import
    is unambiguously for its registration side effect.
    """
    from app import models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    logger.info("Database ready at %s", _safe_database_url())


def _safe_database_url() -> str:
    """The database URL with any password removed, safe for logs."""
    url = settings.database_url
    if "@" not in url or "://" not in url:
        return url
    scheme, _, remainder = url.partition("://")
    credentials, _, host = remainder.rpartition("@")
    if ":" in credentials:
        user, _, _ = credentials.partition(":")
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://{credentials}@{host}"
