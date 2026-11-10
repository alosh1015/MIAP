from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal: sessionmaker[Session] | None = None


def _configure_engine(db_path: Path) -> Engine:
    global engine, SessionLocal

    db_path.parent.mkdir(parents=True, exist_ok=True)
    from sqlalchemy import create_engine

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine


def init_db(db_path: Path | None = None) -> Engine:
    from app.core import schema  # noqa: F401  (register models on Base.metadata)

    target = db_path or settings.database_path
    configured = _configure_engine(target)
    Base.metadata.create_all(configured)
    return configured


def get_session():
    if SessionLocal is None:
        raise RuntimeError("Database is not initialised; call init_db() first")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
