from __future__ import annotations

import os
import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from mmc.clock import SteppingClock
from mmc.config.loader import load_app_config
from mmc.core.tokens import TokenEstimator
from mmc.providers.registry import ProviderRegistry
from mmc.redact import Redactor
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.repository import RunRepository

SENTINEL_ANTHROPIC = "sk-ant-SENTINELaaaa" + "b" * 20
SENTINEL_OPENAI = "sk-proj-SENTINELbbbb" + "c" * 20
SENTINEL_GEMINI = "AIzaSENTINELcccc" + "d" * 35
SENTINEL_XAI = "xai-SENTINELdddd" + "e" * 20

_ENV_KEYS_TO_REMOVE = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
    "GOOGLE_GEMINI_BASE_URL",
    "GEMINI_BASE_URL",
    "XAI_API_HOST",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)

_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_allowed_address(address: object) -> bool:
    if isinstance(address, str):
        host = address.split(":")[0]
        return host in _LOCAL_HOSTS
    if isinstance(address, tuple) and address:
        host = address[0]
        if isinstance(host, str):
            return host in _LOCAL_HOSTS
    return False


def _guarded_connect(self: socket.socket, address: object) -> None:
    if not _is_allowed_address(address) and self.family != socket.AF_UNIX:
        raise OSError(f"network blocked by test guard: {address!r}")
    return _ORIGINAL_CONNECT(self, address)  # type: ignore[arg-type]


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    if not _is_allowed_address(address) and self.family != socket.AF_UNIX:
        raise OSError(f"network blocked by test guard: {address!r}")
    return _ORIGINAL_CONNECT_EX(self, address)  # type: ignore[arg-type]


def _guarded_create_connection(
    address: tuple[str, int] | tuple[str, int, int, int],
    timeout: float | None = None,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    if not _is_allowed_address(address):
        raise OSError(f"network blocked by test guard: {address!r}")
    return _ORIGINAL_CREATE_CONNECTION(address, timeout, source_address)


@pytest.fixture(autouse=True)
def _socket_guard() -> Iterator[None]:
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
    yield
    socket.socket.connect = _ORIGINAL_CONNECT  # type: ignore[method-assign]
    socket.socket.connect_ex = _ORIGINAL_CONNECT_EX  # type: ignore[method-assign]
    socket.create_connection = _ORIGINAL_CREATE_CONNECTION  # type: ignore[assignment]


def test_socket_guard_blocks_external() -> None:
    with pytest.raises(OSError, match="network blocked"):
        socket.create_connection(("203.0.113.1", 443), timeout=0.1)


@pytest.fixture(autouse=True)
def _env_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS_TO_REMOVE:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MMC_PROFILE", "mock")
    monkeypatch.setenv("MMC_TOKEN_ESTIMATOR", "chars")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")


@pytest.fixture
def sentinel_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    keys = {
        "ANTHROPIC_API_KEY": SENTINEL_ANTHROPIC,
        "OPENAI_API_KEY": SENTINEL_OPENAI,
        "GEMINI_API_KEY": SENTINEL_GEMINI,
        "XAI_API_KEY": SENTINEL_XAI,
    }
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    return keys


@pytest.fixture
def scrubbed_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _ENV_KEYS_TO_REMOVE:
        env.pop(key, None)
    env["MMC_PROFILE"] = "mock"
    env["MMC_TOKEN_ESTIMATOR"] = "chars"
    env["OTEL_SDK_DISABLED"] = "true"
    return env


@pytest.fixture
def stepping_clock() -> SteppingClock:
    return SteppingClock(
        start=datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC),
        step=timedelta(seconds=60),
    )


@pytest.fixture
def id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"run-{counter:04d}"

    return _next


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "mmc.sqlite3"
    monkeypatch.setenv("MMC_DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def settings(tmp_db: Path, sentinel_keys: dict[str, str]) -> Settings:
    return Settings.from_env()


@pytest.fixture
def redactor(settings: Settings) -> Redactor:
    secrets = [v.get_secret_value() for v in settings.keys.values()]
    return Redactor(secrets)


@pytest.fixture
def app_config() -> object:
    return load_app_config(None)


@pytest.fixture
def registry(app_config: Any, settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(app_config, settings)


@pytest.fixture
def repo(tmp_db: Path) -> RunRepository:
    engine = init_db(tmp_db)
    return RunRepository(engine)


@pytest.fixture
def estimator() -> TokenEstimator:
    return TokenEstimator("chars")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
