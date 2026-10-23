# Requests and persistence

User input becomes a validated `ResolvedRun`, executes once, and lands in SQLite as an immutable JSON snapshot plus a searchable summary row.

## What these modules do

`src/mmc/core/request.py` defines `RunRequest` (prompt, optional model list, judge override, limits, seed) and `resolve_request()`, the single validation path for CLI flags, REST JSON, and HTML forms. It enforces contestant caps (`MAX_CONTESTANTS`), resolves model keys against config, builds per-model `ProviderRequest` objects, computes `vendors_contacted` for disclosure, and draws a default seed when omitted.

`src/mmc/storage/repository.py` writes two tables: full `record_json` on `RunRow` and denormalised fields on `RunSummaryRow` for history lists (prompt preview, status, subtotal, cost flags). Reads deserialize back into `RunRecord` via Pydantic. `delete()` removes the summary first, then the snapshot, respecting foreign key ordering. `clear()` wipes all runs.

`src/mmc/service.py` ties the pieces together after running contestants and judge, calling `redact_record()` before `save()`. Re-inserting the same primary key raises `IntegrityError`, which tests treat as immutability.

## Code excerpt

Resolved run carries everything downstream needs:

```python
# src/mmc/core/request.py
class ResolvedRun(BaseModel):
    prompt: str
    contestants: list[ModelSpec]
    judge: ModelSpec | None
    requests: dict[str, ProviderRequest]
    judge_settings: JudgeSettings
    seed: int
    vendors_contacted: list[str]
```

Persistence writes snapshot and index together:

```python
# src/mmc/storage/repository.py
session.add(
    RunRow(
        id=record.id,
        record_version=record.record_version,
        record_json=record.model_dump_json(),
    )
)
session.add(
    RunSummaryRow(
        run_id=record.id,
        created_at=record.created_at.isoformat(),
        prompt_preview=record.prompt[:200],
        status=record.status,
        total_known_cost_usd=str(record.total.subtotal_usd),
        cost_flags=cost_flags,
    )
)
```

## Why this design matters

One resolver prevents the web UI from accepting prompts the CLI would reject. Storing canonical JSON snapshots makes exports bit-for-bit faithful and simplifies schema evolution via `record_version` without migrations rewriting old rows.

Summary rows keep history queries fast and LIKE-searchable without parsing JSON in SQL for every list page.

## Tests to run

Request validation and model selection:

```bash
uv run pytest tests/unit/test_request.py -q
```

Repository save, immutability, delete, and clear:

```bash
uv run pytest tests/unit/test_repository.py -q
```

Service-level wiring appears in scenario and CLI tests:

```bash
uv run pytest tests/unit/test_cli.py -q
```
