# Scenario & e2e

## Tests
- `tests/scenario/test_long_session.py` — 18-step seeded session vs hand-calculated `EXPECTED_STEPS`
- `tests/e2e/test_smoke.py` — real `mmc serve` + Playwright in mock mode
- `tests/fixtures/recorded/` — synthetic vendor fixtures (not live API)

## Golden file
`golden_final_state.json` is checked in CI; regenerate only with `MMC_UPDATE_GOLDEN=1` locally.

## Checkpoint
```bash
uv run pytest tests/scenario tests/e2e -q
```

