from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mmc.config.schemas import ModelSpec
from mmc.core.results import Cost, Timing, TokenUsage

JudgeStatus = Literal[
    "ok",
    "skipped_no_answers",
    "unavailable",
    "invalid_output",
    "error",
    "timeout",
    "cancelled",
]


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion: str
    score: int
    rationale: str


class JudgeAttempt(BaseModel):
    attempt_no: int
    raw_output: str
    valid: bool
    error: str | None
    outcome: str | None
    finish_reason: str | None
    provider_request_id: str | None
    usage: TokenUsage | None
    timing: Timing | None
    cost: Cost | None


class AnswerScores(BaseModel):
    criteria: dict[str, CriterionScore]
    overall: Decimal
    self_judged: bool


class JudgeOutcome(BaseModel):
    status: JudgeStatus
    judge: ModelSpec | None
    seed: int
    label_map: dict[str, str]
    scores: dict[str, AnswerScores]
    excluded: dict[str, str]
    attempts: list[JudgeAttempt]
    resolved_params: dict[str, str]
