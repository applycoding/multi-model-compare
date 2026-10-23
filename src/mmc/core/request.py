from __future__ import annotations

import math
import secrets
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from mmc.config.schemas import MAX_CONTESTANTS, AppConfig, JudgeSettings, ModelSpec
from mmc.providers.base import ProviderRequest
from mmc.redact import Redactor
from mmc.settings import Settings

if TYPE_CHECKING:
    from mmc.providers.registry import ProviderRegistry


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    models: list[str] | None = None
    judge: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    timeout_s: float | None = None
    allow_self_judging: bool | None = None
    seed: int | None = None


class ResolvedRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    contestants: list[ModelSpec]
    judge: ModelSpec | None
    requests: dict[str, ProviderRequest]
    judge_settings: JudgeSettings
    seed: int
    vendors_contacted: list[str]


class RequestValidationError(ValueError):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__(errors[0][1] if errors else "validation error")
        self.errors = errors


def resolve_request(
    req: RunRequest,
    config: AppConfig,
    settings: Settings,
    redactor: Redactor,
    registry: ProviderRegistry,
) -> ResolvedRun:
    errors: list[tuple[str, str]] = []
    prompt = req.prompt
    if not prompt.strip():
        errors.append(("prompt", "prompt is required"))
    if len(prompt) > config.limits.max_prompt_chars:
        errors.append(("prompt", f"prompt exceeds {config.limits.max_prompt_chars} characters"))
    if len(prompt.encode("utf-8")) > config.limits.max_prompt_bytes:
        errors.append(("prompt", f"prompt exceeds {config.limits.max_prompt_bytes} bytes"))
    if redactor.contains_secret(prompt):
        errors.append(("prompt", "prompt contains a configured API key"))
    if errors:
        raise RequestValidationError(errors)

    profile = config.profiles[settings.profile]
    model_keys = req.models if req.models is not None else profile.contestants
    seen: set[str] = set()
    deduped: list[str] = []
    for key in model_keys:
        if key not in seen:
            seen.add(key)
            deduped.append(key)
    if not deduped:
        errors.append(("models", "at least one contestant required"))
    if len(deduped) > MAX_CONTESTANTS:
        errors.append(("models", f"at most {MAX_CONTESTANTS} contestants"))
    judge_key = req.judge if req.judge is not None else profile.judge
    judge_spec: ModelSpec | None = None
    if judge_key != "none":
        try:
            judge_spec = config.model(judge_key)
        except KeyError:
            errors.append(("judge", f"unknown judge model {judge_key}"))
    contestants: list[ModelSpec] = []
    for key in deduped:
        try:
            contestants.append(config.model(key))
        except KeyError:
            errors.append(("models", f"unknown model {key}"))
    max_out = req.max_output_tokens or config.defaults.max_output_tokens
    if max_out < 1 or max_out > config.limits.max_output_tokens:
        errors.append(("max_output_tokens", "out of range"))
    temp = req.temperature if req.temperature is not None else config.defaults.temperature
    if not math.isfinite(temp) or temp < 0 or temp > 2:
        errors.append(("temperature", "out of range"))
    timeout_s = req.timeout_s if req.timeout_s is not None else config.defaults.timeout_s
    if timeout_s < config.limits.timeout_s_min or timeout_s > config.limits.timeout_s_max:
        errors.append(("timeout_s", "out of range"))
    seed = req.seed if req.seed is not None else secrets.randbelow(2**31)
    if seed < 0 or seed > 2**31 - 1:
        errors.append(("seed", "out of range"))
    if errors:
        raise RequestValidationError(errors)

    judge_settings = config.judge.model_copy(
        update={"allow_self_judging": req.allow_self_judging} if req.allow_self_judging is not None else {}
    )

    requests: dict[str, ProviderRequest] = {}
    for spec in contestants:
        temp_val = None if not spec.supports_temperature else temp
        requests[spec.key] = ProviderRequest(
            spec=spec,
            system=None,
            user=prompt,
            max_output_tokens=max_out,
            temperature=temp_val,
            timeout_s=timeout_s,
            request_tag=f"contestant/{spec.key}",
        )
    vendors: list[str] = []
    for spec in contestants:
        if spec.vendor not in vendors:
            vendors.append(spec.vendor)
    if judge_spec and judge_spec.vendor not in vendors:
        vendors.append(judge_spec.vendor)

    return ResolvedRun(
        prompt=prompt,
        contestants=contestants,
        judge=judge_spec,
        requests=requests,
        judge_settings=judge_settings,
        seed=seed,
        vendors_contacted=vendors,
    )
