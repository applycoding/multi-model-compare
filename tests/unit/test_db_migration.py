from __future__ import annotations

import csv
import io
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mmc.cli import main
from mmc.config.loader import load_app_config
from mmc.core.request import RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.export import to_csv, to_json
from mmc.providers.registry import ProviderRegistry
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.migrate import SCHEMA_VERSION
from mmc.storage.repository import RunRepository
from mmc.web.app import create_app


def _v1_schema_sql() -> str:
    return """
        CREATE TABLE schema_meta (version INTEGER NOT NULL PRIMARY KEY);
        CREATE TABLE runs (
            id TEXT NOT NULL PRIMARY KEY,
            record_version INTEGER NOT NULL,
            record_json TEXT NOT NULL
        );
        CREATE TABLE run_summaries (
            run_id TEXT NOT NULL PRIMARY KEY,
            created_at TEXT NOT NULL,
            prompt_preview TEXT NOT NULL,
            status TEXT NOT NULL,
            total_known_cost_usd TEXT NOT NULL,
            cost_flags TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        INSERT INTO schema_meta (version) VALUES (1);
    """


def _legacy_mock_record(config: object) -> dict[str, Any]:
    from mmc.config.schemas import AppConfig

    assert isinstance(config, AppConfig)
    gpt = config.model("mock:mock-gpt")
    judge_model = config.model("mock:mock-judge")
    return {
        "record_version": 1,
        "id": "legacy-mock-1",
        "created_at": "2026-10-23T12:00:00+00:00",
        "profile": "mock",
        "app_version": "0.1.0",
        "prompt": "legacy mock prompt",
        "status": "completed",
        "seed": 1,
        "vendors_contacted": ["mock"],
        "judge_settings": config.judge.model_dump(mode="json"),
        "rubric": config.rubric.model_dump(mode="json"),
        "pricing_version": config.pricing.version,
        "pricing_entries_used": [],
        "answers": [
            {
                "model": gpt.model_dump(mode="json"),
                "status": "ok",
                "text": "legacy answer",
                "partial": False,
                "truncated": False,
                "finish_reason": "stop",
                "provider_request_id": "mock-abc",
                "resolved_params": {},
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 60,
                    "reasoning_tokens": None,
                    "total_tokens": 70,
                    "raw": {"input_tokens": 10, "output_tokens": 60},
                    "input_source": "provider",
                    "output_source": "provider",
                    "estimator": None,
                },
                "timing": {"ttft_ms": 12.0, "total_ms": 40.0},
                "cost": {
                    "status": "known",
                    "input_usd": "0.000010",
                    "output_usd": "0.000114",
                    "total_usd": "0.000124",
                    "price": None,
                    "notes": [],
                },
                "error": None,
                "skip_reason": None,
            }
        ],
        "judge": {
            "status": "ok",
            "judge": judge_model.model_dump(mode="json"),
            "seed": 1,
            "label_map": {"A": "mock:mock-gpt"},
            "scores": {
                "mock:mock-gpt": {
                    "criteria": {
                        key: {
                            "criterion": key,
                            "score": 3,
                            "rationale": "legacy",
                        }
                        for key in ("correctness", "completeness", "clarity", "safety")
                    },
                    "overall": "3.0",
                    "self_judged": False,
                }
            },
            "excluded": {},
            "attempts": [],
            "resolved_params": {},
            "scores_mock": False,
        },
        "total": {"subtotal_usd": "0.001896", "estimated": False, "unknown_count": 0},
    }


def _legacy_live_record(config: object) -> dict[str, Any]:
    from mmc.config.schemas import AppConfig

    assert isinstance(config, AppConfig)
    gpt = config.model("openai:gpt-6.1-sol")
    return {
        "record_version": 1,
        "id": "legacy-live-1",
        "created_at": "2026-10-23T12:00:00+00:00",
        "profile": "live",
        "app_version": "0.1.0",
        "prompt": "legacy live prompt",
        "status": "completed",
        "seed": 2,
        "vendors_contacted": ["openai"],
        "judge_settings": config.judge.model_dump(mode="json"),
        "rubric": config.rubric.model_dump(mode="json"),
        "pricing_version": config.pricing.version,
        "pricing_entries_used": [],
        "answers": [
            {
                "model": gpt.model_dump(mode="json"),
                "status": "ok",
                "text": "live answer",
                "partial": False,
                "truncated": False,
                "finish_reason": None,
                "provider_request_id": None,
                "resolved_params": {},
                "usage": None,
                "timing": None,
                "cost": {
                    "status": "known",
                    "input_usd": "0.02",
                    "output_usd": "0.03",
                    "total_usd": "0.05",
                    "price": None,
                    "notes": [],
                },
                "error": None,
                "skip_reason": None,
            }
        ],
        "judge": None,
        "total": {"subtotal_usd": "0.05", "estimated": False, "unknown_count": 0},
    }


