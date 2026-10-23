from __future__ import annotations

from pathlib import Path


def test_docker_run_loopback_in_readme() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8000:8000" in text or Path("docs/tutorial/14-docker-and-ci.md").exists()


def test_dockerignore_env() -> None:
    content = Path(".dockerignore").read_text(encoding="utf-8")
    assert ".env" in content


def test_ci_sha_pins_when_present() -> None:
    ci = Path(".github/workflows/ci.yml")
    if not ci.exists():
        return
    text = ci.read_text(encoding="utf-8")
    assert "permissions:" in text
    assert "contents: read" in text
    import re

    for match in re.finditer(r"uses:\s+\S+@([0-9a-f]{40})", text):
        assert len(match.group(1)) == 40
