# Tokens & pricing

## Modules
- `src/mmc/core/tokens.py` — char/tiktoken estimators, provider vs estimated usage
- `src/mmc/core/pricing.py` — effective-dated lookup, 6dp component rounding, Grok long-context tier

## Hand-calculated example
One input token at $0.50/M → `$0.000001` after `ROUND_HALF_UP` at six decimals.

## Checkpoint
```bash
uv run pytest tests/unit/test_tokens.py tests/unit/test_pricing.py -q
```

