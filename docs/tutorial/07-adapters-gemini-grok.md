# Gemini & Grok

## Modules
- `src/mmc/providers/google_provider.py` — awaited `generate_content_stream`, ms timeout, `client.aio.aclose()`
- `src/mmc/providers/xai_provider.py` — gRPC chat seam, `chunk.content`, billing_estimated when reasoning not additive

## xAI fixtures
JSON files in `tests/fixtures/recorded/xai/` replay via `ReplayChat` in contract tests.

## Checkpoint
```bash
uv run pytest tests/contract -k "google or xai" -q
```

