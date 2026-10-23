from __future__ import annotations

import asyncio

import pytest

from mmc.config.loader import load_app_config
from mmc.core.request import ResolvedRun
from mmc.core.supervisor import Busy, RunSupervisor
from mmc.service import CompareService


@pytest.mark.asyncio
async def test_busy_third_run(repo, registry, settings, redactor, stepping_clock, id_factory, estimator) -> None:
    config = load_app_config(None)
    service = CompareService(config, settings, registry, repo, stepping_clock, redactor, estimator, id_factory)
    sup = RunSupervisor(service, max_concurrent=2, grace_s=1)
    await sup.start()
    from mmc.config.schemas import MockOptions
    from mmc.providers.base import ProviderRequest

    stall_spec = config.model("mock:mock-claude").model_copy(
        update={"mock": MockOptions(behavior="stall", output_words=10)}
    )
    resolved = ResolvedRun(
        prompt="hi",
        contestants=[stall_spec],
        judge=None,
        requests={
            stall_spec.key: ProviderRequest(
                spec=stall_spec,
                system=None,
                user="hi",
                max_output_tokens=100,
                temperature=0.2,
                timeout_s=60,
                request_tag="t",
            )
        },
        judge_settings=config.judge,
        seed=1,
        vendors_contacted=["anthropic"],
    )

    t1 = asyncio.create_task(sup.submit(resolved))
    t2 = asyncio.create_task(sup.submit(resolved))
    await asyncio.sleep(0.05)
    with pytest.raises(Busy):
        await sup.submit(resolved)
    t1.cancel()
    t2.cancel()
    await asyncio.gather(t1, t2, return_exceptions=True)
    await sup.drain()
