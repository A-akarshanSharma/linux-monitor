from pathlib import Path

from sqlalchemy import text

from app.database.session import create_session_factory


def test_creates_parent_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "monitor.db"

    create_session_factory(db_path)

    assert db_path.parent.is_dir()


def test_creates_the_database_file_on_first_write(tmp_path: Path) -> None:
    db_path = tmp_path / "monitor.db"
    factory = create_session_factory(db_path)

    with factory() as session:
        session.execute(text("SELECT 1"))

    assert db_path.exists()


def test_wal_journal_mode_is_enabled(tmp_path: Path) -> None:
    factory = create_session_factory(tmp_path / "monitor.db")

    with factory() as session:
        mode = session.execute(text("PRAGMA journal_mode")).scalar()

    assert mode == "wal"


def test_busy_timeout_is_set(tmp_path: Path) -> None:
    factory = create_session_factory(tmp_path / "monitor.db")

    with factory() as session:
        timeout_ms = session.execute(text("PRAGMA busy_timeout")).scalar()

    assert timeout_ms == 5000


def test_creating_the_factory_twice_against_the_same_file_does_not_raise(tmp_path: Path) -> None:
    db_path = tmp_path / "monitor.db"

    create_session_factory(db_path)
    create_session_factory(db_path)  # create_all must be idempotent


def test_tables_are_created(tmp_path: Path) -> None:
    factory = create_session_factory(tmp_path / "monitor.db")

    with factory() as session:
        tables = (
            session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            .scalars()
            .all()
        )

    assert "metric_samples" in tables
