from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

SCHEMA_VERSION = 2


def _table_has_column(conn: Connection, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _stored_schema_version(conn: Connection) -> int | None:
    if not _table_has_column(conn, "schema_meta", "version"):
        return None
    row = conn.execute(text("SELECT version FROM schema_meta ORDER BY version DESC LIMIT 1")).fetchone()
    if row is None:
        return None
    return int(row[0])


def _migrate_v1_to_v2(conn: Connection) -> None:
    if not _table_has_column(conn, "run_summaries", "pricing_disclosure"):
        conn.execute(text("ALTER TABLE run_summaries ADD COLUMN pricing_disclosure TEXT NOT NULL DEFAULT 'live'"))
    if not _table_has_column(conn, "run_summaries", "scores_mock"):
        conn.execute(text("ALTER TABLE run_summaries ADD COLUMN scores_mock TEXT NOT NULL DEFAULT 'false'"))
    conn.execute(text("DELETE FROM schema_meta"))
    conn.execute(text("INSERT INTO schema_meta (version) VALUES (2)"))


def migrate_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        stored = _stored_schema_version(conn)
        if stored is None:
            conn.execute(text("INSERT INTO schema_meta (version) VALUES (:v)"), {"v": SCHEMA_VERSION})
            return
        if stored == SCHEMA_VERSION:
            return
        if stored == 1 and SCHEMA_VERSION == 2:
            _migrate_v1_to_v2(conn)
            return
        raise RuntimeError(f"unsupported database schema version {stored}; expected {SCHEMA_VERSION}")
