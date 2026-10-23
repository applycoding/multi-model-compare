from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx2
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import SecretStr

from mmc.providers.base import (
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderUsage,
    StreamEnd,
    StreamEvent,
    TextDelta,
)


class AnthropicProvider(Provider):
    id = "anthropic"

    def __init__(
        self,
        api_key: SecretStr | None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        key = api_key.get_secret_value() if api_key else ""
        self._client = AsyncAnthropic(
            api_key=key,
            max_retries=0,
            http_client=http_client,
        )
        self._owns_client = http_client is None

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        kwargs: dict[str, Any] = {
            "model": req.spec.model_id,
            "max_tokens": req.max_output_tokens,
            "messages": [{"role": "user", "content": req.user}],
        }
        if req.system:
            kwargs["system"] = req.system
        if req.output_schema:
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": req.output_schema.json_schema,
                }
            }
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield TextDelta(text=text)
                final = await stream.get_final_message()
        except AuthenticationError as exc:
            raise ProviderError("auth", str(exc)) from exc
        except PermissionDeniedError as exc:
            raise ProviderError("auth", str(exc)) from exc
        except RateLimitError as exc:
            raise ProviderError("rate_limit", str(exc)) from exc
        except (BadRequestError, NotFoundError) as exc:
            raise ProviderError("bad_request", str(exc)) from exc
        except InternalServerError as exc:
            raise ProviderError("server", str(exc)) from exc
        except APITimeoutError as exc:
            raise ProviderError("timeout", str(exc)) from exc
        except APIConnectionError as exc:
            raise ProviderError("network", str(exc)) from exc
        except APIStatusError as exc:
            raise ProviderError("server", str(exc)) from exc

        stop = final.stop_reason
        if stop in ("end_turn", "stop_sequence"):
            outcome = "ok"
        elif stop in ("max_tokens", "pause_turn"):
            outcome = "incomplete"
        elif stop == "refusal":
            outcome = "refused"
        else:
            outcome = "ok"
        usage = ProviderUsage(
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            reasoning_tokens=None,
            total_tokens=final.usage.input_tokens + final.usage.output_tokens,
            raw={
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            },
        )
        rid = final._request_id if hasattr(final, "_request_id") else None  # noqa: SLF001
        yield StreamEnd(
            outcome=outcome,
            finish_reason=stop,
            request_id=rid,
            usage=usage,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()
