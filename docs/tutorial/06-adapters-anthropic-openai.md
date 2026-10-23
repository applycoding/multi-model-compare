# Anthropic and OpenAI adapters

These adapters translate mmc's streaming contract onto Anthropic Messages and the OpenAI Responses API, including structured JSON for the judge.

## What these modules do

`src/mmc/providers/anthropic_provider.py` uses `AsyncAnthropic` with `max_retries=0` and optional injected `httpx2.AsyncClient` for tests. It streams via `messages.stream`, maps SDK exceptions to `ProviderError` kinds, and builds a final `StreamEnd` from `get_final_message()`. Notably, Claude requests in this codebase do not send `temperature` or `top_k` in kwargs even when the user sets temperature for other models; resolved params record `"omitted (unsupported)"` for temperature on Anthropic.

`src/mmc/providers/openai_provider.py` targets `responses.stream` with `store=False` so prompts are not retained server-side by default. It handles output text deltas, refusal deltas, and requires a completed response event before emitting `StreamEnd`. Structured judge output uses `text.format` JSON schema with `strict: True`.

Contract tests replay recorded SSE fixtures from `tests/fixtures/recorded/anthropic/` and `tests/fixtures/recorded/openai/` through real SDK clients backed by `httpx2.MockTransport`, so parsing logic stays aligned with production SDK versions.

## Code excerpt

Anthropic streaming (temperature not passed):

```python
# src/mmc/providers/anthropic_provider.py
kwargs: dict[str, Any] = {
    "model": req.spec.model_id,
    "max_tokens": req.max_output_tokens,
    "messages": [{"role": "user", "content": req.user}],
}
async with self._client.messages.stream(**kwargs) as stream:
    async for text in stream.text_stream:
        if text:
            yield TextDelta(text=text)
```

OpenAI Responses with storage disabled:

```python
# src/mmc/providers/openai_provider.py
kwargs: dict[str, Any] = {
    "model": req.spec.model_id,
    "input": req.user,
    "max_output_tokens": req.max_output_tokens,
    "store": False,
}
async with self._client.responses.stream(**kwargs) as stream:
    ...
```

## Why this design matters

Vendor SDKs differ in event shapes; mmc normalizes them early so the runner never branches on provider id. Disabling OpenAI storage reduces accidental retention of user prompts on shared org accounts. Zero SDK retries keep latency predictable: mmc handles timeouts at the runner layer instead of stacking hidden retries.

Recorded fixtures document edge cases (refusals, truncations, missing terminal events) without billing live APIs in CI.

## Tests to run

Anthropic adapter replays:

```bash
uv run pytest tests/contract/test_anthropic_adapter.py -q
```

OpenAI adapter replays:

```bash
uv run pytest tests/contract/test_openai_adapter.py -q
```

Combined filter:

```bash
uv run pytest tests/contract -k "anthropic or openai" -q
```
