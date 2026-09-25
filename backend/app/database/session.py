"""SQLite engine and session factory.

SQLite is a file, not a server, so a few pragmas matter once more than one
thread touches it (the scheduler writes on its own thread; API requests read
on the thread pool):

* ``WAL`` journal mode lets readers and a writer work at the same time instead
  of blocking each other.
* ``busy_timeout`` makes a request that does collide wait briefly and retry
  instead of raising "database is locked".
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database.orm import Base

logger = logging.getLogger(__name__)


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_session_factory(db_path: Path) -> sessionmaker[Session]:
    """Create the SQLite engine at ``db_path``, ensure tables exist, and return a session factory.

    Creates parent directories if needed. Safe to call more than once against
    the same file (``create_all`` only creates what's missing).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True
    )
    _configure_sqlite(engine)
    Base.metadata.create_all(engine)
    logger.info("database_ready", extra={"path": str(db_path)})
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
