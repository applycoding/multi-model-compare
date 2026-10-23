from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mmc.honesty import EXAMPLE_PRICING_MOCK_LABEL
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


def mock_pricing_label(record: RunRecord) -> str | None:
    if record.pricing_disclosure == "example_pricing_mock":
        return EXAMPLE_PRICING_MOCK_LABEL
    return None


def format_answer_cost_usd(record: RunRecord, total_usd: Decimal | None) -> str:
    if record.pricing_disclosure == "example_pricing_mock":
        return "$0"
    if total_usd is None:
        return "n/a"
    return f"${total_usd}"


def judge_cost_subtotal(record: RunRecord) -> Decimal:
    total = Decimal(0)
    if record.judge is None:
        return total
    for att in record.judge.attempts:
        if att.cost and att.cost.total_usd is not None:
            total += att.cost.total_usd
    return total
