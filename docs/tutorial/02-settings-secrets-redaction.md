# Settings & redaction

## Modules
- `src/mmc/settings.py` — `MMC_*` env vars, blank keys ignored, `MMC_ALLOWED_HOSTS`
- `src/mmc/redact.py` — pattern + configured secret redaction
- `src/mmc/logging_setup.py` — `RedactingFormatter` scrubs tracebacks

## Example
```python
settings = Settings.from_env()
redactor = Redactor([k.get_secret_value() for k in settings.keys.values()])
```

## Checkpoint
```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_redact.py -q
```

