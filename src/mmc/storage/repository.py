from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from mmc.records import RunRecord, RunSummary


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class RunRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, record: RunRecord) -> None:
        from mmc.storage.tables import RunRow, RunSummaryRow

        flags: list[str] = []
        if record.total.estimated:
            flags.append("estimated")
        if record.total.unknown_count:
            flags.append("unknown")
        cost_flags = ",".join(flags)
        with Session(self._engine) as session:
            session.add(
                RunRow(
                    id=record.id,
                    record_version=record.record_version,
                    record_json=record.model_dump_json(),
                )
            )
            session.add(
                RunSummaryRow(
                    run_id=record.id,
                    created_at=record.created_at.isoformat(),
                    prompt_preview=record.prompt[:200],
                    status=record.status,
                    total_known_cost_usd=str(record.total.subtotal_usd),
                    cost_flags=cost_flags,
                )
            )
            session.commit()

    def get(self, run_id: str) -> RunRecord | None:
        from mmc.storage.tables import RunRow

        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            return RunRecord.model_validate_json(row.record_json)

    def list(self, *, limit: int = 50, offset: int = 0, q: str | None = None) -> list[RunSummary]:
        from mmc.storage.tables import RunSummaryRow

        with Session(self._engine) as session:
            stmt = select(RunSummaryRow)
            if q:
                esc = _escape_like(q)
                stmt = stmt.where(col(RunSummaryRow.prompt_preview).ilike(f"%{esc}%", escape="\\"))
            stmt = stmt.order_by(col(RunSummaryRow.created_at).desc(), col(RunSummaryRow.run_id).desc())
            stmt = stmt.offset(offset).limit(limit)
            rows = session.exec(stmt).all()
            return [
                RunSummary(
                    id=r.run_id,
                    created_at=datetime.fromisoformat(r.created_at),
                    prompt_preview=r.prompt_preview,
                    status=r.status,
                    total_known_cost_usd=Decimal(r.total_known_cost_usd),
                    cost_flags=[f for f in r.cost_flags.split(",") if f],
                )
                for r in rows
            ]

    def count(self, q: str | None = None) -> int:
        from mmc.storage.tables import RunSummaryRow

        with Session(self._engine) as session:
            stmt = select(func.count()).select_from(RunSummaryRow)
            if q:
                esc = _escape_like(q)
                stmt = stmt.where(col(RunSummaryRow.prompt_preview).ilike(f"%{esc}%", escape="\\"))
            return int(session.exec(stmt).one())

    def iter_all(self) -> Iterator[RunRecord]:
        from mmc.storage.tables import RunRow

        with Session(self._engine) as session:
            rows = session.exec(select(RunRow).order_by(RunRow.id)).all()
            for row in rows:
                yield RunRecord.model_validate_json(row.record_json)

    def delete(self, run_id: str) -> bool:
        from mmc.storage.tables import RunRow

        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def clear(self) -> int:
        from mmc.storage.tables import RunRow

        with Session(self._engine) as session:
            rows = session.exec(select(RunRow)).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
            return count
