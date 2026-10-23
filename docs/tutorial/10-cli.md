# CLI

The `mmc` command-line interface is the fastest way to run comparisons, inspect history, export data, and start the local web server without writing Python.

## What this module does

`src/mmc/cli.py` builds an argparse tree with subcommands: `run`, `providers`, `history`, `show`, `export`, `clear`, and `serve`. On startup it loads `Settings.from_env()`, optionally overrides profile from `--profile`, constructs a `Redactor` from configured keys, configures logging, loads YAML config, opens SQLite via `init_db()`, and creates a `RunRepository`.

The `run` subcommand parses prompt and model options into `RunRequest`, calls `resolve_request()`, prints vendor disclosure on **stderr** before any provider I/O, then runs `CompareService.run()` inside asyncio. Other subcommands read or mutate stored records, or launch uvicorn with app factory `mmc.web.app:create_app`.

Display helpers in `src/mmc/display.py` format timestamps and millisecond timings for human-readable tables.

## Code excerpt

Entry routing and disclosure before network:

```python
# src/mmc/cli.py
settings = Settings.from_env()
secrets = [v.get_secret_value() for v in settings.keys.values()]
redactor = Redactor(secrets)
configure_logging(settings, redactor)
...
print(cli_run_disclosure(settings.profile, resolved.vendors_contacted), file=sys.stderr)
```

Disclosure strings (`src/mmc/disclosure.py`) distinguish mock mode from live vendor lists:

```python
def cli_run_disclosure(profile: str, vendors: list[str]) -> str:
    if mock_profile_active(profile):
        return "Mock mode: nothing is sent to any provider"
    return f"Sending prompt to: {', '.join(vendors)}"
```

## Why this design matters

Printing disclosure to stderr keeps stdout free for machine-readable exports when users pipe output. Sharing the same service and repository types as the web app guarantees CLI runs appear identically in history and CSV exports.

Argparse keeps dependencies minimal compared to a heavier CLI framework, which matters for Docker images that only install production extras.

## Tests to run

CLI argument parsing, run flow, and subcommands:

```bash
uv run pytest tests/unit/test_cli.py -q
```

Manual smoke in mock profile (no API keys required):

```bash
uv run mmc run "hello" --seed 1
```

History and export after a run:

```bash
uv run mmc history
uv run mmc export --format json --out -
```
