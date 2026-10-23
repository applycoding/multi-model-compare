# Docker and CI

Container images and GitHub Actions workflows package mmc for repeatable deployment and enforce quality on every push to `main` and on pull requests.

## What Docker provides

The multi-stage `Dockerfile` builds a locked virtualenv with uv on Python 3.13, pre-downloads the tiktoken `o200k_base` cache into `/opt/tiktoken`, and copies a slim runtime image. The runtime user is non-root (`app`, uid 10001), `/data` is a volume for SQLite (`MMC_DB_PATH=/data/mmc.sqlite3`), and default env sets `MMC_PROFILE=mock` with `MMC_HOST=0.0.0.0` inside the container.

A `HEALTHCHECK` probes `http://127.0.0.1:8000/healthz`. The default command runs `mmc serve --host 0.0.0.0 --port 8000`. When publishing to the host, bind loopback only so the service is not exposed on all interfaces:

```bash
docker run --rm -d --name mmc -p 127.0.0.1:8000:8000 mmc
```

`.dockerignore` excludes `.env` files so secrets are not copied into build context.

## What CI provides

`.github/workflows/ci.yml` defines jobs for lint (ruff check and format check), typecheck (mypy on `src/`), unit tests, contract tests, scenario tests, and e2e. Actions use immutable SHA pins (for example `actions/checkout@...`, `astral-sh/setup-uv@...`). Gitleaks runs with project config `.gitleaks.toml`. Concurrency groups cancel superseded runs on the same ref.

## Code excerpt

Runtime stage defaults:

```dockerfile
# Dockerfile (excerpt)
ENV MMC_PROFILE=mock MMC_DB_PATH=/data/mmc.sqlite3 MMC_HOST=0.0.0.0 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken OTEL_SDK_DISABLED=true
USER app
VOLUME /data
HEALTHCHECK ... CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else 1)"
CMD ["mmc","serve","--host","0.0.0.0","--port","8000"]
```

CI lint job installs Python 3.13 via uv and runs ruff:

```yaml
# .github/workflows/ci.yml (excerpt)
- run: uv python install 3.13 && uv sync --locked
- run: uv run ruff check .
- run: uv run ruff format --check .
```

## Why this design matters

Pre-baking tiktoken data avoids runtime downloads in air-gapped or slow networks. Non-root execution and a dedicated data volume align with minimal container hygiene. Loopback publish in docs and tests (`tests/unit/test_docs.py`) encodes the expectation that mmc is a local tool, not a public edge service without extra hardening.

SHA-pinned actions reduce supply-chain drift; gitleaks adds a second line of defense beyond redaction code paths.

## Tests to run

Docs assertions for Docker and CI conventions:

```bash
uv run pytest tests/unit/test_docs.py -q
```

Build and HTTP smoke after image build:

```bash
docker build -t mmc .
docker run --rm -d --name mmc -p 127.0.0.1:8000:8000 mmc
uv run python scripts/smoke.py http://127.0.0.1:8000
```

Match CI locally before pushing:

```bash
uv run ruff check . && uv run mypy src && uv run pytest tests/unit tests/contract -q
```
