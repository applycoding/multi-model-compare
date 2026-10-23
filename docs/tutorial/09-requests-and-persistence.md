# Requests & persistence

## Modules
- `src/mmc/core/request.py` — single `resolve_request()` for CLI, API, and HTML forms
- `src/mmc/storage/repository.py` — snapshot `record_json` + `run_summaries` index
- `src/mmc/service.py` — ties runner, judge, pricing into `RunRecord`

## Immutability
Re-saving the same run id must fail (snapshot is immutable).

## Checkpoint
```bash
uv run pytest tests/unit/test_request.py tests/unit/test_repository.py -q
```

