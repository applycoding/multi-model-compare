# Web UI & security

## Modules
- `src/mmc/web/routes_pages.py`, `routes_api.py`, `security.py`
- `src/mmc/core/supervisor.py` — max concurrent runs, drain on shutdown

## Security
Host allowlist, Origin + CSRF on mutations, strict CSP, loopback bind.

## Checkpoint
```bash
uv run pytest tests/unit/test_web.py tests/unit/test_security.py tests/unit/test_supervisor_lifecycle.py -q
```

