from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mmc.records import RunRecord

REDACTED = "[REDACTED]"


class Redactor:
    PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"xai-[A-Za-z0-9_-]{20,}"),
        re.compile(r"AIza[A-Za-z0-9_-]{35}"),
        re.compile(r"Bearer \S+"),
    ]

    def __init__(self, secrets: Iterable[str]) -> None:
        self._secrets = [s for s in secrets if s]

    def contains_secret(self, text: str) -> bool:
        return any(secret and secret in text for secret in self._secrets)

    def __call__(self, text: str) -> str:
        result = text
        for secret in self._secrets:
            if secret:
                result = result.replace(secret, REDACTED)
        for pattern in self.PATTERNS:
            result = pattern.sub(REDACTED, result)
        return result


def redact_record(record: RunRecord, redactor: Redactor) -> RunRecord:
    from mmc.records import RunRecord

    data = record.model_dump(mode="json")
    redacted = _redact_obj(data, redactor)
    return RunRecord.model_validate(redacted)


def _redact_obj(obj: Any, redactor: Redactor) -> Any:
    if isinstance(obj, str):
        return redactor(obj)
    if isinstance(obj, list):
        return [_redact_obj(item, redactor) for item in obj]
    if isinstance(obj, dict):
        return {k: _redact_obj(v, redactor) for k, v in obj.items()}
    return obj
