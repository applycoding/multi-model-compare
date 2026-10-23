# Docker & CI

## Docker
Multi-stage `Dockerfile`, non-root user, `/data` volume, `HEALTHCHECK`, loopback publish in docs.

## CI jobs
Lint (ruff), types (mypy), unit, contract, e2e — all actions pinned by full SHA.

## Checkpoint
```bash
docker build -t mmc .
docker run --rm -d --name mmc -p 127.0.0.1:8000:8000 mmc
uv run python scripts/smoke.py http://127.0.0.1:8000
```
Publish on loopback only: `-p 127.0.0.1:8000:8000`.

