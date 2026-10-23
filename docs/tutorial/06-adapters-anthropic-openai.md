# Anthropic & OpenAI

## Modules
- `src/mmc/providers/anthropic_provider.py` — Messages streaming, **no temperature/top_k** on Claude
- `src/mmc/providers/openai_provider.py` — Responses API, `store=False`, protocol error if no terminal event

## Contract tests
Recorded SSE under `tests/fixtures/recorded/{anthropic,openai}/` replay through real SDK clients + `httpx2.MockTransport`.

## Checkpoint
```bash
uv run pytest tests/contract -k "anthropic or openai" -q
```

