from __future__ import annotations

import pytest

from mmc.core.request import RequestValidationError, RunRequest, resolve_request


def _resolve(prompt: str = "hello", **kwargs: object):
    from mmc.config.loader import load_app_config

    config = load_app_config(None)
    settings = __import__("mmc.settings", fromlist=["Settings"]).Settings.from_env()
    redactor = __import__("mmc.redact", fromlist=["Redactor"]).Redactor([])
    registry = __import__("mmc.providers.registry", fromlist=["ProviderRegistry"]).ProviderRegistry(config, settings)
    req = RunRequest(prompt=prompt, **kwargs)  # type: ignore[arg-type]
    return resolve_request(req, config, settings, redactor, registry)


def test_empty_prompt() -> None:
    with pytest.raises(RequestValidationError):
        _resolve("   ")


def test_prompt_contains_key(sentinel_keys) -> None:
    from mmc.config.loader import load_app_config
    from mmc.providers.registry import ProviderRegistry
    from mmc.redact import Redactor
    from mmc.settings import Settings
    from tests.conftest import SENTINEL_OPENAI

    config = load_app_config(None)
    settings = Settings.from_env()
    redactor = Redactor([v.get_secret_value() for v in settings.keys.values()])
    registry = ProviderRegistry(config, settings)
    req = RunRequest(prompt=f"hello {SENTINEL_OPENAI}")
    with pytest.raises(RequestValidationError, match="configured API key"):
        resolve_request(req, config, settings, redactor, registry)


def test_unknown_model() -> None:
    with pytest.raises(RequestValidationError):
        _resolve(models=["no:such"])


def test_nan_temperature() -> None:
    with pytest.raises(RequestValidationError):
        _resolve(temperature=float("nan"))


def test_dedup_models() -> None:
    resolved = _resolve(models=["mock:mock-gpt", "mock:mock-gpt", "mock:mock-claude"])
    assert len(resolved.contestants) == 2
