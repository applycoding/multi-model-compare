from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from mmc.config.loader import load_app_config
from mmc.core.results import CostTotal
from mmc.display import answers_cost_estimated, format_answer_cost_usd
from mmc.records import RunRecord


def test_answers_cost_estimated_ignores_run_total_flag() -> None:
    estimated_answer = SimpleNamespace(cost=SimpleNamespace(status="estimated"))
    known_answer = SimpleNamespace(cost=SimpleNamespace(status="known"))
    record = SimpleNamespace(
        answers=[estimated_answer, known_answer],
        total=SimpleNamespace(estimated=True),
    )
    assert answers_cost_estimated(record) is True

    judge_only_estimated = SimpleNamespace(
        answers=[known_answer],
        total=SimpleNamespace(estimated=True),
    )
    assert answers_cost_estimated(judge_only_estimated) is False


def test_format_answer_cost_usd_mock_is_exact_dollar_zero() -> None:
    config = load_app_config(None)
    record = RunRecord(
        id="fmt",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        profile="mock",
        app_version="0",
        prompt="p",
        status="completed",
        seed=1,
        vendors_contacted=[],
        judge_settings=config.judge,
        rubric=config.rubric,
        pricing_version=config.pricing.version,
        pricing_entries_used=[],
        answers=[],
        judge=None,
        total=CostTotal(subtotal_usd=Decimal(0), estimated=False, unknown_count=0),
        pricing_disclosure="example_pricing_mock",
    )
    assert format_answer_cost_usd(record, Decimal("0.000000")) == "$0"
    assert format_answer_cost_usd(record, Decimal("0")) == "$0"
    live = record.model_copy(update={"pricing_disclosure": "live"})
    assert format_answer_cost_usd(live, Decimal("0.001")) == "$0.001"
