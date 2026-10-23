from __future__ import annotations

import asyncio
from datetime import date

import pytest

from mmc.config.loader import load_app_config
from mmc.config.schemas import MockOptions
from mmc.core.runner import run_contestants
from mmc.providers import mock as mock_mod
from mmc.providers.base import ProviderRequest


def _req(spec, timeout_s: float = 60.0) -> ProviderRequest:
    return ProviderRequest(
        spec=spec,
        system=None,
        user="lifecycle prompt",
        max_output_tokens=100,
        temperature=0.2,
        timeout_s=timeout_s,
        request_tag="lifecycle/test",
    )


@pytest.fixture(autouse=True)
def _clear_aclose_log() -> None:
    mock_mod.mock_stream_aclose_log.clear()


@pytest.mark.asyncio
async def test_aclose_on_success(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec)},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].status == "ok"
    assert mock_mod.mock_stream_aclose_log == ["ok:lifecycle/test"]


@pytest.mark.asyncio
async def test_aclose_on_error(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(
        update={"mock": MockOptions(behavior="error", error_kind="server", error_message="boom")}
    )
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec)},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].status == "error"
    assert mock_mod.mock_stream_aclose_log == ["error:lifecycle/test"]


@pytest.mark.asyncio
async def test_aclose_on_timeout(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(update={"mock": MockOptions(behavior="stall", output_words=10)})
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec, timeout_s=0.05)},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].status == "timeout"
    assert mock_mod.mock_stream_aclose_log == ["stall:lifecycle/test"]


@pytest.mark.asyncio
async def test_aclose_on_cancel(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(update={"mock": MockOptions(behavior="stall", output_words=10)})
    task = asyncio.create_task(
        run_contestants(
            [spec],
            {spec.key: _req(spec, timeout_s=60)},
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
    assert mock_mod.mock_stream_aclose_log == ["stall:lifecycle/test"]


@pytest.mark.asyncio
async def test_ttft_none_when_no_nonempty_delta(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(update={"mock": MockOptions(behavior="empty", output_words=0)})
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec)},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].timing is not None
    assert results[0].timing.ttft_ms is None


@pytest.mark.asyncio
async def test_ttft_set_when_delta_emitted(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec)},
        registry,
        stepping_clock,
        stepping_clock.perf() + 60,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].timing is not None
    assert results[0].timing.ttft_ms is not None
    assert results[0].timing.ttft_ms <= results[0].timing.total_ms


@pytest.mark.asyncio
async def test_run_deadline_message(registry, stepping_clock, estimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(update={"mock": MockOptions(behavior="stall", output_words=10)})
    results = await run_contestants(
        [spec],
        {spec.key: _req(spec, timeout_s=60)},
        registry,
        stepping_clock,
        stepping_clock.perf() - 1,
        estimator,
        date(2026, 10, 23),
        config.pricing,
    )
    assert results[0].status == "timeout"
    assert results[0].error is not None
    assert results[0].error.message == "run deadline"
