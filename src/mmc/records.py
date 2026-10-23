from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mmc.config.schemas import JudgeSettings, PriceEntry, Rubric
from mmc.core.results import AnswerResult, CostTotal
from mmc.judge.schemas import JudgeOutcome

SummaryPricingDisclosure = Literal["live", "example_pricing_mock", "unknown"]

RunStatus = Literal["completed", "no_contestants", "cancelled"]


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: Literal[1] = 1
    id: str
    created_at: datetime
    profile: str
    app_version: str
    prompt: str
    status: RunStatus
    seed: int
    vendors_contacted: list[str]
    judge_settings: JudgeSettings
    rubric: Rubric
    pricing_version: str
    pricing_entries_used: list[PriceEntry]
    answers: list[AnswerResult]
    judge: JudgeOutcome | None
    total: CostTotal
    pricing_disclosure: Literal["live", "example_pricing_mock"] = "live"


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    created_at: datetime
    prompt_preview: str
    status: RunStatus
    total_known_cost_usd: Decimal
    cost_flags: list[str]
    pricing_disclosure: SummaryPricingDisclosure = "live"
    scores_mock: bool = False
