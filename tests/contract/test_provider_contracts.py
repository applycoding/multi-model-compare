from __future__ import annotations

import asyncio
import json
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
from mmc.providers.base import OutputSchema, ProviderError, ProviderRequest
from mmc.providers.google_provider import GoogleProvider
from mmc.providers.openai_provider import OpenAIProvider
from mmc.providers.xai_provider import XAIProvider
from tests.contract.conftest import ReplayChat, load_xai_fixture, normalize_equivalent_ok


def _provider_request(vendor: str, judge: bool = False) -> ProviderRequest:
    config = load_app_config(None)
    key = {
        "anthropic": "anthropic:claude-sonnet-5-5",
        "openai": "openai:gpt-6.1-sol",
        "google": "google:gemini-3.8-flash",
        "xai": "xai:grok-4.7",
    }[vendor]
    spec = config.model(key)
    out_schema = None
    if judge:
        labels = ["A", "B"]
        criteria = ["correctness"]
        schema_dict = verdict_json_schema(labels, criteria)
        model_cls = verdict_model(labels, criteria, 600)
        out_schema = OutputSchema(name="judge_verdict", json_schema=schema_dict, model=model_cls)
    return ProviderRequest(
        spec=spec,
        system=None,
        user="contract hello",
        max_output_tokens=128,
        temperature=0.2 if vendor != "anthropic" else None,
        timeout_s=30,
        request_tag="contract/test",
        output_schema=out_schema,
    )


@pytest.mark.asyncio
async def test_cross_vendor_ok_normalized_equivalent(recorded_dir: Path) -> None:
    anthropic_body = (recorded_dir / "anthropic" / "ok.sse").read_bytes()
    openai_body = (recorded_dir / "openai" / "ok.sse").read_bytes()
    google_body = (recorded_dir / "google" / "ok.json").read_bytes()
    xai_payload = load_xai_fixture(recorded_dir.parent, "ok")

    async def anth_handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=anthropic_body, headers={"content-type": "text/event-stream"})

    async def oai_handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=openai_body, headers={"content-type": "text/event-stream"})

    async def goog_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=google_body, headers={"content-type": "application/json"})

    config = load_app_config(None)
    anth = AnthropicProvider(
        SecretStr("sk-ant-test"),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(anth_handler)),
    )
    oai = OpenAIProvider(
        SecretStr("sk-proj-test"),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(oai_handler)),
    )
    goog = GoogleProvider(
        SecretStr("AIza-test"),
        httpx_async_client=httpx.AsyncClient(transport=httpx.MockTransport(goog_handler)),
    )
    xai = XAIProvider(
        SecretStr("xai-test"),
        config,
        chat_factory=lambda _req: ReplayChat(xai_payload),
    )
    providers = [("anthropic", anth), ("openai", oai), ("google", goog), ("xai", xai)]
    normalized_sets = []
    for vendor, prov in providers:
        events: list[Any] = []
        async for ev in prov.stream(_provider_request(vendor)):
            events.append(ev)
        normalized_sets.append(normalize_equivalent_ok(events))
        await prov.aclose()
    assert normalized_sets[0] == normalized_sets[1]
    for norm in normalized_sets:
        assert norm[-1]["kind"] == "end"
        assert norm[-1]["outcome"] == "ok"
        assert any(item["kind"] == "delta" for item in norm)


@pytest.mark.asyncio
async def test_anthropic_request_shape(recorded_dir: Path) -> None:
    captured: list[httpx2.Request] = []
    body = (recorded_dir / "anthropic" / "ok.sse").read_bytes()

    async def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    prov = AnthropicProvider(SecretStr("sk-ant-test"), http_client=client)
    async for _ in prov.stream(_provider_request("anthropic")):
        pass
    await prov.aclose()
    assert captured
    req = captured[0]
    assert req.headers.get("anthropic-version") == "2026-10-21"
    assert req.headers.get("authorization", "").startswith("Bearer ")
    payload = json.loads(req.content.decode())
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert "tool_choice" not in payload


