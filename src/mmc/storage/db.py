from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from mmc.storage import tables as _tables  # noqa: F401 - register SQLModel metadata
from mmc.storage.migrate import SCHEMA_VERSION, migrate_schema

__all__ = ["SCHEMA_VERSION", "init_db", "make_engine"]


def make_engine(db_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not db_path.exists():
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
    engine = make_engine(db_path)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    migrate_schema(engine)
    return engine
