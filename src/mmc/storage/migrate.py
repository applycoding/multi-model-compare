from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

SCHEMA_VERSION = 3


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


def _sync_honesty_summaries(conn: Connection) -> None:
    if not _table_has_column(conn, "run_summaries", "pricing_disclosure"):
        return
    from mmc.honesty import honesty_summary_from_record_json

    rows = conn.execute(text("SELECT id, record_json FROM runs")).fetchall()
    for run_id, record_json in rows:
        disclosure, scores_mock, subtotal = honesty_summary_from_record_json(record_json)
        conn.execute(
            text(
                "UPDATE run_summaries SET pricing_disclosure = :d, scores_mock = :s, "
                "total_known_cost_usd = :t WHERE run_id = :id"
            ),
            {
                "d": disclosure,
                "s": "true" if scores_mock else "false",
                "t": str(subtotal),
                "id": run_id,
            },
        )


def _migrate_v1_to_v2(conn: Connection) -> None:
    if not _table_has_column(conn, "run_summaries", "pricing_disclosure"):
        conn.execute(text("ALTER TABLE run_summaries ADD COLUMN pricing_disclosure TEXT NOT NULL DEFAULT 'live'"))
    if not _table_has_column(conn, "run_summaries", "scores_mock"):
        conn.execute(text("ALTER TABLE run_summaries ADD COLUMN scores_mock TEXT NOT NULL DEFAULT 'false'"))
    conn.execute(text("DELETE FROM schema_meta"))
    conn.execute(text("INSERT INTO schema_meta (version) VALUES (2)"))


def _migrate_v2_to_v3(conn: Connection) -> None:
    _sync_honesty_summaries(conn)
    conn.execute(text("DELETE FROM schema_meta"))
    conn.execute(text("INSERT INTO schema_meta (version) VALUES (3)"))


def migrate_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        stored = _stored_schema_version(conn)
        if stored is None:
            conn.execute(text("INSERT INTO schema_meta (version) VALUES (:v)"), {"v": SCHEMA_VERSION})
            return
        if stored == SCHEMA_VERSION:
            return
        if stored == 1:
            _migrate_v1_to_v2(conn)
            _migrate_v2_to_v3(conn)
            return
        if stored == 2 and SCHEMA_VERSION == 3:
            _migrate_v2_to_v3(conn)
            return
        raise RuntimeError(f"unsupported database schema version {stored}; expected {SCHEMA_VERSION}")
