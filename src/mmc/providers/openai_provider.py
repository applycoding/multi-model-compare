from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx2
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
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


class OpenAIProvider(Provider):
    id = "openai"

    def __init__(
        self,
        api_key: SecretStr | None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        key = api_key.get_secret_value() if api_key else ""
        self._client = AsyncOpenAI(
            api_key=key,
            max_retries=0,
            http_client=http_client,
        )
        self._owns_client = http_client is None

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        kwargs: dict[str, Any] = {
            "model": req.spec.model_id,
            "input": req.user,
            "max_output_tokens": req.max_output_tokens,
            "store": False,
        }
        if req.system:
            kwargs["instructions"] = req.system
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        if req.output_schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": req.output_schema.name,
                    "schema": req.output_schema.json_schema,
                    "strict": True,
                }
            }
        output: list[str] = []
        refusal_parts: list[str] = []
        request_id: str | None = None
        outcome = "ok"
        finish_reason: str | None = None
        usage: ProviderUsage | None = None
        try:
            async with self._client.responses.stream(**kwargs) as stream:
                async for event in stream:
                    etype = event.type
                    if etype == "response.output_text.delta":
                        if event.delta:
                            output.append(event.delta)
                            yield TextDelta(text=event.delta)
                    elif etype == "response.refusal.delta":
                        if event.delta:
                            refusal_parts.append(event.delta)
                    elif etype == "response.completed":
                        finish_reason = "completed"
                        resp = event.response
                        request_id = getattr(resp, "id", None)
                        if resp.usage:
                            rt = None
                            if resp.usage.output_tokens_details:
                                rt = resp.usage.output_tokens_details.reasoning_tokens
                            usage = ProviderUsage(
                                input_tokens=resp.usage.input_tokens,
                                output_tokens=resp.usage.output_tokens,
                                reasoning_tokens=rt,
                                total_tokens=resp.usage.total_tokens,
                                raw={
                                    "input_tokens": resp.usage.input_tokens,
                                    "output_tokens": resp.usage.output_tokens,
                                },
                            )
                        if refusal_parts and not output:
                            outcome = "refused"
                    elif etype == "response.incomplete":
                        reason = event.response.incomplete_details.reason if event.response.incomplete_details else ""
                        if reason == "max_output_tokens":
                            outcome = "incomplete"
                        elif reason == "content_filter":
                            outcome = "blocked"
                        finish_reason = reason
                    elif etype in ("response.failed", "error"):
                        raise ProviderError("server", str(event))
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

        yield StreamEnd(
            outcome=outcome,
            finish_reason=finish_reason,
            request_id=request_id,
            usage=usage,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()
