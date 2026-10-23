from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mmc.cli import main as cli_main
from mmc.config.loader import load_app_config
from mmc.config.schemas import MockOptions
from mmc.core.request import RequestValidationError, RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.export import to_csv, to_json
from mmc.providers.registry import ProviderRegistry
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.repository import RunRepository
from mmc.web.app import create_app
from tests.conftest import (
    SENTINEL_ANTHROPIC,
    SENTINEL_GEMINI,
    SENTINEL_OPENAI,
    SENTINEL_XAI,
)

SENTINELS = (SENTINEL_ANTHROPIC, SENTINEL_OPENAI, SENTINEL_GEMINI, SENTINEL_XAI)


def _db_bytes(db_path: Path) -> bytes:
    chunks: list[bytes] = []
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(db_path) + suffix)
        if path.exists():
            chunks.append(path.read_bytes())
    return b"".join(chunks)


@pytest.mark.asyncio
async def test_sentinel_never_reaches_sinks(
    tmp_path,
    monkeypatch,
    sentinel_keys,
    id_factory,
    stepping_clock,
    caplog,
) -> None:
    db = tmp_path / "sentinel.sqlite3"
    monkeypatch.setenv("MMC_DB_PATH", str(db))
    monkeypatch.setenv("MMC_CONFIG_DIR", str(Path(__file__).parent.parent / "fixtures" / "config"))
    settings = Settings.from_env()
    config = load_app_config(settings.config_dir)
    redactor = Redactor([v.get_secret_value() for v in settings.keys.values()])
    engine = init_db(db)
    repo = RunRepository(engine)
    registry = ProviderRegistry(config, settings)
    service = CompareService(
        config,
        settings,
        registry,
        repo,
        stepping_clock,
        redactor,
        TokenEstimator("chars"),
        id_factory,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RequestValidationError):
            resolve_request(
                RunRequest(prompt=f"prefix {SENTINEL_OPENAI} suffix", seed=1),
                config,
                settings,
                redactor,
                registry,
            )
        assert registry.call_count == 0
        assert repo.count() == 0

        grok = config.model("mock:mock-grok").model_copy(
            update={
                "mock": MockOptions(
                    behavior="error",
                    error_kind="server",
                    error_message=f"traceback embeds {SENTINEL_XAI}",
                )
            }
        )
        models = [m if m.key != "mock:mock-grok" else grok for m in config.models]
        err_config = config.model_copy(update={"models": models})
        registry._config = err_config
        service._config = err_config
        resolved = resolve_request(
            RunRequest(prompt="sentinel sink integration", seed=42),
            err_config,
            settings,
            redactor,
            registry,
        )
        await service.run(resolved)

    cap_text = caplog.text
    for needle in SENTINELS:
        assert needle not in cap_text

    db_blob = _db_bytes(db)
    for needle in SENTINELS:
        assert needle.encode() not in db_blob

    app = create_app(settings)
    run_id = "run-0001"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        html = client.get(f"/runs/{run_id}").text
        api_json = client.get(f"/api/runs/{run_id}").json()
    for needle in SENTINELS:
        assert needle not in html
        dumped = json.dumps(api_json)
        assert needle not in dumped

    monkeypatch.setenv("MMC_DB_PATH", str(db))
    out = StringIO()
    import sys

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = out
    sys.stderr = StringIO()
    try:
        assert cli_main(["show", run_id, "--json"]) == 0
        cli_stdout = out.getvalue()
        cli_stderr = sys.stderr.getvalue()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    for needle in SENTINELS:
        assert needle not in cli_stdout
        assert needle not in cli_stderr

    record = repo.get(run_id)
    assert record is not None
    export_json = to_json([record], datetime.now(UTC))
    export_csv = to_csv([record])
    for needle in SENTINELS:
        assert needle not in export_json
        assert needle not in export_csv
