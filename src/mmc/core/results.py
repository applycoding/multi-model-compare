from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mmc.config.schemas import ErrorKind, ModelSpec, PriceEntry

AnswerStatus = Literal[
    "ok",
    "incomplete",
    "refused",
    "blocked",
    "error",
    "timeout",
    "cancelled",
    "skipped",
]
UsageSource = Literal["provider", "estimated"]


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    raw: dict[str, int | None]
    input_source: UsageSource
    output_source: UsageSource
    estimator: str | None = None


class Timing(BaseModel):
    ttft_ms: float | None
    total_ms: float


class PriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry: PriceEntry
    tier: Literal["base", "long_context"]
    pricing_version: str


class Cost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["known", "estimated", "unknown"]
    input_usd: Decimal | None = None
    output_usd: Decimal | None = None
    total_usd: Decimal | None = None
    price: PriceSnapshot | None = None
    notes: list[str] = Field(default_factory=list)


class CostTotal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subtotal_usd: Decimal
    estimated: bool
    unknown_count: int


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ErrorKind | Literal["cancelled"]
    message: str


class AnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ModelSpec
    status: AnswerStatus
    text: str = ""
    partial: bool = False
    truncated: bool = False
    finish_reason: str | None = None
    provider_request_id: str | None = None
    resolved_params: dict[str, str] = Field(default_factory=dict)
    usage: TokenUsage | None = None
    timing: Timing | None = None
    cost: Cost | None = None
    error: ErrorInfo | None = None
    skip_reason: str | None = None
