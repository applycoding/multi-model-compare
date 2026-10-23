from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from mmc.config.loader import load_app_config
from mmc.providers.base import ProviderRequest
from mmc.providers.xai_provider import XAIProvider


class _FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self) -> None:
        self.id = "resp_synthetic_xai"
        self.finish_reason = "stop"
        self.usage = SimpleNamespace(
            prompt_tokens=4,
            completion_tokens=6,
            reasoning_tokens=0,
            total_tokens=10,
        )


class _FakeChat:
    async def stream(self) -> AsyncIterator[tuple[Any, Any]]:
        async def _iter() -> AsyncIterator[tuple[Any, Any]]:
            yield _FakeResponse(), _FakeChunk("Hello from synthetic xAI fixture.")

        return _iter()

    async def parse(self, model: type[Any]) -> tuple[Any, Any]:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_ok_fixture_stream(fixtures_dir: Path) -> None:
    meta = fixtures_dir / "recorded" / "xai" / "ok.meta.json"
    assert meta.is_file()

    config = load_app_config(None)
    spec = config.model("xai:grok-4.7")
    provider = XAIProvider(
        SecretStr("xai-test"),
        config,
        chat_factory=lambda _req: _FakeChat(),
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
    assert events[0].kind == "delta"
    assert events[-1].kind == "end"
    await provider.aclose()
