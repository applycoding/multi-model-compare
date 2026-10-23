from __future__ import annotations

from mmc.settings import Settings


def test_defaults_mock_profile() -> None:
    s = Settings.from_env({})
    assert s.profile == "mock"
    assert s.token_estimator == "chars"
    assert "127.0.0.1" in s.allowed_hosts


def test_blank_keys_ignored() -> None:
    s = Settings.from_env({"ANTHROPIC_API_KEY": "  ", "OPENAI_API_KEY": ""})
    assert "ANTHROPIC_API_KEY" not in s.keys


def test_allowed_hosts_extra(monkeypatch) -> None:
    monkeypatch.setenv("MMC_ALLOWED_HOSTS", "testhost,foo")
    s = Settings.from_env()
    assert "testhost" in s.allowed_hosts
    assert "foo" in s.allowed_hosts
