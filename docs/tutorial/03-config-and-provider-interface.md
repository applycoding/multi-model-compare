# Config and provider interface

Configuration and the provider contract are the seams where vendor differences stop and shared runner logic begins.

## What these modules do

`src/mmc/config/loader.py` loads `models.yaml`, pricing, and rubric either from `MMC_CONFIG_DIR` or bundled defaults under `mmc.defaults`. YAML parsing uses `DupKeySafeLoader` in `yaml_loader.py`, which rejects duplicate keys with a file and line number instead of silently overwriting.

`src/mmc/config/schemas.py` (not shown here) validates the merged `AppConfig`: model specs, judge defaults, limits, and pricing tables. `src/mmc/providers/base.py` defines `ProviderRequest`, streaming events (`TextDelta`, `StreamEnd`), and `ProviderError` with typed `ErrorKind` values.

`src/mmc/providers/mock.py` supplies deterministic behaviors (including a `gate` mode used to prove concurrency). `src/mmc/providers/registry.py` constructs per-event-loop clients, wraps providers to count calls, enforces terminal events, and exposes `availability()` based on keys and profile.

Every vendor implements `async def stream(req) -> AsyncIterator[StreamEvent]`, yielding text deltas and exactly one terminal `StreamEnd` with usage when possible.

## Code excerpt

Duplicate-safe YAML loading:

```python
# src/mmc/config/yaml_loader.py
if key in mapping:
    line = key_node.start_mark.line + 1
    raise ConfigError(f"{loader.name}:{line}: duplicate key '{key}'")
```

The shared streaming types:

```python
# src/mmc/providers/base.py
class TextDelta(BaseModel):
    kind: Literal["delta"] = "delta"
    text: str


class StreamEnd(BaseModel):
    kind: Literal["end"] = "end"
    outcome: Outcome
    finish_reason: str | None
    request_id: str | None
    usage: ProviderUsage | None
```

## Why this design matters

A narrow event stream lets the runner treat Claude SSE, OpenAI Responses events, Gemini async iterators, and Grok gRPC chunks uniformly. Centralizing protocol errors (missing terminal event) in the registry wrapper means adapters only translate wire format, not retry policy for the whole app.

Strict config validation prevents partially loaded rubrics or unknown model keys from reaching live API calls, which saves money and makes mock tests representative.

## Tests to run

Configuration parsing and schema edges:

```bash
uv run pytest tests/unit/test_config.py -q
```

Mock provider behaviors and registry wiring:

```bash
uv run pytest tests/unit/test_mock_provider.py -q
```

Recorded contract suites for real adapters (later chapters) build on this interface:

```bash
uv run pytest tests/contract/test_provider_contracts.py -q
```
