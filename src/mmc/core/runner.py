from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date

from mmc.clock import Clock
from mmc.config.schemas import ModelSpec
from mmc.core.pricing import compute_cost
from mmc.core.results import AnswerResult, ErrorInfo, Timing
from mmc.core.tokens import TokenEstimator, resolve_usage
from mmc.providers.base import ProviderError, ProviderRequest, StreamEnd, TextDelta
from mmc.providers.registry import ProviderRegistry


def _resolved_params(req: ProviderRequest) -> dict[str, str]:
    temp = "omitted (unsupported)" if req.temperature is None else str(req.temperature)
    return {
        "temperature": temp,
        "max_output_tokens": str(req.max_output_tokens),
        "timeout_s": str(req.timeout_s),
    }


async def _run_one(
    spec: ModelSpec,
    req: ProviderRequest,
    registry: ProviderRegistry,
    clock: Clock,
    deadline: float,
    estimator: TokenEstimator,
    pricing_on: date,
    pricing_version: str,
    pricing_table: object,
) -> AnswerResult:
    from mmc.config.schemas import PricingTable

    assert isinstance(pricing_table, PricingTable)
    available, reason = registry.availability(spec)
    if not available:
        return AnswerResult(
            model=spec,
            status="skipped",
            skip_reason=reason,
            resolved_params=_resolved_params(req),
        )
    start = clock.perf()
    text_parts: list[str] = []
    ttft: float | None = None
    end_event: StreamEnd | None = None
    status: str = "ok"
    partial = False
    error_info: ErrorInfo | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    billing_estimated = False

    timeout_at = min(start + req.timeout_s, deadline)
    try:
        async with asyncio.timeout_at(timeout_at):
            provider = registry.get(spec.provider)
            stream = provider.stream(req)
            try:
                async for event in stream:
                    if isinstance(event, TextDelta):
                        if event.text:
                            if ttft is None:
                                ttft = (clock.perf() - start) * 1000
                            text_parts.append(event.text)
                    elif isinstance(event, StreamEnd):
                        end_event = event
                        finish_reason = event.finish_reason
                        request_id = event.request_id
                        if event.usage:
                            billing_estimated = event.usage.billing_estimated
            finally:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await close()
    except TimeoutError:
        status = "timeout"
        msg = "run deadline" if clock.perf() >= deadline - 0.001 else "timeout"
        error_info = ErrorInfo(kind="timeout", message=msg)
        partial = bool(text_parts)
    except ProviderError as exc:
        status = "error"
        error_info = ErrorInfo(kind=exc.kind, message=exc.message[:500])
        partial = bool(text_parts)
        request_id = exc.request_id
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        status = "error"
        error_info = ErrorInfo(kind="unknown", message=str(exc)[:500])
        partial = bool(text_parts)
    else:
        if end_event is None:
            status = "error"
            error_info = ErrorInfo(kind="protocol", message="stream ended without terminal event")
            partial = bool(text_parts)
        elif end_event.outcome == "ok":
            status = "ok"
        else:
            status = end_event.outcome
            partial = bool(text_parts)

    total_ms = (clock.perf() - start) * 1000
    text = "".join(text_parts)
    truncated = False
    if len(text) > 100_000:
        text = text[:100_000]
        truncated = True

    usage = resolve_usage(end_event, req, text, estimator)
    cost = compute_cost(spec.key, usage, billing_estimated, pricing_table, pricing_on)
    return AnswerResult(
        model=spec,
        status=status,
        text=text,
        partial=partial and status not in ("ok", "skipped"),
        truncated=truncated,
        finish_reason=finish_reason,
        provider_request_id=request_id,
        resolved_params=_resolved_params(req),
        usage=usage,
        timing=Timing(ttft_ms=ttft, total_ms=total_ms),
        cost=cost,
        error=error_info,
    )


async def run_contestants(
    specs: Sequence[ModelSpec],
    requests: dict[str, ProviderRequest],
    registry: ProviderRegistry,
    clock: Clock,
    deadline: float,
    estimator: TokenEstimator,
    pricing_on: date,
    pricing_table: object,
) -> list[AnswerResult]:
    results: list[AnswerResult | None] = [None] * len(specs)

    async def worker(idx: int, spec: ModelSpec) -> None:
        try:
            results[idx] = await _run_one(
                spec,
                requests[spec.key],
                registry,
                clock,
                deadline,
                estimator,
                pricing_on,
                "",
                pricing_table,
            )
        except asyncio.CancelledError:
            results[idx] = AnswerResult(
                model=spec,
                status="cancelled",
                error=ErrorInfo(kind="cancelled", message="cancelled"),
                resolved_params=_resolved_params(requests[spec.key]),
            )
            raise

    async with asyncio.TaskGroup() as tg:
        for i, spec in enumerate(specs):
            tg.create_task(worker(i, spec))

    return [r for r in results if r is not None]