def _create_v1_database(db_path: Path, records: list[tuple[str, dict[str, Any], str]]) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_v1_schema_sql())
    for run_id, record, summary_total in records:
        conn.execute(
            "INSERT INTO runs (id, record_version, record_json) VALUES (?, ?, ?)",
            (run_id, 1, json.dumps(record)),
        )
        conn.execute(
            "INSERT INTO run_summaries "
            "(run_id, created_at, prompt_preview, status, total_known_cost_usd, cost_flags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                record["created_at"],
                record["prompt"][:200],
                record["status"],
                summary_total,
                "",
            ),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def legacy_v1_db(tmp_path: Path) -> Path:
    config = load_app_config(None)
    db_path = tmp_path / "legacy.sqlite"
    _create_v1_database(
        db_path,
        [
            ("legacy-mock-1", _legacy_mock_record(config), "0.001896"),
            ("legacy-live-1", _legacy_live_record(config), "0.05"),
        ],
    )
    return db_path


def test_init_db_twice_is_idempotent(legacy_v1_db: Path) -> None:
    init_db(legacy_v1_db)
    init_db(legacy_v1_db)
    repo = RunRepository(init_db(legacy_v1_db))
    mock_row = next(s for s in repo.list() if s.id == "legacy-mock-1")
    assert mock_row.pricing_disclosure == "example_pricing_mock"
    assert mock_row.total_known_cost_usd == Decimal(0)


def test_legacy_mock_honesty_on_list_get_api_ui_and_exports(legacy_v1_db: Path, monkeypatch) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(legacy_v1_db))
    engine = init_db(legacy_v1_db)
    assert SCHEMA_VERSION == 3

    repo = RunRepository(engine)
    mock_summary = next(s for s in repo.list() if s.id == "legacy-mock-1")
    assert mock_summary.pricing_disclosure == "example_pricing_mock"
    assert mock_summary.scores_mock is True
    assert mock_summary.total_known_cost_usd == Decimal(0)

    live_summary = next(s for s in repo.list() if s.id == "legacy-live-1")
    assert live_summary.pricing_disclosure == "live"
    assert live_summary.scores_mock is False
    assert live_summary.total_known_cost_usd == Decimal("0.05")

    from sqlmodel import Session

    from mmc.storage.tables import RunRow

    with Session(engine) as session:
        row = session.get(RunRow, "legacy-mock-1")
        assert row is not None
        stored = json.loads(row.record_json)
        assert stored["answers"][0]["cost"]["total_usd"] == "0.000124"

    record = repo.get("legacy-mock-1")
    assert record is not None
    assert record.pricing_disclosure == "example_pricing_mock"
    assert record.judge is not None
    assert record.judge.scores_mock is True
    assert record.answers[0].cost is not None
    assert record.answers[0].cost.total_usd == Decimal(0)
    assert record.total.subtotal_usd == Decimal(0)

    csv_text = to_csv([record])
    csv_rows = list(csv.reader(io.StringIO(csv_text)))
    header = csv_rows[0]
    data_row = csv_rows[1]
    assert "pricing_disclosure" in header
    assert data_row[header.index("pricing_disclosure")] == "example_pricing_mock"
    assert data_row[header.index("scores_mock")] == "true"
    assert data_row[header.index("cost_usd")] == "0"

    payload = json.loads(to_json([record], record.created_at))
    assert payload["runs"][0]["pricing_disclosure"] == "example_pricing_mock"
    assert payload["runs"][0]["judge"]["scores_mock"] is True

    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        api_list = client.get("/api/runs").json()
        mock_api = next(r for r in api_list if r["id"] == "legacy-mock-1")
        assert mock_api["pricing_disclosure"] == "example_pricing_mock"
        assert mock_api["scores_mock"] is True
        assert mock_api["total_known_cost_usd"] == "0"

        detail = client.get("/api/runs/legacy-mock-1").json()
        assert detail["answers"][0]["cost"]["total_usd"] == "0"

        page = client.get("/runs/legacy-mock-1")
        assert page.status_code == 200
        assert "example pricing (mock)" in page.text
        assert "mock scores (deterministic, not a real judge)" in page.text
        assert "$0.000124" not in page.text


def test_v1_database_migrates_and_new_run_works(legacy_v1_db: Path, monkeypatch, stepping_clock, redactor) -> None:
    monkeypatch.setenv("MMC_DB_PATH", str(legacy_v1_db))
    engine = init_db(legacy_v1_db)
    repo = RunRepository(engine)
    assert main(["history", "--json"]) == 0

    config = load_app_config(None)
    settings = Settings.from_env()
    registry = ProviderRegistry(config, settings)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, TokenEstimator("chars"))
    resolved = resolve_request(RunRequest(prompt="after migrate", seed=5), config, settings, redactor, registry)

    import asyncio

    asyncio.run(service.run(resolved))
    asyncio.run(registry.aclose())
    assert len(repo.list()) == 3
