from __future__ import annotations

import pytest

from mmc.config.loader import load_app_config
from mmc.providers.base import ProviderRequest, StreamEnd, TextDelta
from mmc.providers.mock import MockProvider


async def _collect(req: ProviderRequest) -> list[object]:
    p = MockProvider(load_app_config(None).rubric)
    events = []
    async for ev in p.stream(req):
        events.append(ev)
    return events


def _req(behavior: str, **mock_kw: object) -> ProviderRequest:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt").model_copy(
        update={"mock": config.model("mock:mock-gpt").mock.model_copy(update={"behavior": behavior, **mock_kw})}  # type: ignore[union-attr]
    )
    return ProviderRequest(
        spec=spec,
        system=None,
        user="test prompt",
        max_output_tokens=100,
        temperature=0.2,
        timeout_s=60,
        request_tag="t",
    )


@pytest.mark.asyncio
async def test_deterministic_text() -> None:
    a = await _collect(_req("ok"))
    b = await _collect(_req("ok"))
    text_a = "".join(e.text for e in a if isinstance(e, TextDelta))
    text_b = "".join(e.text for e in b if isinstance(e, TextDelta))
    assert text_a == text_b
    assert len(text_a.split()) == 60


@pytest.mark.asyncio
async def test_refused_outcome() -> None:
    events = await _collect(_req("refused"))
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].outcome == "refused"
