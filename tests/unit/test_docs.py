from __future__ import annotations

import re
from pathlib import Path

_UNICODE_DASHES = re.compile(r"[\u2013\u2014]")


def test_readme_and_docs_use_plain_dashes_not_en_em() -> None:
    paths = [Path("README.md"), *Path("docs").rglob("*.md")]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert _UNICODE_DASHES.search(text) is None, f"unicode dash in {path}"


def test_pricing_yaml_marked_illustrative() -> None:
    text = Path("src/mmc/defaults/pricing.yaml").read_text(encoding="utf-8")
    assert "ILLUSTRATIVE" in text
    assert "TODO: verify" in text


def test_models_yaml_points_at_model_ids_doc() -> None:
    text = Path("src/mmc/defaults/models.yaml").read_text(encoding="utf-8")
    assert "MODEL_IDS.md" in text


def test_ci_runs_playwright_e2e_job() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "e2e:" in ci
    assert "playwright install" in ci
    assert "pytest tests/e2e" in ci


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
