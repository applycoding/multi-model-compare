from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from mmc.storage.tables import SchemaMeta

SCHEMA_VERSION = 1


def make_engine(db_path: Path) -> Engine:
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


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
    with Session(engine) as session:
        existing = session.get(SchemaMeta, SCHEMA_VERSION)
        if existing is None:
            meta = session.get(SchemaMeta, 1)
            if meta is None:
                session.add(SchemaMeta(version=SCHEMA_VERSION))
                session.commit()
            else:
                if meta.version != SCHEMA_VERSION:
                    raise RuntimeError(f"schema mismatch: expected {SCHEMA_VERSION}")
    return engine
