from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from pydantic import SecretStr
from xai_sdk import AsyncClient

from mmc.config.schemas import AppConfig
from mmc.providers.base import (
    OutputSchema,
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderUsage,
    StreamEnd,
    StreamEvent,
    TextDelta,
)


class ChatLike(Protocol):
    async def stream(self) -> AsyncIterator[tuple[Any, Any]]: ...

    async def parse(self, model: type[Any]) -> tuple[Any, Any]: ...


_FINISH_MAP = {
    "stop": "ok",
    "max_tokens": "incomplete",
    "content_filter": "blocked",
}


class XAIProvider(Provider):
    id = "xai"

    def __init__(
        self,
        api_key: SecretStr | None,
        config: AppConfig,
        chat_factory: Callable[[ProviderRequest], ChatLike] | None = None,
    ) -> None:
        key = api_key.get_secret_value() if api_key else ""
        self._client = AsyncClient(
            api_key=key,
            timeout=120,
            channel_options=[("grpc.enable_retries", 0)],
        )
        self._config = config
        self._chat_factory = chat_factory

    def _create_chat(self, req: ProviderRequest) -> ChatLike:
        if self._chat_factory:
            return self._chat_factory(req)
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.user})
        kwargs: dict[str, Any] = {
            "model": req.spec.model_id,
            "messages": messages,
            "max_tokens": req.max_output_tokens,
        }
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        return self._client.chat.create(**kwargs)

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        chat = self._create_chat(req)
        if req.output_schema:
            assert isinstance(req.output_schema, OutputSchema)
            try:
                response, _ = await chat.parse(req.output_schema.model)
            except Exception as exc:
                raise _map_grpc_error(exc) from exc
            text = getattr(response, "content", "") or ""
            if text:
                yield TextDelta(text=text)
            usage = _usage_from_response(response, self._config)
            reason = getattr(response, "finish_reason", "stop")
            outcome = _FINISH_MAP.get(str(reason).lower())
            if outcome is None:
                raise ProviderError("unknown", str(reason))
            yield StreamEnd(
                outcome=outcome,
                finish_reason=str(reason),
                request_id=getattr(response, "id", None),
                usage=usage,
            )
            return

        final = None
        try:
            stream_iter = await chat.stream()
            async for response, chunk in stream_iter:
                final = response
                content = getattr(chunk, "content", None) or ""
                if content:
                    yield TextDelta(text=content)
        except Exception as exc:
            raise _map_grpc_error(exc) from exc
        if final is None:
            raise ProviderError("protocol", "empty stream")
        reason = getattr(final, "finish_reason", "stop")
        outcome = _FINISH_MAP.get(str(reason).lower())
        if outcome is None:
            raise ProviderError("unknown", str(reason))
        yield StreamEnd(
            outcome=outcome,
            finish_reason=str(reason),
            request_id=getattr(final, "id", None),
            usage=_usage_from_response(final, self._config),
        )

    async def aclose(self) -> None:
        await self._client.close()


def _usage_from_response(response: Any, config: AppConfig) -> ProviderUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    reasoning = getattr(usage, "reasoning_tokens", None)
    total = getattr(usage, "total_tokens", None)
    additive = config.providers["xai"].reasoning_tokens_additive
    billable = completion
    billing_estimated = False
    if completion is not None:
        if additive and reasoning is not None:
            billable = completion + reasoning
        else:
            billing_estimated = reasoning is not None and reasoning > 0
    return ProviderUsage(
        input_tokens=prompt,
        output_tokens=billable,
        reasoning_tokens=reasoning,
        total_tokens=total,
        raw={
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
            "total_tokens": total,
        },
        billing_estimated=billing_estimated,
    )


def _map_grpc_error(exc: Exception) -> ProviderError:
    import grpc

    if isinstance(exc, grpc.aio.AioRpcError):
        code = exc.code()
        if code in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            return ProviderError("auth", exc.details() or "auth")
        if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
            return ProviderError("rate_limit", exc.details() or "rate limit")
        if code in (grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.NOT_FOUND):
            return ProviderError("bad_request", exc.details() or "bad request")
        if code == grpc.StatusCode.UNAVAILABLE:
            return ProviderError("network", exc.details() or "unavailable")
        if code == grpc.StatusCode.DEADLINE_EXCEEDED:
            return ProviderError("timeout", exc.details() or "timeout")
        return ProviderError("server", exc.details() or "server")
    return ProviderError("unknown", str(exc))
