# multi-model-compare

Portfolio demo (MIT) by Arpan Bom — compare up to 8 LLM models concurrently with structured judging.

## Quickstart (mock, no keys)

```bash
uv sync
uv run mmc run "Explain CAP theorem in 3 sentences" --seed 1
uv run mmc serve   # http://127.0.0.1:8000
```

## Docker (local)

```bash
docker build -t mmc .
docker run --rm -d --name mmc -p 127.0.0.1:8000:8000 mmc
uv run python scripts/smoke.py http://127.0.0.1:8000
```

See [PLAN.md](PLAN.md) and [docs/tutorial/](docs/tutorial/) for the full tutorial (`stage-00` … `stage-14` tags).
