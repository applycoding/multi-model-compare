from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from mmc.config.loader import load_app_config
from mmc.core.request import RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.providers.registry import ProviderRegistry
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings

FIXTURES = Path(__file__).parent.parent / "fixtures" / "config"
PROMPT = "Scenario prompt for multi-step seeded session."
SEED = 20261023


def _per_answer_cost(prompt: str, pricing_version: str = "2026-10-23") -> Decimal:
    inp = math.ceil(len(prompt) / 4)
    from datetime import date

    from mmc.core.pricing import compute_cost
    from mmc.core.results import TokenUsage

    config = load_app_config(FIXTURES)
    usage = TokenUsage(
        input_tokens=inp,
        output_tokens=60,
        reasoning_tokens=None,
        total_tokens=inp + 60,
        raw={},
        input_source="provider",
        output_source="provider",
    )
    cost = compute_cost("mock:mock-gpt", usage, False, config.pricing, date(2026, 10, 23))
    assert cost.total_usd is not None
    return cost.total_usd


EXPECTED_STEPS: dict[int, dict[str, object]] = {
    1: {"judged": 3, "judge_status": "ok", "excluded_vendor": "mock:mock-gemini"},
}


@pytest.fixture
def scenario_env(tmp_path, monkeypatch, id_factory, stepping_clock):
    cfg_dir = FIXTURES
    db = tmp_path / "scenario.sqlite3"
    monkeypatch.setenv("MMC_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("MMC_DB_PATH", str(db))
    settings = Settings.from_env()
    config = load_app_config(cfg_dir)
    redactor = Redactor([v.get_secret_value() for v in settings.keys.values()])
    engine = __import__("mmc.storage.db", fromlist=["init_db"]).init_db(db)
    repo = __import__("mmc.storage.repository", fromlist=["RunRepository"]).RunRepository(engine)
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
    yield config, settings, service, repo, registry, redactor


@pytest.mark.asyncio
async def test_step1_self_vendor_excluded(scenario_env) -> None:
    config, settings, service, repo, registry, redactor = scenario_env
    req = RunRequest(prompt=PROMPT, seed=SEED)
    resolved = resolve_request(req, config, settings, redactor, registry)
    record = await service.run(resolved)
    assert record.judge and record.judge.status == "ok"
    assert len(record.judge.scores) == 3
    assert "mock:mock-gemini" in record.judge.excluded
    cost = _per_answer_cost(PROMPT)
    for ans in record.answers:
        if ans.cost and ans.cost.total_usd:
            assert ans.cost.total_usd == cost


def test_golden_file_valid_json() -> None:
    golden = Path(__file__).parent / "golden_final_state.json"
    assert golden.exists()
    json.loads(golden.read_text(encoding="utf-8"))
