# Concurrent runner

## Modules
- `src/mmc/core/runner.py` — `asyncio.TaskGroup`, `timeout_at`, TTFT tracking
- `src/mmc/clock.py` — injectable clock for tests

## TTFT rule
`ttft_ms` is set on the first **non-empty** `TextDelta`; usage-only or empty streams keep `ttft_ms=None`.

## Barrier test
Mock `gate` behaviour proves `max_in_flight == n` without wall-clock sleeps.

## Checkpoint
```bash
uv run pytest tests/unit/test_runner.py tests/unit/test_runner_lifecycle.py -q
```

