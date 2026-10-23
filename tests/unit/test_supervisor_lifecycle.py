from __future__ import annotations

import asyncio

import pytest

from mmc.config.loader import load_app_config
from mmc.config.schemas import MockOptions
from mmc.core.request import ResolvedRun
from mmc.core.supervisor import Busy, RunSupervisor
from mmc.providers.base import ProviderRequest
from mmc.service import CompareService


def _stall_resolved(config, prompt: str = "sup") -> ResolvedRun:
    stall_spec = config.model("mock:mock-claude").model_copy(
        update={"mock": MockOptions(behavior="stall", output_words=5)}
    )
    return ResolvedRun(
        prompt=prompt,
        contestants=[stall_spec],
        judge=None,
        requests={
            stall_spec.key: ProviderRequest(
                spec=stall_spec,
                system=None,
                user=prompt,
                max_output_tokens=100,
                temperature=0.2,
                timeout_s=60,
                request_tag="sup/test",
            )
        },
        judge_settings=config.judge,
        seed=1,
        vendors_contacted=["anthropic"],
    )


@pytest.mark.asyncio
async def test_drain_waits_for_in_flight(
    repo, registry, settings, redactor, stepping_clock, id_factory, estimator
) -> None:
    config = load_app_config(None)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, estimator, id_factory)
    sup = RunSupervisor(service, max_concurrent=2, grace_s=2)
    await sup.start()
    resolved = _stall_resolved(config)
    task = asyncio.create_task(sup.submit(resolved))
    await asyncio.sleep(0.05)
    assert sup.in_flight == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await sup.drain()
    assert sup.in_flight == 0


@pytest.mark.asyncio
async def test_grace_cancels_stuck_runs(
    repo, registry, settings, redactor, stepping_clock, id_factory, estimator
) -> None:
    config = load_app_config(None)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, estimator, id_factory)
    sup = RunSupervisor(service, max_concurrent=1, grace_s=0.1)
    await sup.start()
    resolved = _stall_resolved(config)
    _ = asyncio.create_task(sup.submit(resolved))
    await asyncio.sleep(0.05)
    await sup.drain()
    assert sup.in_flight == 0


@pytest.mark.asyncio
async def test_cancelled_vs_timeout_distinct(registry, stepping_clock, estimator) -> None:
    from datetime import date

    from mmc.config.schemas import MockOptions
    from mmc.core.runner import run_contestants
    from mmc.providers.base import ProviderRequest

    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(update={"mock": MockOptions(behavior="stall", output_words=5)})
    req = ProviderRequest(
        spec=spec,
        system=None,
        user="x",
        max_output_tokens=100,
        temperature=0.2,
        timeout_s=0.05,
        request_tag="t",
    )
    timeout_res = await run_contestants(
        [spec],
        {spec.key: req},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert timeout_res[0].status == "timeout"
    assert timeout_res[0].error and timeout_res[0].error.message == "timeout"

    task = asyncio.create_task(
        run_contestants(
            [spec],
            {spec.key: req.model_copy(update={"timeout_s": 60})},
            registry,
            stepping_clock,
            stepping_clock.perf() + 60,
            estimator,
            date(2026, 10, 23),
            config.pricing,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_busy_when_at_capacity(repo, registry, settings, redactor, stepping_clock, id_factory, estimator) -> None:
    config = load_app_config(None)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, estimator, id_factory)
    sup = RunSupervisor(service, max_concurrent=1, grace_s=1)
    await sup.start()
    resolved = _stall_resolved(config)
    t1 = asyncio.create_task(sup.submit(resolved))
    await asyncio.sleep(0.02)
    with pytest.raises(Busy):
        await sup.submit(resolved)
    t1.cancel()
    await asyncio.gather(t1, return_exceptions=True)
    await sup.drain()
