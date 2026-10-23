from __future__ import annotations

from pathlib import Path

import pytest

from mmc.providers.base import ProviderError, StreamEnd
from tests.contract.conftest import normalize_stream_events, stream_recorded_fixture

# (vendor, fixture_name, expected_outcome | None, expect_error)
_CATALOG: list[tuple[str, str, str | None, bool]] = [
    ("anthropic", "ok", "ok", False),
    ("anthropic", "refusal", "refused", False),
    ("anthropic", "incomplete", "incomplete", False),
    ("anthropic", "truncation", "incomplete", False),
    ("anthropic", "error", None, True),
    ("anthropic", "missing_terminal", None, True),
    ("anthropic", "judge", "ok", False),
    ("openai", "ok", "ok", False),
    ("openai", "refusal", "refused", False),
    ("openai", "incomplete", "incomplete", False),
    ("openai", "truncation", "incomplete", False),
    ("openai", "blocked", "blocked", False),
    ("openai", "error", None, True),
    ("openai", "missing_terminal", "ok", False),
    ("openai", "judge", "ok", False),
    ("google", "ok", "ok", False),
    ("google", "blocked", "blocked", False),
    ("google", "incomplete", "incomplete", False),
    ("google", "truncation", "incomplete", False),
    ("google", "missing_terminal", None, True),
    ("google", "usage_only", "ok", False),
    ("google", "reasoning_only", "incomplete", False),
    ("google", "error", None, True),
    ("google", "judge", "ok", False),
    ("xai", "ok", "ok", False),
    ("xai", "blocked", "blocked", False),
    ("xai", "incomplete", "incomplete", False),
    ("xai", "truncation", "incomplete", False),
    ("xai", "missing_terminal", None, True),
    ("xai", "usage_only", "ok", False),
    ("xai", "reasoning", "ok", False),  # reasoning.json (billing_estimated)
    ("xai", "judge", "ok", False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "name", "expected_outcome", "expect_error"),
    _CATALOG,
    ids=[f"{v}-{n}" for v, n, _, _ in _CATALOG],
)
async def test_recorded_fixture_stream(
    recorded_dir: Path,
    vendor: str,
    name: str,
    expected_outcome: str | None,
    expect_error: bool,
) -> None:
    judge = name == "judge"
    fixture_path = recorded_dir / vendor / (f"{name}.sse" if vendor in ("anthropic", "openai") else f"{name}.json")
    assert fixture_path.is_file()
    assert (recorded_dir / vendor / f"{name}.meta.json").is_file()

    if expect_error:
        with pytest.raises((ProviderError, Exception)):
            await stream_recorded_fixture(recorded_dir, vendor, name, judge=judge)
        return

    events = await stream_recorded_fixture(recorded_dir, vendor, name, judge=judge)
    assert events
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].outcome == expected_outcome
    norm = normalize_stream_events(events)
    assert norm[-1]["kind"] == "end"
    if name == "usage_only":
        assert any(item["kind"] == "delta" for item in norm)
    if name == "reasoning_only" and vendor == "google":
        assert not any(item["kind"] == "delta" for item in norm)
