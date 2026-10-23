from __future__ import annotations

from pathlib import Path

import pytest

from mmc.providers.base import ProviderError, StreamEnd
from tests.contract.conftest import normalize_stream_events, stream_recorded_fixture

# vendor, fixture_name, expected_outcome (if success), error_kind (if ProviderError expected)
_CATALOG: list[tuple[str, str, str | None, str | None]] = [
    ("anthropic", "ok", "ok", None),
    ("anthropic", "refusal", "refused", None),
    ("anthropic", "incomplete", "incomplete", None),
    ("anthropic", "truncation", "incomplete", None),
    ("anthropic", "error", None, "server"),
    ("anthropic", "missing_terminal", None, "server"),
    ("anthropic", "judge", "ok", None),
    ("openai", "ok", "ok", None),
    ("openai", "refusal", "refused", None),
    ("openai", "incomplete", "incomplete", None),
    ("openai", "truncation", "incomplete", None),
    ("openai", "blocked", "blocked", None),
    ("openai", "error", None, "server"),
    ("openai", "missing_terminal", None, "protocol"),
    ("openai", "judge", "ok", None),
    ("google", "ok", "ok", None),
    ("google", "blocked", "blocked", None),
    ("google", "incomplete", "incomplete", None),
    ("google", "truncation", "incomplete", None),
    ("google", "missing_terminal", None, "protocol"),
    ("google", "usage_only", "ok", None),
    ("google", "reasoning_only", "incomplete", None),
    ("google", "error", None, "server"),
    ("google", "judge", "ok", None),
    ("xai", "ok", "ok", None),
    ("xai", "blocked", "blocked", None),
    ("xai", "incomplete", "incomplete", None),
    ("xai", "truncation", "incomplete", None),
    ("xai", "missing_terminal", None, "protocol"),
    ("xai", "usage_only", "ok", None),
    ("xai", "reasoning", "ok", None),
    ("xai", "error", None, "server"),
    ("xai", "judge", "ok", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "name", "expected_outcome", "error_kind"),
    _CATALOG,
    ids=[f"{v}-{n}" for v, n, _, _ in _CATALOG],
)
async def test_recorded_fixture_stream(
    recorded_dir: Path,
    vendor: str,
    name: str,
    expected_outcome: str | None,
    error_kind: str | None,
) -> None:
    judge = name == "judge"
    fixture_path = recorded_dir / vendor / (f"{name}.sse" if vendor in ("anthropic", "openai") else f"{name}.json")
    assert fixture_path.is_file()
    assert (recorded_dir / vendor / f"{name}.meta.json").is_file()

    if error_kind is not None:
        with pytest.raises(ProviderError) as excinfo:
            await stream_recorded_fixture(recorded_dir, vendor, name, judge=judge)
        assert excinfo.value.kind == error_kind
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
