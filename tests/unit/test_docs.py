from __future__ import annotations

import re
from pathlib import Path


def test_docker_run_loopback_in_readme() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8000:8000" in text
    tutorial = Path("docs/tutorial/14-docker-and-ci.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8000:8000" in tutorial


def test_dockerignore_env() -> None:
    content = Path(".dockerignore").read_text(encoding="utf-8")
    assert ".env" in content
    assert ".env.*" in content


def test_ci_sha_pins() -> None:
    ci = Path(".github/workflows/ci.yml")
    assert ci.is_file()
    text = ci.read_text(encoding="utf-8")
    assert "permissions:" in text
    assert "contents: read" in text
    for line in text.splitlines():
        if "uses:" not in line:
            continue
        assert re.search(r"@[0-9a-f]{40}\b", line), f"unpinned action: {line.strip()}"
