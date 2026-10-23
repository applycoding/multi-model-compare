from __future__ import annotations

import json
import math
import os
import shutil
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from mmc.cli import main as cli_main
from mmc.config.loader import load_app_config
from mmc.config.schemas import AppConfig, MockOptions, ModelSpec
from mmc.core.request import RequestValidationError, RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.providers.registry import ProviderRegistry
from mmc.records import RunRecord
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.repository import RunRepository
from mmc.storage.tables import RunRow
from mmc.web.app import create_app
from tests.conftest import (
    SENTINEL_ANTHROPIC,
    SENTINEL_GEMINI,
    SENTINEL_OPENAI,
    SENTINEL_XAI,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "config"
GOLDEN_PATH = Path(__file__).parent / "golden_final_state.json"
SEED = 20261023

P1 = "Scenario prompt for multi-step seeded session."
P3 = "P3: stall mock-gpt with a short timeout."
P4 = "P4: grok rate_limit error carries a secret-shaped string."
P5 = "P5: grok requires_env when XAI key unset."
P6 = "P6: claude no_usage uses estimated tokens."
P7 = "P7: mixed refusal block incomplete and ok."
P8 = "P8: missing_terminal and usage_only_chunks."
P9 = "P9: judge_bad_json_once then success."
P10 = "P10: judge_bad_json_always exhausts retries."
P11 = "P11: all contestants error."
P12 = "P12: all contestants require_env missing."
P13 = P1
P14 = "=SUM(1,2)"
P15 = "P15: includes mock-unpriced for unknown cost."
P16 = P1

def _inp_tokens(prompt: str) -> int:
    return math.ceil(len(prompt) / 4)


_QUANT = Decimal("0.000001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _hand_answer_cost(prompt: str, input_per_mtok: Decimal, output_per_mtok: Decimal) -> Decimal:
    inp = _inp_tokens(prompt)
    in_cost = _q(Decimal(inp) * input_per_mtok / Decimal(1_000_000))
    out_cost = _q(Decimal(60) * output_per_mtok / Decimal(1_000_000))
    return in_cost + out_cost


def _hand_judge_attempt_cost(input_per_mtok: Decimal, output_per_mtok: Decimal) -> Decimal:
    in_cost = _q(Decimal(1000) * input_per_mtok / Decimal(1_000_000))
    out_cost = _q(Decimal(200) * output_per_mtok / Decimal(1_000_000))
    return in_cost + out_cost


P1_ANSWER_COST = _hand_answer_cost(P1, Decimal("1"), Decimal("2"))
P1_ANSWER_COST_V2 = _hand_answer_cost(P1, Decimal("2"), Decimal("4"))
JUDGE_ATTEMPT_COST = _hand_judge_attempt_cost(Decimal("1"), Decimal("2"))
JUDGE_ATTEMPT_COST_V2 = _hand_judge_attempt_cost(Decimal("2"), Decimal("4"))


EXPECTED_STEPS: dict[int, dict[str, Any]] = {
    1: {
        "run_status": "completed",
        "judged": 3,
        "judge_status": "ok",
        "judge_attempts": 1,
        "excluded": ["mock:mock-gemini"],
        "answer_ok": 4,
        "run_subtotal": str(P1_ANSWER_COST * 4 + JUDGE_ATTEMPT_COST),
    },
    2: {
        "judged": 4,
        "judge_status": "ok",
        "self_judged_gemini": True,
        "run_subtotal": str(P1_ANSWER_COST * 4 + JUDGE_ATTEMPT_COST),
    },
    3: {
        "gpt_status": "timeout",
        "judged": 2,
        "judge_status": "ok",
        "total_estimated": True,
    },
    4: {
        "grok_status": "error",
        "judged": 2,
        "sentinel_redacted_in_error": True,
    },
    5: {
        "grok_status": "skipped",
        "judged": 2,
    },
    6: {
        "claude_cost_estimated": True,
        "judged": 3,
    },
    7: {
        "judged": 1,
        "grok_only_judged": True,
    },
    8: {
        "claude_status": "error",
        "gpt_status": "ok",
        "judged": 2,
    },
    9: {
        "judge_attempts": 2,
        "judge_status": "ok",
    },
    10: {
        "judge_attempts": 3,
        "judge_status": "invalid_output",
        "answers_kept": 4,
    },
    11: {
        "judge_status": "skipped_no_answers",
    },
    12: {
        "run_status": "no_contestants",
    },
    13: {
        "pricing_version": "2026-11-01",
        "answer_cost_vs_step1": 2,
        "prior_snapshots_unchanged": True,
    },
    14: {
        "run_0001_unchanged": True,
        "html_unchanged": True,
    },
    15: {
        "contestant_count": 4,
        "prompt": P14,
    },
    16: {
        "rejections": 5,
        "call_count_delta": 0,
        "row_count_delta": 0,
    },
    17: {
        "unknown_count": 1,
        "history_runs": 15,
        "csv_formula_prefix": True,
    },
    18: {
        "labels_match_step1": True,
        "scores_match_step1": True,
    },
}


class ScenarioCtx:
    def __init__(
        self,
        config: AppConfig,
        settings: Settings,
        service: CompareService,
        repo: RunRepository,
        registry: ProviderRegistry,
        redactor: Redactor,
        config_dir: Path,
        db_path: Path,
    ) -> None:
        self.config = config
        self.settings = settings
        self.service = service
        self.repo = repo
        self.registry = registry
        self.redactor = redactor
        self.config_dir = config_dir
        self.db_path = db_path
        self.step1_record: RunRecord | None = None
        self.step1_html: str | None = None
        self.snapshots_1_12: dict[str, bytes] = {}


def _patch_models(config: AppConfig, updates: dict[str, dict[str, Any]]) -> AppConfig:
    models: list[ModelSpec] = []
    for spec in config.models:
        if spec.key in updates:
            patch = updates[spec.key]
            mock_patch = patch.pop("mock", None)
            new_spec = spec
            if mock_patch is not None:
                base = spec.mock or MockOptions()
                new_spec = spec.model_copy(update={"mock": base.model_copy(update=mock_patch)})
            if patch:
                new_spec = new_spec.model_copy(update=patch)
            models.append(new_spec)
        else:
            models.append(spec)
    return config.model_copy(update={"models": models})


def _apply_config(ctx: ScenarioCtx, config: AppConfig) -> None:
    ctx.config = config
    ctx.service._config = config
    ctx.registry._config = config
    ctx.registry._providers.clear()


def _row_json(repo: RunRepository, run_id: str) -> bytes:
    from sqlmodel import Session

    with Session(repo._engine) as session:
        row = session.get(RunRow, run_id)
        assert row is not None
        return row.record_json.encode("utf-8")


def _assert_step(record: RunRecord, step: int, ctx: ScenarioCtx) -> None:
    exp = EXPECTED_STEPS[step]
    if "run_status" in exp:
        assert record.status == exp["run_status"]
    if "judged" in exp:
        assert record.judge is not None
        assert len(record.judge.scores) == exp["judged"]
    if "judge_status" in exp:
        assert record.judge is not None
        assert record.judge.status == exp["judge_status"]
    if "judge_attempts" in exp:
        assert record.judge is not None
        assert len(record.judge.attempts) == exp["judge_attempts"]
    if "excluded" in exp:
        assert record.judge is not None
        for key in exp["excluded"]:
            assert key in record.judge.excluded
    if "answer_ok" in exp:
        assert sum(1 for a in record.answers if a.status == "ok") == exp["answer_ok"]
    if "self_judged_gemini" in exp:
        assert record.judge is not None
        assert record.judge.scores["mock:mock-gemini"].self_judged is True
    if "gpt_status" in exp:
        gpt = next(a for a in record.answers if a.model.key == "mock:mock-gpt")
        assert gpt.status == exp["gpt_status"]
    if "grok_status" in exp:
        grok = next(a for a in record.answers if a.model.key == "mock:mock-grok")
        assert grok.status == exp["grok_status"]
    if "claude_status" in exp:
        claude = next(a for a in record.answers if a.model.key == "mock:mock-claude")
        assert claude.status == exp["claude_status"]
    if "sentinel_redacted_in_error" in exp:
        grok = next(a for a in record.answers if a.model.key == "mock:mock-grok")
        assert grok.error is not None
        assert SENTINEL_XAI not in (grok.error.message or "")
        assert "[REDACTED]" in (grok.error.message or "")
    if "claude_cost_estimated" in exp:
        claude = next(a for a in record.answers if a.model.key == "mock:mock-claude")
        assert claude.cost is not None
        assert claude.cost.status == "estimated"
    if "grok_only_judged" in exp:
        assert record.judge is not None
        assert list(record.judge.scores.keys()) == ["mock:mock-grok"]
    if "total_estimated" in exp:
        assert record.total.estimated is True
    if "answers_kept" in exp:
        assert len(record.answers) == exp["answers_kept"]
    if "run_subtotal" in exp:
        assert str(record.total.subtotal_usd) == exp["run_subtotal"]
    if "pricing_version" in exp:
        assert record.pricing_version == exp["pricing_version"]
    if "answer_cost_vs_step1" in exp:
        mult = exp["answer_cost_vs_step1"]
        for ans in record.answers:
            assert ans.cost is not None
            assert ans.cost.total_usd is not None
            assert ans.cost.total_usd == P1_ANSWER_COST * mult
    if "contestant_count" in exp:
        assert len(record.answers) == exp["contestant_count"]
    if "prompt" in exp:
        assert record.prompt == exp["prompt"]
    if "unknown_count" in exp:
        assert record.total.unknown_count == exp["unknown_count"]


async def _run(ctx: ScenarioCtx, req: RunRequest) -> RunRecord:
    resolved = resolve_request(req, ctx.config, ctx.settings, ctx.redactor, ctx.registry)
    return await ctx.service.run(resolved)


def _normalize_state(repo: RunRepository) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for rec in sorted(repo.iter_all(), key=lambda r: (r.created_at, r.id)):
        data = json.loads(rec.model_dump_json())
        for ans in data.get("answers", []):
            ans.pop("timing", None)
        judge = data.get("judge")
        if judge:
            for att in judge.get("attempts", []):
                att.pop("timing", None)
        runs.append(data)
    return {"runs": runs, "run_count": len(runs)}


def _assert_no_sentinel_in_db(db_path: Path) -> None:
    needles = (SENTINEL_ANTHROPIC, SENTINEL_OPENAI, SENTINEL_GEMINI, SENTINEL_XAI)
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(db_path) + suffix)
        if not path.exists():
            continue
        blob = path.read_bytes()
        for needle in needles:
            assert needle.encode() not in blob


@pytest.fixture
def scenario_ctx(tmp_path, monkeypatch, id_factory, stepping_clock, sentinel_keys) -> ScenarioCtx:
    cfg_dir = FIXTURES
    db = tmp_path / "scenario.sqlite3"
    monkeypatch.setenv("MMC_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("MMC_DB_PATH", str(db))
    settings = Settings.from_env()
    config = load_app_config(cfg_dir)
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
    return ScenarioCtx(config, settings, service, repo, registry, redactor, cfg_dir, db)


@pytest.mark.asyncio
async def test_long_scenario(scenario_ctx: ScenarioCtx, caplog, monkeypatch, tmp_path) -> None:
    ctx = scenario_ctx
    step1_scores: dict[str, Any] | None = None
    step1_labels: dict[str, str] | None = None

    # 1
    rec = await _run(ctx, RunRequest(prompt=P1, seed=SEED))
    _assert_step(rec, 1, ctx)
    ctx.step1_record = ctx.repo.get(rec.id)
    assert ctx.step1_record == rec
    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        ctx.step1_html = client.get(f"/runs/{rec.id}").text
    assert rec.judge is not None
    step1_scores = {k: v.overall for k, v in rec.judge.scores.items()}
    step1_labels = dict(rec.judge.label_map)
    ctx.snapshots_1_12[rec.id] = _row_json(ctx.repo, rec.id)

    # 2
    rec = await _run(ctx, RunRequest(prompt=P1, seed=SEED, allow_self_judging=True))
    _assert_step(rec, 2, ctx)

    # 3
    cfg = _patch_models(
        ctx.config,
        {"mock:mock-gpt": {"mock": {"behavior": "stall"}}},
    )
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P3, seed=SEED, timeout_s=0.2))
    _assert_step(rec, 3, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 4
    cfg = _patch_models(
        ctx.config,
        {
            "mock:mock-grok": {
                "mock": {
                    "behavior": "error",
                    "error_kind": "rate_limit",
                    "error_message": f"limit exceeded key={SENTINEL_XAI}",
                }
            }
        },
    )
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P4, seed=SEED))
    _assert_step(rec, 4, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 5
    cfg = _patch_models(ctx.config, {"mock:mock-grok": {"requires_env": "XAI_API_KEY"}})
    _apply_config(ctx, cfg)
    keys = {k: v for k, v in ctx.settings.keys.items() if k != "XAI_API_KEY"}
    ctx.settings = ctx.settings.model_copy(update={"keys": keys})
    ctx.registry._settings = ctx.settings
    ctx.service._settings = ctx.settings
    rec = await _run(ctx, RunRequest(prompt=P5, seed=SEED))
    _assert_step(rec, 5, ctx)
    ctx.settings = Settings.from_env()
    ctx.registry._settings = ctx.settings
    ctx.service._settings = ctx.settings
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 6
    cfg = _patch_models(ctx.config, {"mock:mock-claude": {"mock": {"behavior": "no_usage"}}})
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P6, seed=SEED))
    _assert_step(rec, 6, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 7
    cfg = _patch_models(
        ctx.config,
        {
            "mock:mock-claude": {"mock": {"behavior": "refused"}},
            "mock:mock-gpt": {"mock": {"behavior": "blocked"}},
            "mock:mock-gemini": {"mock": {"behavior": "incomplete"}},
            "mock:mock-grok": {"mock": {"behavior": "ok"}},
        },
    )
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P7, seed=SEED))
    _assert_step(rec, 7, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 8
    cfg = _patch_models(
        ctx.config,
        {
            "mock:mock-claude": {"mock": {"behavior": "missing_terminal"}},
            "mock:mock-gpt": {"mock": {"behavior": "usage_only_chunks"}},
        },
    )
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P8, seed=SEED))
    _assert_step(rec, 8, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 9
    cfg = _patch_models(ctx.config, {"mock:mock-judge": {"mock": {"behavior": "judge_bad_json_once"}}})
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P9, seed=SEED))
    _assert_step(rec, 9, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 10
    cfg = _patch_models(ctx.config, {"mock:mock-judge": {"mock": {"behavior": "judge_bad_json_always"}}})
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P10, seed=SEED))
    _assert_step(rec, 10, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 11
    cfg = _patch_models(
        ctx.config,
        {
            "mock:mock-claude": {"mock": {"behavior": "error"}},
            "mock:mock-gpt": {"mock": {"behavior": "error"}},
            "mock:mock-gemini": {"mock": {"behavior": "error"}},
            "mock:mock-grok": {"mock": {"behavior": "error"}},
        },
    )
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P11, seed=SEED))
    _assert_step(rec, 11, ctx)
    _apply_config(ctx, load_app_config(ctx.config_dir))

    # 12
    cfg = _patch_models(
        ctx.config,
        {
            "mock:mock-claude": {"requires_env": "ANTHROPIC_API_KEY"},
            "mock:mock-gpt": {"requires_env": "OPENAI_API_KEY"},
            "mock:mock-gemini": {"requires_env": "GEMINI_API_KEY"},
            "mock:mock-grok": {"requires_env": "XAI_API_KEY"},
        },
    )
    _apply_config(ctx, cfg)
    empty_keys: dict[str, SecretStr] = {}
    ctx.settings = ctx.settings.model_copy(update={"keys": empty_keys})
    ctx.registry._settings = ctx.settings
    ctx.service._settings = ctx.settings
    rec = await _run(ctx, RunRequest(prompt=P12, seed=SEED))
    _assert_step(rec, 12, ctx)
    ctx.settings = Settings.from_env()
    ctx.registry._settings = ctx.settings
    ctx.service._settings = ctx.settings
    _apply_config(ctx, load_app_config(ctx.config_dir))

    for rid in [f"run-{i:04d}" for i in range(1, 13)]:
        ctx.snapshots_1_12[rid] = _row_json(ctx.repo, rid)

    # 13 pricing v2
    cfg = load_app_config(ctx.config_dir, pricing_file="pricing_v2.yaml")
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P13, seed=SEED))
    _assert_step(rec, 13, ctx)
    for i in range(1, 13):
        rid = f"run-{i:04d}"
        assert _row_json(ctx.repo, rid) == ctx.snapshots_1_12[rid]

    # 14 rename + rubric v2
    cfg14_dir = tmp_path / "cfg14"
    shutil.copytree(ctx.config_dir, cfg14_dir)
    shutil.copy(cfg14_dir / "models_renamed.yaml", cfg14_dir / "models.yaml")
    cfg = load_app_config(cfg14_dir, rubric_file="rubric_v2.yaml")
    _apply_config(ctx, cfg)
    assert ctx.repo.get("run-0001") == ctx.step1_record
    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        html = client.get("/runs/run-0001").text
    assert html == ctx.step1_html

    # 15 dedupe models
    dup_models = [
        "mock:mock-claude",
        "mock:mock-gpt",
        "mock:mock-gemini",
        "mock:mock-grok",
        "mock:mock-claude",
        "mock:mock-gpt",
    ]
    rec = await _run(ctx, RunRequest(prompt=P14, seed=SEED, models=dup_models))
    _assert_step(rec, 15, ctx)

    # 16 rejections
    before_calls = ctx.registry.call_count
    before_rows = ctx.repo.count()
    default_cfg = load_app_config(None)
    nine_models = [m.key for m in default_cfg.models if m.provider != "mock"][:9]
    reject_cases: list[RunRequest] = [
        RunRequest(prompt="   ", seed=SEED),
        RunRequest(prompt="nine", seed=SEED, models=nine_models),
        RunRequest(prompt="nan temp", seed=SEED, temperature=float("nan")),
        RunRequest(prompt="bad model", seed=SEED, models=["mock:no-such"]),
        RunRequest(prompt=f"leak {SENTINEL_OPENAI}", seed=SEED),
    ]
    for req in reject_cases:
        cfg = default_cfg if req.models == nine_models else ctx.config
        with pytest.raises(RequestValidationError):
            resolve_request(req, cfg, ctx.settings, ctx.redactor, ctx.registry)
    assert ctx.registry.call_count == before_calls
    assert ctx.repo.count() == before_rows

    # 17 P15 + CLI export/history
    rec = await _run(
        ctx,
        RunRequest(
            prompt=P15,
            seed=SEED,
            models=[
                "mock:mock-claude",
                "mock:mock-gpt",
                "mock:mock-gemini",
                "mock:mock-grok",
                "mock:mock-unpriced",
            ],
        ),
    )
    _assert_step(rec, 17, ctx)
    monkeypatch.setenv("MMC_DB_PATH", str(ctx.db_path))
    monkeypatch.setenv("MMC_CONFIG_DIR", str(ctx.config_dir))
    import sys
    from io import StringIO

    old_out = sys.stdout
    sys.stdout = StringIO()
    try:
        assert cli_main(["history", "--limit", "50", "--json"]) == 0
        hist_json = json.loads(sys.stdout.getvalue())
    finally:
        sys.stdout = old_out
    assert len(hist_json) == 15
    csv_path = tmp_path / "all.csv"
    assert cli_main(["export", "--format", "json", "--out", "-"]) == 0
    assert cli_main(["export", "--format", "csv", "--out", str(csv_path)]) == 0
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "'=SUM(1,2)" in csv_text

    # 18 repeat P1 (restore step-1 rubric/models so judge scores match)
    cfg = load_app_config(FIXTURES, pricing_file="pricing_v2.yaml")
    _apply_config(ctx, cfg)
    rec = await _run(ctx, RunRequest(prompt=P16, seed=SEED))
    assert rec.judge is not None
    assert rec.judge.label_map == step1_labels
    assert {k: v.overall for k, v in rec.judge.scores.items()} == step1_scores

    assert ctx.repo.count() == 16

    for rec_all in ctx.repo.iter_all():
        for ans in rec_all.answers:
            if ans.timing and ans.timing.ttft_ms is not None:
                assert 0 <= ans.timing.ttft_ms <= ans.timing.total_ms

    _assert_no_sentinel_in_db(ctx.db_path)
    for needle in (SENTINEL_ANTHROPIC, SENTINEL_OPENAI, SENTINEL_GEMINI, SENTINEL_XAI):
        assert needle not in caplog.text

    normalized = _normalize_state(ctx.repo)
    if os.environ.get("MMC_UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        if not GOLDEN_PATH.is_file():
            pytest.fail(
                f"Missing {GOLDEN_PATH.name}; commit the golden file or set MMC_UPDATE_GOLDEN=1 locally to regenerate"
            )
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        assert normalized == golden
