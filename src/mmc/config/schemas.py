from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

ProviderId = Literal["anthropic", "openai", "google", "xai", "mock"]
MAX_CONTESTANTS = 8

MockBehavior = Literal[
    "ok",
    "stall",
    "gate",
    "error",
    "error_midstream",
    "missing_terminal",
    "no_usage",
    "usage_only_chunks",
    "empty",
    "reasoning_only",
    "refused",
    "blocked",
    "incomplete",
    "judge",
    "judge_bad_json_once",
    "judge_bad_json_always",
]

ErrorKind = Literal[
    "timeout",
    "auth",
    "rate_limit",
    "bad_request",
    "server",
    "network",
    "protocol",
    "unknown",
]


class MockOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    behavior: MockBehavior = "ok"
    output_words: int = Field(60, ge=0, le=500)
    fixed_usage: tuple[int, int] | None = None
    error_kind: ErrorKind = "server"
    error_message: str = "simulated failure"


class ProviderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    env_var: str | None = None
    reasoning_tokens_additive: bool = False


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str
    provider: ProviderId
    vendor: str
    model_id: str
    display_name: str
    supports_temperature: bool
    requires_env: str | None = None
    mock: MockOptions | None = None

    @model_validator(mode="after")
    def anthropic_no_temperature(self) -> ModelSpec:
        if self.provider == "anthropic" and self.supports_temperature:
            raise ValueError(f"Anthropic model {self.key} must have supports_temperature=false")
        return self


class ProfileSpec(BaseModel):
    contestants: list[str] = Field(min_length=1, max_length=MAX_CONTESTANTS)
    judge: str


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_prompt_chars: int = 32_000
    max_prompt_bytes: int = 131_072
    max_body_bytes: int = 262_144
    max_output_tokens: int = 32_768
    timeout_s_min: float = 0.1
    timeout_s_max: float = 300
    run_deadline_s: float = 900
    max_concurrent_runs: int = 2
    shutdown_grace_s: float = 30

    @model_validator(mode="after")
    def finite_bounds(self) -> Limits:
        for name in self.model_fields:
            val = getattr(self, name)
            if isinstance(val, float) and not val == val:  # noqa: PLR0124
                raise ValueError(f"{name} must be finite")
        return self

    @model_validator(mode="after")
    def deadline_covers_timeout(self) -> Limits:
        # judge max retries handled at app level; basic check
        if self.run_deadline_s < self.timeout_s_max:
            raise ValueError("run_deadline_s must be >= timeout_s_max")
        return self


class GenerationDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_output_tokens: int = 1024
    temperature: float = 0.2
    timeout_s: float = 60


class JudgeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_self_judging: bool = False
    include_incomplete: bool = False
    max_retries: int = Field(2, ge=0, le=5)
    timeout_s: float = Field(120, gt=0, le=300)
    temperature: float = 0.0
    output_tokens_base: int = 512
    output_tokens_per_cell: int = 200
    output_tokens_cap: int = 16_384
    rationale_max_chars: int = 600
    redact_terms: list[str]


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z_]{1,32}$")
    weight: Decimal = Field(gt=0)
    description: str


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    name: str
    scale_min: Literal[1] = 1
    scale_max: Literal[5] = 5
    criteria: list[Criterion] = Field(min_length=1, max_length=8)
    sha256: str = ""

    @model_validator(mode="after")
    def criteria_valid(self) -> Rubric:
        keys = [c.key for c in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate criterion keys")
        total = sum(c.weight for c in self.criteria)
        if total != Decimal("1"):
            raise ValueError(f"criteria weights must sum to 1, got {total}")
        return self


class LongContextTier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    above_input_tokens: int
    input_per_mtok: Decimal
    output_per_mtok: Decimal


class PriceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_key: str
    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)
    basis: Literal["exact", "from"] = "exact"
    long_context: LongContextTier | None = None
    effective_from: date
    effective_to: date | None = None
    source_url: HttpUrl
    retrieved_on: date


class PricingTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    currency: Literal["USD"]
    entries: list[PriceEntry]

    @model_validator(mode="after")
    def no_overlapping_ranges(self) -> PricingTable:
        by_model: dict[str, list[PriceEntry]] = {}
        for entry in self.entries:
            by_model.setdefault(entry.model_key, []).append(entry)
        for model_key, ranges in by_model.items():
            sorted_entries = sorted(ranges, key=lambda e: e.effective_from)
            for i, entry in enumerate(sorted_entries):
                end = entry.effective_to or date.max
                if i + 1 < len(sorted_entries):
                    next_start = sorted_entries[i + 1].effective_from
                    if end >= next_start:
                        raise ValueError(
                            f"overlapping price ranges for {model_key}: {entry.effective_from}..{end} and {next_start}"
                        )
        return self

    def lookup(self, model_key: str, on: date) -> PriceEntry | None:
        candidates = [
            e
            for e in self.entries
            if e.model_key == model_key and e.effective_from <= on and (e.effective_to is None or on <= e.effective_to)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.effective_from)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: dict[ProviderId, ProviderSpec]
    models: list[ModelSpec]
    profiles: dict[Literal["mock", "live"], ProfileSpec]
    defaults: GenerationDefaults
    limits: Limits
    judge: JudgeSettings
    rubric: Rubric
    pricing: PricingTable

    @model_validator(mode="after")
    def unique_model_keys(self) -> AppConfig:
        keys = [m.key for m in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate model keys")
        model_set = set(keys)
        for profile in self.profiles.values():
            for key in profile.contestants:
                if key not in model_set:
                    raise ValueError(f"profile references unknown model {key}")
            if profile.judge not in model_set:
                raise ValueError(f"profile references unknown judge {profile.judge}")
        return self

    def model(self, key: str) -> ModelSpec:
        for m in self.models:
            if m.key == key:
                return m
        raise KeyError(key)


def rubric_sha256(rubric: Rubric) -> str:
    payload = rubric.model_dump(mode="json", exclude={"sha256"})
    import json

    data = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()
