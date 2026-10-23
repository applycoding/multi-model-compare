from __future__ import annotations

import csv
import io
import json

import pytest

from mmc.export import RunExport, to_csv, to_json
from tests.unit.test_repository import _minimal_record


def test_json_schema(stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    from datetime import UTC, datetime

    payload = json.loads(to_json([rec], datetime.now(UTC)))
    assert RunExport.model_validate(payload).schema_version == 1


@pytest.mark.asyncio
async def test_csv_includes_pricing_disclosure_and_scores_mock(
    tmp_db, monkeypatch, stepping_clock, redactor, repo
) -> None:
    from mmc.config.loader import load_app_config
    from mmc.core.request import RunRequest, resolve_request
    from mmc.core.tokens import TokenEstimator
    from mmc.providers.registry import ProviderRegistry
    from mmc.service import CompareService
    from mmc.settings import Settings

    monkeypatch.setenv("MMC_DB_PATH", str(tmp_db))
    settings = Settings.from_env()
    config = load_app_config(None)
    registry = ProviderRegistry(config, settings)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, TokenEstimator("chars"))
    resolved = resolve_request(RunRequest(prompt="csv export", seed=11), config, settings, redactor, registry)
    rec = await service.run(resolved)
    await registry.aclose()
    text = to_csv([rec])
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    assert "pricing_disclosure" in header
    assert "scores_mock" in header
    disc_idx = header.index("pricing_disclosure")
    mock_idx = header.index("scores_mock")
    assert rows[1][disc_idx] == "example_pricing_mock"
    assert rows[1][mock_idx] == "true"


def test_csv_formula_prefix(stepping_clock, id_factory) -> None:
    rec = _minimal_record(id_factory(), stepping_clock)
    rec = rec.model_copy(update={"prompt": "=SUM(1,2)"})
    text = to_csv([rec])
    rows = list(csv.reader(io.StringIO(text)))
    prompt_cell = rows[1][2]
    assert prompt_cell.startswith("'")
