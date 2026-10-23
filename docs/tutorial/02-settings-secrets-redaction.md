# Settings and redaction

Operational safety in mmc starts with typed settings, aggressive secret redaction, and log formatters that scrub tracebacks before they reach stderr.

## What these modules do

`src/mmc/settings.py` defines `Settings`, loaded from environment variables with the `MMC_` prefix where applicable. Important fields include `profile` (`mock` or `live`), optional `MMC_CONFIG_DIR`, `MMC_DB_PATH`, bind `host`/`port`, and `allowed_hosts` (defaults plus comma-separated extras from `MMC_ALLOWED_HOSTS`). API keys are read from standard vendor env vars; blank values are ignored so missing keys simply mark models unavailable rather than crashing at import time.

`src/mmc/redact.py` implements `Redactor`, which replaces configured secret strings and matches common key patterns (Anthropic, OpenAI, Google, xAI, Bearer tokens). `redact_record()` walks a `RunRecord` JSON tree so persisted history never stores raw keys that appeared in prompts or errors.

`src/mmc/logging_setup.py` installs `RedactingFormatter` on the root logger and quiets noisy HTTP/gRPC libraries. OpenTelemetry is disabled by default via `OTEL_SDK_DISABLED=true` to keep local logs readable.

## Code excerpt

Settings construction ignores empty keys and merges host allowlists:

```python
# src/mmc/settings.py
keys: dict[str, SecretStr] = {}
for name in KEY_ENV_VARS:
    value = env.get(name, "").strip()
    if value:
        keys[name] = SecretStr(value)
return cls(
    profile=profile,
    allowed_hosts=frozenset(allowed),
    keys=keys,
    ...
)
```

Redaction applies both literal secrets and regex patterns:

```python
# src/mmc/redact.py
def __call__(self, text: str) -> str:
    result = text
    for secret in self._secrets:
        if secret:
            result = result.replace(secret, REDACTED)
    for pattern in self.PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result
```

## Why this design matters

Secrets often appear in error messages from upstream SDKs. Scrubbing at log and persistence boundaries means SQLite exports, web pages, and support bundles stay shareable. Using `SecretStr` in settings prevents accidental serialization in debug prints while still allowing explicit `.get_secret_value()` at provider construction.

Host allowlisting pairs with the web middleware in `web/security.py` so DNS rebinding against a local server is harder when you add extra hosts for containers.

## Tests to run

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_redact.py -q
```

Integration with logging configuration is covered indirectly via CLI and web tests that enable logging with a redactor:

```bash
uv run pytest tests/unit/test_cli.py tests/integration/test_sentinel_sink.py -q
```
