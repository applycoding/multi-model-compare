from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from mmc.clock import Clock
from mmc.config.schemas import JudgeSettings, ModelSpec, PricingTable, Rubric
from mmc.core.pricing import compute_cost
from mmc.core.results import AnswerResult, Timing
from mmc.core.tokens import TokenEstimator, resolve_usage
from mmc.judge.anonymise import assign_labels, redact_identity
from mmc.judge.parser import VerdictError, parse_verdict
from mmc.judge.payload import build_judge_request, build_retry_request
from mmc.judge.schema_builder import verdict_json_schema, verdict_model
from mmc.judge.schemas import AnswerScores, CriterionScore, JudgeAttempt, JudgeOutcome
from mmc.providers.base import OutputSchema, ProviderError, StreamEnd, TextDelta
from mmc.providers.registry import ProviderRegistry


async def run_judge(
    prompt: str,
    answers: Sequence[AnswerResult],
    judge_spec: ModelSpec,
    settings: JudgeSettings,
    rubric: Rubric,
    seed: int,
    run_id: str,
    registry: ProviderRegistry,
    clock: Clock,
    deadline: float,
    estimator: TokenEstimator,
    pricing: PricingTable,
    on: date,
) -> JudgeOutcome:
    excluded: dict[str, str] = {}
    eligible: list[AnswerResult] = []
    for ans in answers:
        if ans.status not in ("ok",) and not (settings.include_incomplete and ans.status == "incomplete"):
            excluded[ans.model.key] = f"status={ans.status}"
            continue
        if ans.model.vendor == judge_spec.vendor and not settings.allow_self_judging:
            excluded[ans.model.key] = "same vendor as judge"
            continue
        eligible.append(ans)

    available, reason = registry.availability(judge_spec)
    if not eligible:
        return JudgeOutcome(
            status="skipped_no_answers",
            judge=judge_spec,
            seed=seed,
            label_map={},
            scores={},
            excluded=excluded,
            attempts=[],
            resolved_params={},
        )
    if not available:
        return JudgeOutcome(
            status="unavailable",
            judge=judge_spec,
            seed=seed,
            label_map={},
            scores={},
            excluded=excluded,
            attempts=[],
            resolved_params={"skip": reason or ""},
        )

    keys = [a.model.key for a in eligible]
    label_to_key = assign_labels(keys, seed)
    label_map = {lbl: label_to_key[lbl] for lbl in sorted(label_to_key)}
    model_ids = [a.model.model_id for a in eligible]
    labelled = {
        lbl: redact_identity(ans.text, settings.redact_terms, model_ids)
        for lbl, key in label_map.items()
        for ans in eligible
        if ans.model.key == key
    }
    labels = sorted(label_map.keys())
    criteria = [c.key for c in rubric.criteria]
    schema_dict = verdict_json_schema(labels, criteria)
    model_cls = verdict_model(labels, criteria, settings.rationale_max_chars)
    out_schema = OutputSchema(name="judge_verdict", json_schema=schema_dict, model=model_cls)
    budget = min(
        settings.output_tokens_cap,
        settings.output_tokens_base + len(labels) * len(criteria) * settings.output_tokens_per_cell,
    )
    base_req = build_judge_request(
        prompt,
        labelled,
        rubric,
        judge_spec,
        settings,
        f"{run_id}/judge/0",
        budget,
        out_schema,
    )
    attempts: list[JudgeAttempt] = []
    req = base_req
    max_attempts = settings.max_retries + 1
    parsed: dict[str, dict[str, CriterionScore]] | None = None
    status = "ok"

    for attempt_no in range(1, max_attempts + 1):
        if clock.perf() >= deadline:
            status = "timeout"
            break
        start = clock.perf()
        raw_parts: list[str] = []
        end_event: StreamEnd | None = None
        ttft: float | None = None
        try:
            async with asyncio.timeout_at(min(start + settings.timeout_s, deadline)):
                stream = registry.get(judge_spec.provider).stream(req)
                try:
                    async for event in stream:
                        if isinstance(event, TextDelta):
                            if event.text:
                                if ttft is None:
                                    ttft = (clock.perf() - start) * 1000
                                raw_parts.append(event.text)
                        elif isinstance(event, StreamEnd):
                            end_event = event
                finally:
                    close = getattr(stream, "aclose", None)
                    if close is not None:
                        await close()
        except TimeoutError:
            status = "timeout"
            attempts.append(
                JudgeAttempt(
                    attempt_no=attempt_no,
                    raw_output="".join(raw_parts),
                    valid=False,
                    error="timeout",
                    outcome=None,
                    finish_reason=None,
                    provider_request_id=None,
                    usage=None,
                    timing=Timing(ttft_ms=ttft, total_ms=(clock.perf() - start) * 1000),
                    cost=None,
                )
            )
            break
        except ProviderError as exc:
            status = "error"
            attempts.append(
                JudgeAttempt(
                    attempt_no=attempt_no,
                    raw_output="".join(raw_parts),
                    valid=False,
                    error=exc.message,
                    outcome=None,
                    finish_reason=None,
                    provider_request_id=exc.request_id,
                    usage=None,
                    timing=Timing(ttft_ms=ttft, total_ms=(clock.perf() - start) * 1000),
                    cost=None,
                )
            )
            break

        raw = "".join(raw_parts)
        total_ms = (clock.perf() - start) * 1000
        usage = resolve_usage(end_event, req, raw, estimator)
        billing_est = bool(end_event and end_event.usage and end_event.usage.billing_estimated)
        cost = compute_cost(judge_spec.key, usage, billing_est, pricing, on)
        if end_event and end_event.outcome in ("refused", "blocked"):
            status = "error"
            attempts.append(
                JudgeAttempt(
                    attempt_no=attempt_no,
                    raw_output=raw,
                    valid=False,
                    error=end_event.outcome,
                    outcome=end_event.outcome,
                    finish_reason=end_event.finish_reason,
                    provider_request_id=end_event.request_id,
                    usage=usage,
                    timing=Timing(ttft_ms=ttft, total_ms=total_ms),
                    cost=cost,
                )
            )
            break
        try:
            parsed_scores = parse_verdict(raw, set(labels), criteria, settings.rationale_max_chars)
            parsed = parsed_scores
            attempts.append(
                JudgeAttempt(
                    attempt_no=attempt_no,
                    raw_output=raw,
                    valid=True,
                    error=None,
                    outcome=end_event.outcome if end_event else None,
                    finish_reason=end_event.finish_reason if end_event else None,
                    provider_request_id=end_event.request_id if end_event else None,
                    usage=usage,
                    timing=Timing(ttft_ms=ttft, total_ms=total_ms),
                    cost=cost,
                )
            )
            break
        except VerdictError as exc:
            attempts.append(
                JudgeAttempt(
                    attempt_no=attempt_no,
                    raw_output=raw,
                    valid=False,
                    error=str(exc),
                    outcome=end_event.outcome if end_event else None,
                    finish_reason=end_event.finish_reason if end_event else None,
                    provider_request_id=end_event.request_id if end_event else None,
                    usage=usage,
                    timing=Timing(ttft_ms=ttft, total_ms=total_ms),
                    cost=cost,
                )
            )
            if attempt_no >= max_attempts:
                status = "invalid_output"
                break
            req = build_retry_request(base_req, exc, attempt_no)

    scores: dict[str, AnswerScores] = {}
    if parsed and status == "ok":
        weights = {c.key: c.weight for c in rubric.criteria}
        for lbl, crit_scores in parsed.items():
            key = label_map[lbl]
            overall = Decimal(0)
            for ck, sc in crit_scores.items():
                overall += weights[ck] * Decimal(sc.score)
            overall = overall.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self_judged = (
                settings.allow_self_judging
                and next(a for a in eligible if a.model.key == key).model.vendor == judge_spec.vendor
            )
            scores[key] = AnswerScores(
                criteria=crit_scores,
                overall=overall,
                self_judged=self_judged,
            )

    temp_param = "omitted (unsupported)" if not judge_spec.supports_temperature else str(settings.temperature)
    return JudgeOutcome(
        status=status if parsed else status,
        judge=judge_spec,
        seed=seed,
        label_map=label_map,
        scores=scores,
        excluded=excluded,
        attempts=attempts,
        resolved_params={"temperature": temp_param},
    )
