# History & export

## Modules
- `src/mmc/export.py` — JSON `schema_version=1`, CSV with formula-prefix escaping
- History reads from `run_summaries`, detail from snapshots

## Delete / clear
Removes both summary row and snapshot (FK-safe ordering).

## Checkpoint
```bash
uv run pytest tests/unit/test_export.py -q && uv run mmc export --format csv --out -
```

