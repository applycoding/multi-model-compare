from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
import pytest
from pydantic import SecretStr

from mmc.config.loader import load_app_config
from mmc.judge.schema_builder import verdict_json_schema, verdict_model
from mmc.providers.anthropic_provider import AnthropicProvider
from mmc.providers.base import OutputSchema, ProviderRequest, StreamEnd, StreamEvent, TextDelta
from mmc.providers.google_provider import GoogleProvider
from mmc.providers.openai_provider import OpenAIProvider
from mmc.providers.xai_provider import XAIProvider


@pytest.fixture
def recorded_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "recorded"


def normalize_equivalent_ok(events: list[StreamEvent]) -> list[dict[str, str]]:
    """Cross-vendor ok fixtures should yield the same logical event shape."""
    normalized: list[dict[str, str]] = []
    for event in events:
        if isinstance(event, TextDelta):
            normalized.append({"kind": "delta"})
        elif isinstance(event, StreamEnd):
            normalized.append({"kind": "end", "outcome": event.outcome})
    return normalized


def normalize_stream_events(events: list[StreamEvent]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, TextDelta):
            normalized.append({"kind": "delta", "text": "SYNTHETIC_TEXT"})
        elif isinstance(event, StreamEnd):
            usage = None
            if event.usage:
                usage = {
                    "input_tokens": event.usage.input_tokens,
                    "output_tokens": event.usage.output_tokens,
                    "reasoning_tokens": event.usage.reasoning_tokens,
                    "billing_estimated": event.usage.billing_estimated,
                }
            normalized.append(
                {
                    "kind": "end",
                    "outcome": event.outcome,
                    "finish_reason": event.finish_reason,
                    "usage": usage,
                }
            )
    return normalized


def load_xai_fixture(fixtures_dir: Path, name: str) -> dict[str, Any]:
    path = fixtures_dir / "recorded" / "xai" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _ns(data: dict[str, Any]) -> Any:
    return json.loads(json.dumps(data), object_hook=lambda d: SimpleNamespace(**d))


class ReplayChat:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def stream(self) -> AsyncIterator[tuple[Any, Any]]:
        async def _iter() -> AsyncIterator[tuple[Any, Any]]:
            for item in self._payload.get("chunks", []):
                yield _ns(item["response"]), _ns(item["chunk"])

        return _iter()

    async def parse(self, model: type[Any]) -> tuple[Any, Any]:
        resp = _ns(self._payload["response"])
        return resp, None


def _judge_schema() -> OutputSchema:
    config = load_app_config(None)
    labels = ["A", "B"]
    criteria = [c.key for c in config.rubric.criteria]
    schema_dict = verdict_json_schema(labels, criteria)
    model_cls = verdict_model(labels, criteria, 600)
    return OutputSchema(name="judge_verdict", json_schema=schema_dict, model=model_cls)


def _provider_request(vendor: str, judge: bool = False) -> ProviderRequest:
    config = load_app_config(None)
    key = {
        "anthropic": "anthropic:claude-sonnet-5-5",
        "openai": "openai:gpt-6.1-sol",
        "google": "google:gemini-3.8-flash",
        "xai": "xai:grok-4.7",
    }[vendor]
    spec = config.model(key)
    out_schema = _judge_schema() if judge else None
    return ProviderRequest(
        spec=spec,
        system=None,
        user="contract fixture hello",
        max_output_tokens=128,
        temperature=0.2 if vendor != "anthropic" else None,
        timeout_s=30,
        request_tag="contract/fixture",
        output_schema=out_schema,
    )


async def stream_recorded_fixture(
    recorded_dir: Path,
    vendor: str,
    name: str,
    *,
    judge: bool = False,
) -> list[StreamEvent]:
    meta = recorded_dir / vendor / f"{name}.meta.json"
    assert meta.is_file(), f"missing meta for {vendor}/{name}"
    req = _provider_request(vendor, judge=judge)
    events: list[StreamEvent] = []

    if vendor == "anthropic":
        body = (recorded_dir / vendor / f"{name}.sse").read_bytes()

        async def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        prov = AnthropicProvider(SecretStr("sk-ant-test"), http_client=client)
    elif vendor == "openai":
        body = (recorded_dir / vendor / f"{name}.sse").read_bytes()

        async def oai_handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(oai_handler))
        prov = OpenAIProvider(SecretStr("sk-proj-test"), http_client=client)
    elif vendor == "google":
        path = recorded_dir / vendor / f"{name}.json"
        if name == "error":
            body = path.read_bytes()

            async def err_handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(500, content=body)

            client = httpx.AsyncClient(transport=httpx.MockTransport(err_handler))
        else:
            body = path.read_bytes()

            async def goog_handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, content=body)

            client = httpx.AsyncClient(transport=httpx.MockTransport(goog_handler))
        prov = GoogleProvider(SecretStr("AIza-test"), httpx_async_client=client)
    elif vendor == "xai":
        payload = json.loads((recorded_dir / vendor / f"{name}.json").read_text(encoding="utf-8"))
        config = load_app_config(None)
        prov = XAIProvider(
            SecretStr("xai-test"),
            config,
            chat_factory=lambda _req: ReplayChat(payload),
        )
        client = None
    else:
        raise ValueError(vendor)

    try:
        async for ev in prov.stream(req):
            events.append(ev)
    finally:
        await prov.aclose()
        if client is not None:
            await client.aclose()
    return events
