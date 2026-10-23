# CLI

## Module
`src/mmc/cli.py` — `run`, `history`, `show`, `export`, `clear`, `serve`.

## Vendor disclosure
`mmc run` prints which vendors will be contacted (or mock disclosure) on **stderr** before any provider call.

## Checkpoint
```bash
uv run mmc run "hello" --seed 1
```

