from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

KEY_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
)

DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["mock", "live"] = "mock"
    config_dir: Path | None = None
    db_path: Path = Path("data/mmc.sqlite3")
    log_level: str = "INFO"
    token_estimator: Literal["auto", "tiktoken", "chars"] = "auto"
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: frozenset[str]
    keys: dict[str, SecretStr]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = dict(environ or os.environ)
        profile = env.get("MMC_PROFILE", "mock")
        if profile not in ("mock", "live"):
            profile = "mock"
        config_dir_raw = env.get("MMC_CONFIG_DIR", "").strip()
        config_dir = Path(config_dir_raw) if config_dir_raw else None
        db_path = Path(env.get("MMC_DB_PATH", "data/mmc.sqlite3"))
        log_level = env.get("MMC_LOG_LEVEL", "INFO")
        token_estimator = env.get("MMC_TOKEN_ESTIMATOR", "auto")
        if token_estimator not in ("auto", "tiktoken", "chars"):
            token_estimator = "auto"
        host = env.get("MMC_HOST", "127.0.0.1")
        port = int(env.get("MMC_PORT", "8000"))
        extra_hosts = env.get("MMC_ALLOWED_HOSTS", "")
        allowed = set(DEFAULT_ALLOWED_HOSTS)
        for part in extra_hosts.split(","):
            part = part.strip()
            if part:
                allowed.add(part)
        keys: dict[str, SecretStr] = {}
        for name in KEY_ENV_VARS:
            value = env.get(name, "").strip()
            if value:
                keys[name] = SecretStr(value)
        return cls(
            profile=profile,
            config_dir=config_dir,
            db_path=db_path,
            log_level=log_level,
            token_estimator=token_estimator,
            host=host,
            port=port,
            allowed_hosts=frozenset(allowed),
            keys=keys,
        )