@pytest.mark.asyncio
async def test_anthropic_judge_output_config(recorded_dir: Path) -> None:
    captured: list[httpx2.Request] = []
    body = (recorded_dir / "anthropic" / "judge.sse").read_bytes()

    async def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    prov = AnthropicProvider(SecretStr("sk-ant-test"), http_client=client)
    async for _ in prov.stream(_provider_request("anthropic", judge=True)):
        pass
    await prov.aclose()
    payload = json.loads(captured[0].content.decode())
    assert "output_config" in payload
    assert payload["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_openai_store_false_and_no_tool_choice(recorded_dir: Path) -> None:
    captured: list[httpx2.Request] = []
    body = (recorded_dir / "openai" / "ok.sse").read_bytes()

    async def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    prov = OpenAIProvider(SecretStr("sk-proj-test"), http_client=client)
    async for _ in prov.stream(_provider_request("openai")):
        pass
    await prov.aclose()
    payload = json.loads(captured[0].content.decode())
    assert payload.get("store") is False
    assert "tool_choice" not in payload


@pytest.mark.asyncio
async def test_openai_judge_strict_format(recorded_dir: Path) -> None:
    captured: list[httpx2.Request] = []
    body = (recorded_dir / "openai" / "ok.sse").read_bytes()

    async def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    prov = OpenAIProvider(SecretStr("sk-proj-test"), http_client=client)
    async for _ in prov.stream(_provider_request("openai", judge=True)):
        pass
    await prov.aclose()
    payload = json.loads(captured[0].content.decode())
    assert payload["text"]["format"]["strict"] is True


@pytest.mark.asyncio
async def test_google_request_has_no_tool_choice(recorded_dir: Path) -> None:
    body = (recorded_dir / "google" / "ok.json").read_bytes()
    captured: list[httpx.Request] = []

    async def goog_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(goog_handler))
    prov = GoogleProvider(SecretStr("AIza-test"), httpx_async_client=client)
    async for _ in prov.stream(_provider_request("google")):
        pass
    await prov.aclose()
    await client.aclose()
    assert captured
    payload = json.loads(captured[0].content.decode("utf-8"))
    assert "tool_choice" not in payload
    assert "tools" not in payload
    assert "toolConfig" not in payload


@pytest.mark.asyncio
async def test_xai_chat_create_has_no_tool_choice(recorded_dir: Path) -> None:
    payload = load_xai_fixture(recorded_dir.parent, "ok")
    create_kwargs: list[dict[str, Any]] = []

    class _ChatStub:
        def create(self, **kwargs: Any) -> ReplayChat:
            create_kwargs.append(kwargs)
            return ReplayChat(payload)

    config = load_app_config(None)

    async def _noop_close() -> None:
        return None

    prov = XAIProvider(SecretStr("xai-test"), config)
    prov._client = SimpleNamespace(chat=_ChatStub(), close=_noop_close)
    async for _ in prov.stream(_provider_request("xai")):
        pass
    await prov.aclose()
    assert len(create_kwargs) == 1
    assert "tools" not in create_kwargs[0]
    assert "tool_choice" not in create_kwargs[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("grpc_status", "error_kind"),
    [
        ("INTERNAL", "server"),
        ("UNAUTHENTICATED", "auth"),
        ("RESOURCE_EXHAUSTED", "rate_limit"),
    ],
)
async def test_xai_grpc_error_mapping(grpc_status: str, error_kind: str) -> None:
    payload = {"grpc_status": grpc_status, "chunks": []}
    config = load_app_config(None)
    prov = XAIProvider(SecretStr("xai-test"), config, chat_factory=lambda _: ReplayChat(payload))
    with pytest.raises(ProviderError) as excinfo:
        async for _ in prov.stream(_provider_request("xai")):
            pass
    await prov.aclose()
    assert excinfo.value.kind == error_kind


@pytest.mark.asyncio
async def test_google_timeout_ms_and_aclose(recorded_dir: Path) -> None:
    body = (recorded_dir / "google" / "ok.json").read_bytes()

    async def goog_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(goog_handler))
    prov = GoogleProvider(SecretStr("AIza-test"), httpx_async_client=client)
    req = _provider_request("google")
    async for _ in prov.stream(req):
        pass
    await prov.aclose()
    await client.aclose()
    assert client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limit"), (500, "server")])
async def test_http_errors_map(status: int, kind: str) -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": "x"})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    prov = OpenAIProvider(SecretStr("sk-proj-test"), http_client=client)
    with pytest.raises(ProviderError) as exc:
        async for _ in prov.stream(_provider_request("openai")):
            pass
    assert exc.value.kind == kind
    await prov.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("vendor", ["anthropic", "openai", "google"])
async def test_hung_stream_mock_transport_times_out(vendor: str, recorded_dir: Path) -> None:
    hang = asyncio.Event()

    async def hang_handler_httpx2(request: httpx2.Request) -> httpx2.Response:
        await asyncio.wait_for(hang.wait(), timeout=30)
        return httpx2.Response(200, content=b"")

    async def hang_handler_httpx(request: httpx.Request) -> httpx.Response:
        await asyncio.wait_for(hang.wait(), timeout=30)
        return httpx.Response(200, content=b"")

    req = _provider_request(vendor)

    async def consume() -> None:
        if vendor == "anthropic":
            client = httpx2.AsyncClient(transport=httpx2.MockTransport(hang_handler_httpx2))
            prov = AnthropicProvider(SecretStr("sk-ant-test"), http_client=client)
        elif vendor == "openai":
            client = httpx2.AsyncClient(transport=httpx2.MockTransport(hang_handler_httpx2))
            prov = OpenAIProvider(SecretStr("sk-proj-test"), http_client=client)
        else:
            client = httpx.AsyncClient(transport=httpx.MockTransport(hang_handler_httpx))
            prov = GoogleProvider(SecretStr("AIza-test"), httpx_async_client=client)
        try:
            async for _ in prov.stream(req):
                pass
        finally:
            await prov.aclose()
            await client.aclose()

    with pytest.raises((asyncio.TimeoutError, ProviderError)):
        await asyncio.wait_for(consume(), timeout=2.0)
