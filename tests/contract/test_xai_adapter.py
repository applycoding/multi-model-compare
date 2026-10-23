from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from mmc.config.loader import load_app_config
from mmc.core.pricing import compute_cost
from mmc.core.tokens import TokenEstimator, resolve_usage
from mmc.providers.base import ProviderRequest, StreamEnd
from mmc.providers.xai_provider import XAIProvider
from tests.contract.conftest import load_xai_fixture


def _ns(data: dict[str, Any]) -> Any:
    return json.loads(json.dumps(data), object_hook=lambda d: SimpleNamespace(**d))


class _ReplayChat:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def stream(self) -> AsyncIterator[tuple[Any, Any]]:
        async def _iter() -> AsyncIterator[tuple[Any, Any]]:
            for item in self._payload["chunks"]:
                yield _ns(item["response"]), _ns(item["chunk"])

        return _iter()

    async def parse(self, model: type[Any]) -> tuple[Any, Any]:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_ok_fixture_from_file(fixtures_dir: Path) -> None:
    meta = fixtures_dir / "recorded" / "xai" / "ok.meta.json"
    assert meta.is_file()
    payload = load_xai_fixture(fixtures_dir, "ok")
    config = load_app_config(None)
    spec = config.model("xai:grok-4.7")
    provider = XAIProvider(
        SecretStr("xai-test"),
        config,
        chat_factory=lambda _req: _ReplayChat(payload),
    )
    req = ProviderRequest(
        spec=spec,
        system=None,
        user="hello",
        max_output_tokens=100,
        temperature=None,
        timeout_s=30,
        request_tag="t",
    )
    events = []
    async for ev in provider.stream(req):
        events.append(ev)
    assert events[-1].kind == "end"
    await provider.aclose()


@pytest.mark.asyncio
async def test_reasoning_fixture_cost_estimated(fixtures_dir: Path) -> None:
    payload = load_xai_fixture(fixtures_dir, "reasoning")
    assert payload.get("reasoning_tokens_additive") is False
    config = load_app_config(None)
    spec = config.model("xai:grok-4.7")
    provider = XAIProvider(
        SecretStr("xai-test"),
        config,
        chat_factory=lambda _req: _ReplayChat(payload),
    )
    req = ProviderRequest(
        spec=spec,
        system=None,
        user="hello",
        max_output_tokens=100,
        temperature=None,
        timeout_s=30,
        request_tag="t",
    )
    end: StreamEnd | None = None
    async for ev in provider.stream(req):
        if ev.kind == "end":
            end = ev
    assert end and end.usage
    assert end.usage.billing_estimated is True
    usage = resolve_usage(end, req, "text", TokenEstimator("chars"))
    cost = compute_cost(spec.key, usage, end.usage.billing_estimated, config.pricing, date(2026, 10, 23))
    assert cost.status == "estimated"
    await provider.aclose()
