from __future__ import annotations

import asyncio

import pytest

from mmc.config.loader import load_app_config
from mmc.config.schemas import MockOptions
from mmc.core.runner import run_contestants
from mmc.providers import mock as mock_mod
from mmc.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_gate_max_in_flight(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    n = 4
    specs = [config.model("mock:mock-gpt") for _ in range(n)]
    for i, spec in enumerate(specs):
        specs[i] = spec.model_copy(update={"mock": MockOptions(behavior="gate", output_words=10)})
    mock_mod.mock_gate_barrier = asyncio.Barrier(n + 1)
    mock_mod.mock_in_flight_counter = [0]
    requests = {
        s.key: ProviderRequest(
            spec=s,
            system=None,
            user="p",
            max_output_tokens=100,
            temperature=0.2,
            timeout_s=60,
            request_tag=f"t/{s.key}",
        )
        for s in specs
    }
    deadline = stepping_clock.perf() + 30
    task = asyncio.create_task(
        run_contestants(
            specs,
            requests,
            registry,
            stepping_clock,
            deadline,
            estimator,
            __import__("datetime").date(2026, 10, 23),
            config.pricing,
        )
    )
    await asyncio.sleep(0.05)
    assert max(mock_mod.mock_in_flight_counter) == n
    await mock_mod.mock_gate_barrier.wait()
    await task
    mock_mod.mock_gate_barrier = None


@pytest.mark.asyncio
async def test_skipped_missing_key(stepping_clock, estimator, app_config, monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    from mmc.settings import Settings

    settings = Settings.from_env()
    registry = __import__("mmc.providers.registry", fromlist=["ProviderRegistry"]).ProviderRegistry(
        app_config, settings
    )
    config = app_config
    spec = config.model("mock:mock-grok").model_copy(update={"requires_env": "XAI_API_KEY"})
    req = ProviderRequest(
        spec=spec,
        system=None,
        user="p",
        max_output_tokens=100,
        temperature=0.2,
        timeout_s=60,
        request_tag="t",
    )
    results = await run_contestants(
        [spec],
        {spec.key: req},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        __import__("datetime").date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].status == "skipped"
