# Overview

## Goal
Build **multi-model-compare (mmc)**: one prompt, up to eight models, structured judge, SQLite history, mock-first CLI and web UI.

## Architecture
- `src/mmc/core/` — request validation, concurrent `runner`, tokens, pricing, supervisor
- `src/mmc/providers/` — vendor adapters + `mock.py` + `registry.py`
- `src/mmc/judge/` — anonymised JSON payload, native structured output, retries
- `src/mmc/storage/` — immutable `RunRecord` snapshots in SQLite
- `src/mmc/web/` — FastAPI loopback UI with CSRF and CSP

## Key excerpt
The service orchestrates contestants then the judge:

```python
# mmc/service.py (simplified)
answers = await run_contestants(...)
judge = await run_judge(...)
record = build_run_record(...)
repo.save(record)
```

## Checkpoint
```bash
uv run pytest tests/unit/test_settings.py -q
```

