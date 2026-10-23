from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from mmc.config.loader import load_app_config
from mmc.providers.base import ProviderRequest
from mmc.providers.google_provider import GoogleProvider


@pytest.mark.asyncio
async def test_ok_fixture_stream(fixtures_dir: Path) -> None:
    fixture = fixtures_dir / "recorded" / "google" / "ok.json"
    meta = fixtures_dir / "recorded" / "google" / "ok.meta.json"
    assert fixture.is_file()
    assert meta.is_file()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture.read_bytes(), headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    config = load_app_config(None)
    spec = config.model("google:gemini-3.8-flash")
    provider = GoogleProvider(SecretStr("AIza-test"), httpx_async_client=client)
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
