from __future__ import annotations

import csv
import io
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from mmc.config.loader import load_app_config
from mmc.honesty import apply_profile_honesty, honesty_summary_from_record_json
from mmc.records import RunRecord
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.migrate import SCHEMA_VERSION
from mmc.storage.repository import RunRepository
from mmc.web.app import create_app
from tests.unit.test_db_migration import _legacy_mock_record


def _create_broken_v2_database(db_path: Path) -> None:
    """v2 schema with f82e2f8-style wrong honesty columns (live/false/real total)."""
    config = load_app_config(None)
    record = _legacy_mock_record(config)
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
            pricing_disclosure TEXT NOT NULL DEFAULT 'live',
            scores_mock TEXT NOT NULL DEFAULT 'false',
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        INSERT INTO schema_meta (version) VALUES (2);
        """
    )
    conn.execute(
        "INSERT INTO runs (id, record_version, record_json) VALUES (?, ?, ?)",
        ("legacy-mock-1", 1, json.dumps(record)),
    )
    conn.execute(
        "INSERT INTO run_summaries "
        "(run_id, created_at, prompt_preview, status, total_known_cost_usd, cost_flags, "
        "pricing_disclosure, scores_mock) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy-mock-1",
            record["created_at"],
            record["prompt"][:200],
            record["status"],
            "0.001896",
            "",
            "live",
            "false",
        ),
    )
    conn.commit()
    conn.close()


def test_v2_broken_summary_repaired_on_init_db(tmp_path: Path) -> None:
    db_path = tmp_path / "broken-v2.sqlite"
    _create_broken_v2_database(db_path)
    engine = init_db(db_path)
    assert SCHEMA_VERSION == 3
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT version FROM schema_meta").fetchone()[0] == 3
    conn.close()
    repo = RunRepository(engine)
    row = next(s for s in repo.list() if s.id == "legacy-mock-1")
    assert row.pricing_disclosure == "example_pricing_mock"
    assert row.scores_mock is True
    assert row.total_known_cost_usd == Decimal(0)


def test_export_routes_honest_legacy_mock_records(tmp_path: Path, monkeypatch) -> None:
    from tests.unit.test_db_migration import _create_v1_database

    config = load_app_config(None)
    db_path = tmp_path / "legacy.sqlite"
    _create_v1_database(db_path, [("legacy-mock-1", _legacy_mock_record(config), "0.001896")])
    monkeypatch.setenv("MMC_DB_PATH", str(db_path))
    init_db(db_path)

    app = create_app(Settings.from_env())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        csv_resp = client.get("/export/runs.csv")
        assert csv_resp.status_code == 200
        csv_rows = list(csv.reader(io.StringIO(csv_resp.text)))
        header = csv_rows[0]
        data = csv_rows[1]
        assert data[header.index("pricing_disclosure")] == "example_pricing_mock"
        assert data[header.index("scores_mock")] == "true"
        assert data[header.index("cost_usd")] == "0"

        json_resp = client.get("/export/runs.json")
        assert json_resp.status_code == 200
        run = json_resp.json()["runs"][0]
        assert run["pricing_disclosure"] == "example_pricing_mock"
        assert run["judge"]["scores_mock"] is True
        assert run["answers"][0]["cost"]["total_usd"] == "0"


def test_non_mock_judge_provider_not_marked_scores_mock() -> None:
    config = load_app_config(None)
    record_dict = _legacy_mock_record(config)
    judge_model = config.model("google:gemini-3.8-flash")
    record_dict["judge"]["judge"] = judge_model.model_dump(mode="json")
    record = RunRecord.model_validate(record_dict)
    honest = apply_profile_honesty(record)
    assert honest.judge is not None
    assert honest.judge.judge is not None
    assert honest.judge.judge.provider != "mock"
    assert honest.judge.scores_mock is False
    disc, scores_mock, _ = honesty_summary_from_record_json(json.dumps(record_dict))
    assert disc == "example_pricing_mock"
    assert scores_mock is False


def test_honesty_summary_unknown_when_profile_missing() -> None:
    raw = json.dumps({"total": {"subtotal_usd": "1.5"}})
    disc, scores_mock, subtotal = honesty_summary_from_record_json(raw)
    assert disc == "unknown"
    assert scores_mock is False
    assert subtotal == Decimal("1.5")
