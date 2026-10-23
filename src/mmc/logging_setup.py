from __future__ import annotations

import logging
import os
import sys

from mmc.redact import Redactor
from mmc.settings import Settings

os.environ.setdefault("OTEL_SDK_DISABLED", "true")


class RedactingFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return self._redactor(text)


def configure_logging(settings: Settings, redactor: Redactor) -> None:
    os.environ["OTEL_SDK_DISABLED"] = "true"
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter(redactor, fmt="%(levelname)s %(name)s: %(message)s"))
    root.handlers.clear()
    root.addHandler(handler)
    for name in (
        "httpx",
        "httpx2",
        "httpcore",
        "grpc",
        "anthropic",
        "openai",
        "google_genai",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
