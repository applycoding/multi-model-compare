# Config & providers

## Modules
- `src/mmc/config/loader.py` — duplicate-key-safe YAML via custom SafeLoader
- `src/mmc/providers/base.py` — `ProviderRequest`, `StreamEvent`, `ProviderError`
- `src/mmc/providers/mock.py` — deterministic behaviours for CI
- `src/mmc/providers/registry.py` — per-loop clients, availability, call counting

## Concept
Every vendor implements `async def stream(req) -> AsyncIterator[StreamEvent]` yielding `TextDelta` and a terminal `StreamEnd`.

## Checkpoint
```bash
uv run pytest tests/unit/test_config.py tests/unit/test_mock_provider.py -q
```

