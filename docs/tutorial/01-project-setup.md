# Project setup

## You'll build
Python 3.13 project managed by **uv**, strict **ruff** + **mypy**, CI workflow with SHA-pinned GitHub Actions.

## Files
- `pyproject.toml` — dependencies, `[project.scripts] mmc`, pytest asyncio mode
- `.github/workflows/ci.yml` — lint, types, unit, contract, e2e jobs

## Run locally
```bash
uv sync
uv run ruff check .
uv run mypy src
```

## Checkpoint
```bash
uv run ruff check . && uv run mypy src
```

