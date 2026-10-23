from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from google import genai
from google.genai import errors
from google.genai.types import GenerateContentConfig, HttpOptions, HttpRetryOptions
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


class GoogleProvider(Provider):
    id = "google"

    def __init__(
        self,
        api_key: SecretStr | None,
        httpx_async_client: httpx.AsyncClient | None = None,
    ) -> None:
        key = api_key.get_secret_value() if api_key else ""
        self._client = genai.Client(
            api_key=key,
            http_options=HttpOptions(
                retry_options=HttpRetryOptions(attempts=1),
                httpx_async_client=httpx_async_client,
            ),
        )
        self._owns_client = httpx_async_client is None

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        config_kwargs: dict[str, Any] = {
            "max_output_tokens": req.max_output_tokens,
            "http_options": HttpOptions(timeout=int(req.timeout_s * 1000)),
        }
        if req.system:
            config_kwargs["system_instruction"] = req.system
        if req.temperature is not None:
            config_kwargs["temperature"] = req.temperature
        if req.output_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = req.output_schema.json_schema
        config = GenerateContentConfig(**config_kwargs)
        usage_meta = None
        finish_reason: str | None = None
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=req.spec.model_id,
                contents=req.user,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    yield TextDelta(text=chunk.text)
                if chunk.usage_metadata:
                    usage_meta = chunk.usage_metadata
                if chunk.candidates and chunk.candidates[0].finish_reason:
                    finish_reason = str(chunk.candidates[0].finish_reason)
        except errors.ClientError as exc:
            code = getattr(exc, "code", None) or 0
            if code in (401, 403):
                raise ProviderError("auth", str(exc)) from exc
            if code == 429:
                raise ProviderError("rate_limit", str(exc)) from exc
            if 400 <= int(code) < 500:
                raise ProviderError("bad_request", str(exc)) from exc
            raise ProviderError("server", str(exc)) from exc
        except errors.ServerError as exc:
            raise ProviderError("server", str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", str(exc)) from exc
        except httpx.TransportError as exc:
            raise ProviderError("network", str(exc)) from exc

        if not finish_reason:
            raise ProviderError("protocol", "missing finish reason")
        blocked = {
            "SAFETY",
            "RECITATION",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "IMAGE_SAFETY",
        }
        if finish_reason in blocked:
            outcome = "blocked"
        elif finish_reason == "STOP":
            outcome = "ok"
        elif finish_reason == "MAX_TOKENS":
            outcome = "incomplete"
        else:
            raise ProviderError("unknown", finish_reason)

        usage = None
        if usage_meta:
            cand = usage_meta.candidates_token_count
            thoughts = usage_meta.thoughts_token_count
            out_tok = None
            if cand is not None or thoughts is not None:
                out_tok = (cand or 0) + (thoughts or 0)
            usage = ProviderUsage(
                input_tokens=usage_meta.prompt_token_count,
                output_tokens=out_tok,
                reasoning_tokens=thoughts,
                total_tokens=usage_meta.total_token_count,
                raw={
                    "prompt_token_count": usage_meta.prompt_token_count,
                    "candidates_token_count": cand,
                    "thoughts_token_count": thoughts,
                },
            )
        yield StreamEnd(
            outcome=outcome,
            finish_reason=finish_reason,
            request_id=None,
            usage=usage,
        )

    async def aclose(self) -> None:
        await self._client.aio.aclose()
