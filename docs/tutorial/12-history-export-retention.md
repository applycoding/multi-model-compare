# History, export, and retention

Operators need to list past runs, inspect details, export datasets for analysis, and delete data without corrupting SQLite relations.

## What these modules do

History list endpoints and CLI `history` read lightweight `RunSummary` rows: created time, prompt preview (first 200 characters), status, known subtotal USD, and cost flags such as `estimated` or `unknown`. Detail views load the full `RunRecord` JSON snapshot by run id.

`src/mmc/export.py` serialises runs to JSON with `schema_version=1` wrapped in `RunExport`, or flattens rows to CSV with stable criterion column ordering derived from rubric keys across the export batch. `_sanitize_cell()` neutralises formula injection in spreadsheet tools by prefixing dangerous leading characters.

Deletion via repository `delete()` removes the summary row first, then the snapshot. `clear()` counts and wipes all runs for retention resets. Exports operate on in-memory `RunRecord` objects so redaction applied at save time is what users receive.

## Code excerpt

JSON export envelope:

```python
# src/mmc/export.py
class RunExport(BaseModel):
    schema_version: Literal[1] = 1
    exported_at: datetime
    runs: list[RunRecord]


def to_json(records: Iterable[RunRecord], now: datetime) -> str:
    payload = RunExport(exported_at=now, runs=list(records))
    return payload.model_dump_json()
```

CSV formula-prefix guard:

```python
def _sanitize_cell(value: str) -> str:
    ...
    if result and result[0] in "=+-@\t\r\n":
        result = "'" + result
    return result
```

Ordered delete:

```python
# src/mmc/storage/repository.py
if summary is not None:
    session.delete(summary)
    session.flush()
session.delete(row)
```

## Why this design matters

Separating summary and snapshot tables keeps list queries cheap while preserving rich nested judge data in JSON. Versioned export schema gives downstream tools a migration hook. CSV sanitisation is a small line of defense against prompt text that starts with `=` being interpreted as formulas in Excel or LibreOffice.

Explicit delete ordering avoids foreign key violations without cascading surprises.

## Tests to run

Export JSON and CSV:

```bash
uv run pytest tests/unit/test_export.py -q
```

Repository list, delete, clear:

```bash
uv run pytest tests/unit/test_repository.py -q
```

Manual CSV smoke:

```bash
uv run mmc export --format csv --out -
```
