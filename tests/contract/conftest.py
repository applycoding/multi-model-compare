from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mmc.providers.base import StreamEnd, StreamEvent, TextDelta


@pytest.fixture
def recorded_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "recorded"


def normalize_equivalent_ok(events: list[StreamEvent]) -> list[dict[str, str]]:
    """Cross-vendor ok fixtures should yield the same logical event shape."""
    normalized: list[dict[str, str]] = []
    for event in events:
        if isinstance(event, TextDelta):
            normalized.append({"kind": "delta"})
        elif isinstance(event, StreamEnd):
            normalized.append({"kind": "end", "outcome": event.outcome})
    return normalized


def normalize_stream_events(events: list[StreamEvent]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, TextDelta):
            normalized.append({"kind": "delta", "text": "SYNTHETIC_TEXT"})
        elif isinstance(event, StreamEnd):
            usage = None
            if event.usage:
                usage = {
                    "input_tokens": event.usage.input_tokens,
                    "output_tokens": event.usage.output_tokens,
                    "reasoning_tokens": event.usage.reasoning_tokens,
                    "billing_estimated": event.usage.billing_estimated,
                }
            normalized.append(
                {
                    "kind": "end",
                    "outcome": event.outcome,
                    "finish_reason": event.finish_reason,
                    "usage": usage,
                }
            )
    return normalized


def load_xai_fixture(fixtures_dir: Path, name: str) -> dict[str, Any]:
    path = fixtures_dir / "recorded" / "xai" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
