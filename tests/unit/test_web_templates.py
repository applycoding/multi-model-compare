from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mmc.config.loader import load_app_config
from mmc.core.results import AnswerResult, Cost, CostTotal, Timing
from mmc.records import RunRecord
from mmc.settings import Settings
from mmc.web.app import create_app


@pytest.fixture
def templates(tmp_db, monkeypatch):
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    app = create_app(Settings.from_env())
    with TestClient(app, base_url="http://127.0.0.1"):
        yield app.state.templates


def test_answers_table_answers_cost_ignores_total_estimated_flag(templates) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    answer = AnswerResult(
        model=spec,
        status="ok",
        text="hello",
        timing=Timing(ttft_ms=12.0, total_ms=40.0),
        cost=Cost(status="known", total_usd=Decimal("0.002")),
    )
    record = RunRecord(
        id="run-template",
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
        profile="mock",
        app_version="0.1.0",
        prompt="template test",
        status="completed",
        seed=1,
        vendors_contacted=["mock"],
        judge_settings=config.judge,
        rubric=config.rubric,
        pricing_version=config.pricing.version,
        pricing_entries_used=[],
        answers=[answer],
        judge=None,
        total=CostTotal(subtotal_usd=Decimal("0.05"), estimated=True, unknown_count=0),
    )
    html = templates.env.get_template("_answers_table.html").render(record=record)
    assert re.search(r"Answers cost: \$[\d.]+ est\.", html) is None
    assert "Total: $0.05 est." in html


def test_answers_table_shows_mock_pricing_label(templates) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    answer = AnswerResult(
        model=spec,
        status="ok",
        text="hello",
        cost=Cost(status="known", total_usd=Decimal("0")),
    )
    record = RunRecord(
        id="run-mock-label",
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
        profile="mock",
        app_version="0.1.0",
        prompt="x",
        status="completed",
        seed=1,
        vendors_contacted=["mock"],
        judge_settings=config.judge,
        rubric=config.rubric,
        pricing_version=config.pricing.version,
        pricing_entries_used=[],
        answers=[answer],
        judge=None,
        total=CostTotal(subtotal_usd=Decimal(0), estimated=False, unknown_count=0),
        pricing_disclosure="example_pricing_mock",
    )
    html = templates.env.get_template("_answers_table.html").render(record=record)
    assert "example pricing (mock)" in html
    assert "Answers cost: $0" in html
