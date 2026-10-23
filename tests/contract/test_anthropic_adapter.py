from __future__ import annotations

from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from mmc.config.loader import load_app_config
from mmc.providers.anthropic_provider import AnthropicProvider
from mmc.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_ok_fixture_stream(fixtures_dir: Path) -> None:
    fixture = fixtures_dir / "recorded" / "anthropic" / "ok.sse"
    if not fixture.exists():
        pytest.skip("recorded fixture not present")

    async def handler(request: httpx2.Request) -> httpx2.Response:
        body = fixture.read_bytes()
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    transport = httpx2.MockTransport(handler)
    client = httpx2.AsyncClient(transport=transport)
    config = load_app_config(None)
    spec = config.model("anthropic:claude-sonnet-5-5")
    provider = AnthropicProvider(SecretStr("sk-ant-test"), http_client=client)
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
