# Scenario and end-to-end testing

mmc's test pyramid combines fast unit tests, recorded vendor contracts, a long deterministic scenario session, and a Playwright smoke path against a real server.

## What these tests do

**Unit tests** under `tests/unit/` cover pricing math, request validation, judge parsing, security middleware, and adapter-adjacent logic with mocks.

**Contract tests** under `tests/contract/` replay files in `tests/fixtures/recorded/{anthropic,openai,google,xai}/` through production SDK clients and mocked transports, asserting normalized `StreamEnd` outcomes for ok, error, refusal, truncation, and missing-terminal fixtures.

**Scenario** `tests/scenario/test_long_session.py` drives eighteen sequential steps: CLI runs, web API calls, exports, deletes, and edge validations against hand-maintained `EXPECTED_STEPS` cost and status values. A golden file `tests/scenario/golden_final_state.json` captures final DB-visible state; CI fails on drift unless you regenerate locally with `MMC_UPDATE_GOLDEN=1`.

**E2E** `tests/e2e/test_smoke.py` starts `mmc serve` in mock profile and uses Playwright to load pages, submit a run, and verify basic UI wiring.

## Code excerpt

Golden update guard (pattern used in scenario tests):

```python
# tests/scenario/test_long_session.py (conceptual)
if os.environ.get("MMC_UPDATE_GOLDEN") == "1":
    # rewrite golden_final_state.json from computed state
    ...
else:
    assert computed == json.loads(golden_path.read_text())
```

E2e relies on shared fixtures in `tests/e2e/conftest.py` to bind an ephemeral port and terminate the server after tests.

## Why this design matters

Recorded fixtures let CI prove adapter parsing without live API keys or flaky network. The long scenario catches integration bugs that unit tests miss: SQLite migrations, export columns, supervisor limits, and cumulative pricing across many runs.

Playwright smoke ensures templates, static assets, and CSRF headers work together, not just in isolation with `TestClient`.

## Tests to run

Full scenario session (slowest integration):

```bash
uv run pytest tests/scenario/test_long_session.py -q
```

Browser e2e (requires Playwright browsers installed):

```bash
uv run pytest tests/e2e/test_smoke.py -q
```

Run both directories:

```bash
uv run pytest tests/scenario tests/e2e -q
```

Contract suite for adapter regressions:

```bash
uv run pytest tests/contract -q
```
