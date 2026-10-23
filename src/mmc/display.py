from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mmc.records import RunRecord


def format_ms_rounded(ms: float | None) -> str:
    if ms is None:
        return ""
    return str(int(round(ms)))


def format_local_datetime(dt: datetime) -> str:
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S %Z")


def answers_cost_subtotal(record: RunRecord) -> Decimal:
    total = Decimal(0)
    for ans in record.answers:
        if ans.cost and ans.cost.total_usd is not None:
            total += ans.cost.total_usd
    return total


def answers_cost_estimated(record: RunRecord) -> bool:
    return any(ans.cost and ans.cost.status == "estimated" for ans in record.answers)


def judge_cost_subtotal(record: RunRecord) -> Decimal:
    total = Decimal(0)
    if record.judge is None:
        return total
    for att in record.judge.attempts:
        if att.cost and att.cost.total_usd is not None:
            total += att.cost.total_usd
    return total
