from __future__ import annotations

from sqlmodel import Field, SQLModel


class SchemaMeta(SQLModel, table=True):
    __tablename__ = "schema_meta"
    version: int = Field(primary_key=True)


class RunRow(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(primary_key=True)
    record_version: int
    record_json: str


class RunSummaryRow(SQLModel, table=True):
    __tablename__ = "run_summaries"
    run_id: str = Field(primary_key=True, foreign_key="runs.id")
    created_at: str
    prompt_preview: str
    status: str
    total_known_cost_usd: str
    cost_flags: str
