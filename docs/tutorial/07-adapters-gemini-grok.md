# Gemini and Grok adapters

Google Gemini and xAI Grok use different client stacks than the HTTP/SSE-first vendors, but they still expose the same `StreamEvent` iterator to the runner.

## What these modules do

`src/mmc/providers/google_provider.py` wraps `google.genai.Client` with `HttpOptions` for millisecond timeouts and limited HTTP retries. Streaming uses `generate_content_stream` (async iteration over chunks). The provider maps finish reasons and safety blocks into mmc outcomes (`ok`, `incomplete`, `blocked`, etc.) and closes the async client on shutdown when it owns the httpx client.

`src/mmc/providers/xai_provider.py` uses `xai_sdk.AsyncClient` with an injectable `chat_factory` for tests. Streaming reads `chunk.content` from gRPC-style iterators. Reasoning token fields may not sum cleanly with billed output; the adapter sets `billing_estimated` on usage when reasoning counts are present but not verified additive. Structured judge calls can use `parse()` with a Pydantic model parallel to other vendors' JSON schema paths.

Contract tests for Google replay JSON under `tests/fixtures/recorded/google/`. xAI fixtures are JSON files under `tests/fixtures/recorded/xai/` consumed by `ReplayChat` in `tests/contract/test_xai_adapter.py`.

## Code excerpt

Gemini client and timeout wiring:

```python
# src/mmc/providers/google_provider.py
self._client = genai.Client(
    api_key=key,
    http_options=HttpOptions(
        retry_options=HttpRetryOptions(attempts=1),
        httpx_async_client=httpx_async_client,
    ),
)
config_kwargs: dict[str, Any] = {
    "max_output_tokens": req.max_output_tokens,
    "http_options": HttpOptions(timeout=int(req.timeout_s * 1000)),
}
```

xAI finish reason mapping:

```python
# src/mmc/providers/xai_provider.py
_FINISH_MAP = {
    "stop": "ok",
    "max_tokens": "incomplete",
    "content_filter": "blocked",
}
```

## Why this design matters

Gemini's async stream must be awaited chunk by chunk; hiding that inside `stream()` keeps `run_contestants()` generic. Explicit `aclose()` prevents resource leaks when the web supervisor drains in-flight runs during shutdown.

For Grok, marking reasoning-related billing as estimated avoids presenting false precision in CSV exports when token math is vendor-opaque. Injectable chat factories let contract tests run fully offline like SSE replays.

## Tests to run

Google/Gemini contract replays:

```bash
uv run pytest tests/contract/test_google_adapter.py -q
```

xAI contract replays:

```bash
uv run pytest tests/contract/test_xai_adapter.py -q
```

Filter both:

```bash
uv run pytest tests/contract -k "google or xai" -q
```

Fixture catalog integrity:

```bash
uv run pytest tests/contract/test_recorded_fixture_catalog.py -q
```
