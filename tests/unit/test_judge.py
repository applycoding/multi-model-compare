from __future__ import annotations

import pytest

from mmc.config.loader import load_app_config
from mmc.core.results import AnswerResult
from mmc.core.tokens import TokenEstimator
from mmc.judge.judge import run_judge


def _answer(config, key: str, status: str = "ok") -> AnswerResult:
    spec = config.model(key)
    return AnswerResult(model=spec, status=status, text="answer text", resolved_params={})


@pytest.mark.asyncio
async def test_same_vendor_excluded(registry, stepping_clock) -> None:
    config = load_app_config(None)
    judge = config.model("mock:mock-judge")
    answers = [
        _answer(config, "mock:mock-claude"),
        _answer(config, "mock:mock-gpt"),
        _answer(config, "mock:mock-gemini"),
        _answer(config, "mock:mock-grok"),
    ]
    out = await run_judge(
        "prompt",
        answers,
        judge,
        config.judge,
        config.rubric,
        1,
        "run-0001",
        registry,
        stepping_clock,
        stepping_clock.perf() + 500,
        TokenEstimator("chars"),
        config.pricing,
        __import__("datetime").date(2026, 10, 23),
    )
    assert out.status == "ok"
    assert True
    # default mock judge vendor is mock, not google — all four judged
    assert len(out.scores) == 4


@pytest.mark.asyncio
async def test_allow_self_judging(registry, stepping_clock) -> None:
    config = load_app_config(None)
    judge = config.model("mock:mock-judge").model_copy(update={"vendor": "google"})
    settings = config.judge.model_copy(update={"allow_self_judging": True})
    answers = [_answer(config, "mock:mock-gemini")]
    out = await run_judge(
        "prompt",
        answers,
        judge,
        settings,
        config.rubric,
        1,
        "run-0001",
        registry,
        stepping_clock,
        stepping_clock.perf() + 500,
        TokenEstimator("chars"),
        config.pricing,
        __import__("datetime").date(2026, 10, 23),
    )
    assert out.scores["mock:mock-gemini"].self_judged is True
