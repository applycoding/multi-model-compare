from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping

from pydantic import SecretStr

from mmc.config.schemas import AppConfig, ModelSpec, ProviderId
from mmc.providers.base import Provider, ProviderError, ProviderRequest, StreamEnd, StreamEvent
from mmc.providers.mock import MockProvider
from mmc.settings import Settings


class _CountingProvider:
    def __init__(self, inner: Provider, registry: ProviderRegistry) -> None:
        self._inner = inner
        self._registry = registry

    @property
    def id(self) -> ProviderId:
        return self._inner.id

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        self._registry._call_count += 1
        saw_end = False
        gen = self._inner.stream(req)
        try:
            async for event in gen:
                if isinstance(event, StreamEnd):
                    saw_end = True
                yield event
        finally:
            close = getattr(gen, "aclose", None)
            if close is not None:
                await close()
        if not saw_end:
            raise ProviderError("protocol", "stream ended without terminal event")

    async def aclose(self) -> None:
        await self._inner.aclose()


class ProviderRegistry:
    def __init__(
        self,
        config: AppConfig,
        settings: Settings,
        factories: Mapping[ProviderId, Callable[[SecretStr | None], Provider]] | None = None,
    ) -> None:
        self._config = config
        self._settings = settings
        self._factories = dict(factories or {})
        self._providers: dict[ProviderId, _CountingProvider] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            self._loop = loop
            self._providers = {}
        return loop

    def availability(self, spec: ModelSpec) -> tuple[bool, str | None]:
        if spec.provider == "mock":
            if spec.requires_env and spec.requires_env not in self._settings.keys:
                return False, f"missing env var {spec.requires_env}"
            return True, None
        prov = self._config.providers[spec.provider]
        env_name = spec.requires_env or prov.env_var
        if env_name is None:
            return True, None
        if env_name not in self._settings.keys:
            return False, f"missing env var {env_name}"
        return True, None

    def get(self, provider: ProviderId) -> Provider:
        self._ensure_loop()
        if provider not in self._providers:
            self._providers[provider] = _CountingProvider(self._build(provider), self)
        return self._providers[provider]  # type: ignore[return-value]

    def _build(self, provider: ProviderId) -> Provider:
        if provider in self._factories:
            key = self._settings.keys.get(self._config.providers[provider].env_var or "", None)
            return self._factories[provider](key)
        if provider == "mock":
            return MockProvider(self._config.rubric)
        from mmc.providers.anthropic_provider import AnthropicProvider
        from mmc.providers.google_provider import GoogleProvider
        from mmc.providers.openai_provider import OpenAIProvider
        from mmc.providers.xai_provider import XAIProvider

        spec = self._config.providers[provider]
        env_name = spec.env_var
        secret = self._settings.keys.get(env_name or "", None) if env_name else None
        match provider:
            case "anthropic":
                return AnthropicProvider(secret)
            case "openai":
                return OpenAIProvider(secret)
            case "google":
                return GoogleProvider(secret)
            case "xai":
                return XAIProvider(secret, self._config)
            case _:
                return MockProvider(self._config.rubric)

    async def aclose(self) -> None:
        for prov in self._providers.values():
            await prov.aclose()
        self._providers.clear()
