# Concurrent runner

The runner is where mmc meets asyncio: every contestant model streams in parallel, shares a run-level deadline, and produces comparable `AnswerResult` rows for pricing and judging.

## What this module does

`src/mmc/core/runner.py` implements `_run_one()` for a single `ModelSpec` and `run_contestants()` for the full list. Each worker uses `asyncio.timeout_at()` bounded by both per-request `timeout_s` and the global run deadline from `CompareService`. Events from `registry.get(spec.provider).stream(req)` update TTFT on the first non-empty `TextDelta`, accumulate text, and require a terminal `StreamEnd`.

On success or failure, the runner calls `resolve_usage()` and `compute_cost()`, caps extremely long text at 100,000 characters, and records timing in milliseconds. Skipped models (missing API keys) never hit the network: availability is checked first.

Concurrency uses `asyncio.TaskGroup` so one failing task does not silently drop siblings; cancellation propagates as `AnswerResult` with status `cancelled`. `src/mmc/clock.py` supplies injectable time for deterministic unit tests.

## Code excerpt

TTFT and terminal-event handling:

```python
# src/mmc/core/runner.py
async for event in stream:
    if isinstance(event, TextDelta):
        if event.text:
            if ttft is None:
                ttft = (clock.perf() - start) * 1000
            text_parts.append(event.text)
    elif isinstance(event, StreamEnd):
        end_event = event
...
if end_event is None:
    status = "error"
    error_info = ErrorInfo(kind="protocol", message="stream ended without terminal event")
```

Fan-out:

```python
async with asyncio.TaskGroup() as tg:
    for i, spec in enumerate(specs):
        tg.create_task(worker(i, spec))
```

## Why this design matters

Parallel contestant calls minimize wall-clock latency for comparisons. Sharing one deadline prevents a single slow model from blocking the UI indefinitely while others finished minutes ago. Measuring TTFT only on non-empty deltas avoids counting keep-alive or usage-only chunks as user-visible latency.

The mock `gate` behavior proves `max_in_flight == n` without sleeping on real clocks, which keeps CI fast and stable.

## Tests to run

Core runner behavior, TTFT, timeouts, and protocol errors:

```bash
uv run pytest tests/unit/test_runner.py -q
```

Lifecycle and cancellation interactions:

```bash
uv run pytest tests/unit/test_runner_lifecycle.py -q
```

The gate concurrency tests live in `tests/unit/test_runner.py` (`test_gate_max_in_flight` and the eight-model variant).
