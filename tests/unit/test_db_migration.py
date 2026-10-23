from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from mmc.cli import main
from mmc.config.loader import load_app_config
from mmc.core.request import RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.providers.registry import ProviderRegistry
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.migrate import SCHEMA_VERSION
from mmc.storage.repository import RunRepository
from mmc.web.app import create_app


def _create_v1_schema_database(db_path: Path) -> None:
    """Simulate a database created by main @ 7a1af33 (schema version 1, no honesty columns)."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
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
    )
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    record = {
        "record_version": 1,
        "id": "legacy-run-1",
        "created_at": "2026-10-23T12:00:00+00:00",
        "profile": "mock",
        "app_version": "0.1.0",
        "prompt": "legacy prompt",
        "status": "completed",
        "seed": 1,
        "vendors_contacted": ["mock"],
        "judge_settings": config.judge.model_dump(mode="json"),
        "rubric": config.rubric.model_dump(mode="json"),
        "pricing_version": config.pricing.version,
        "pricing_entries_used": [],
        "answers": [
            {
                "model": spec.model_dump(mode="json"),
                "status": "ok",
                "text": "hi",
                "partial": False,
                "truncated": False,
                "finish_reason": None,
                "provider_request_id": None,
                "resolved_params": {},
                "usage": None,
                "timing": None,
                "cost": None,
                "error": None,
                "skip_reason": None,
            }
        ],
        "judge": None,
        "total": {"subtotal_usd": "0.001", "estimated": False, "unknown_count": 0},
    }
    conn.execute(
        "INSERT INTO runs (id, record_version, record_json) VALUES (?, ?, ?)",
        ("legacy-run-1", 1, json.dumps(record)),
    )
    conn.execute(
        "INSERT INTO run_summaries "
        "(run_id, created_at, prompt_preview, status, total_known_cost_usd, cost_flags) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("legacy-run-1", "2026-10-23T12:00:00+00:00", "legacy prompt", "completed", "0.001", ""),
    )
    conn.commit()
    conn.close()


def test_v1_database_migrates_list_history_and_new_run(tmp_path: Path, monkeypatch, stepping_clock, redactor) -> None:
    db_path = tmp_path / "legacy.sqlite"
    _create_v1_schema_database(db_path)
    monkeypatch.setenv("MMC_DB_PATH", str(db_path))

    engine = init_db(db_path)
    assert SCHEMA_VERSION == 2

    repo = RunRepository(engine)
    summaries = repo.list()
    assert len(summaries) == 1
    assert summaries[0].pricing_disclosure == "live"
    assert summaries[0].scores_mock is False

    assert main(["history", "--json"]) == 0

    config = load_app_config(None)
    settings = Settings.from_env()
    registry = ProviderRegistry(config, settings)
    redactor = Redactor([])
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, TokenEstimator("chars"))
    resolved = resolve_request(RunRequest(prompt="after migrate", seed=5), config, settings, redactor, registry)

    import asyncio

    asyncio.run(service.run(resolved))
    asyncio.run(registry.aclose())

    assert len(repo.list()) == 2

    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        api_rows = client.get("/api/runs").json()
        assert len(api_rows) == 2
        assert client.get("/history").status_code == 200
