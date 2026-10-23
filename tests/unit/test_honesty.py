from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mmc.config.loader import load_app_config
from mmc.core.request import RunRequest, resolve_request
from mmc.core.results import CostTotal
from mmc.core.tokens import TokenEstimator
from mmc.honesty import EXAMPLE_PRICING_MOCK_LABEL, apply_profile_honesty
from mmc.providers.registry import ProviderRegistry
from mmc.records import RunRecord
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.repository import RunRepository
from mmc.web.app import create_app


@pytest.mark.asyncio
async def test_mock_profile_zeros_costs_and_sets_disclosure(
    tmp_db, monkeypatch, stepping_clock, redactor, repo: RunRepository
) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    settings = Settings.from_env()
    config = load_app_config(None)
    registry = ProviderRegistry(config, settings)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, TokenEstimator("chars"))
    req = RunRequest(prompt="honesty cost test", seed=7)
    resolved = resolve_request(req, config, settings, redactor, registry)
    record = await service.run(resolved)
    await registry.aclose()

    assert record.pricing_disclosure == "example_pricing_mock"
    assert record.total.subtotal_usd == Decimal(0)
    for ans in record.answers:
        if ans.cost and ans.cost.total_usd is not None:
            assert ans.cost.total_usd == Decimal(0)
            assert EXAMPLE_PRICING_MOCK_LABEL in ans.cost.notes
    assert record.judge is not None
    assert record.judge.scores_mock is True


def test_api_mock_run_includes_honesty_fields(tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    app = create_app(Settings.from_env())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/csrf").json()["csrf_token"]
        resp = client.post(
            "/api/runs",
            json={"prompt": "api honesty", "seed": 3},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["pricing_disclosure"] == "example_pricing_mock"
        assert body["total"]["subtotal_usd"] == "0"
        assert body["judge"]["scores_mock"] is True


def test_apply_profile_honesty_leaves_live_disclosure() -> None:
    config = load_app_config(None)
    record = RunRecord(
        id="x",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        profile="live",
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
        total=CostTotal(subtotal_usd=Decimal("1"), estimated=False, unknown_count=0),
        pricing_disclosure="live",
    )
    out = apply_profile_honesty(record)
    assert out.pricing_disclosure == "live"
    assert out.total.subtotal_usd == Decimal("1")
