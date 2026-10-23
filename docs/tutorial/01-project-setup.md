# Project setup

This chapter covers how mmc is packaged, which tools guard quality, and how to bootstrap a developer machine before touching providers or the web UI.

## What you are building

mmc is a Python 3.13 application managed with **uv**. Source lives under `src/mmc/` as an installable package. The console script `mmc` is declared in `pyproject.toml` and points at `mmc.cli:main`. Development dependencies include **ruff** (lint and format), **mypy** (strict typing on `src/`), **pytest** with asyncio auto mode, and **Playwright** for browser e2e tests.

Runtime dependencies pin major vendor SDKs (Anthropic, OpenAI, Google GenAI, xAI) plus FastAPI, SQLModel, PyYAML, and tiktoken for token estimation. Package data ships default YAML (`defaults/models.yaml`, pricing, rubric) and web templates inside the wheel.

Continuous integration in `.github/workflows/ci.yml` runs ruff, mypy, unit tests, contract replays, scenario tests, and Playwright e2e. Third-party GitHub Actions are pinned by full commit SHA, and gitleaks scans for accidental secrets.

## Code excerpt

The project metadata and entry point are centralized:

```toml
# pyproject.toml (excerpt)
[project]
name = "mmc"
requires-python = ">=3.13,<3.14"

[project.scripts]
mmc = "mmc.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

The build backend uses `uv_build` with `module-root = "src"`, so imports are always `from mmc...` whether you run from a venv or an editable install.

## Why these choices matter

Pinning Python to 3.13 keeps language features (for example `asyncio.TaskGroup` in the runner) consistent across laptops and CI. uv gives reproducible lockfiles and fast syncs, which matters when contract tests pull many fixtures. Treating ruff and mypy as gatekeepers catches adapter mistakes before they hit recorded SSE/JSON replays.

Shipping defaults inside the package means `load_app_config(None)` works out of the box; operators can override with `MMC_CONFIG_DIR` without forking code.

## Run locally

Install dependencies and verify static checks:

```bash
uv sync
uv run ruff check .
uv run mypy src
```

## Tests to run

Documentation and CI hygiene (SHA-pinned actions, Docker loopback docs):

```bash
uv run pytest tests/unit/test_docs.py -q
```

After changing packaging or scripts:

```bash
uv run pytest tests/unit/test_cli.py -q
```
