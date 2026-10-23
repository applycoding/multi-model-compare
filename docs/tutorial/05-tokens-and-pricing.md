# Tokens and pricing

mmc separates **token measurement** (what the provider reported versus what we estimate) from **cost calculation** (effective-dated price rows with conservative rounding).

## What these modules do

`src/mmc/core/tokens.py` defines `TokenEstimator` with modes `auto`, `tiktoken`, or `chars`. Auto tries `tiktoken` encoding `o200k_base` and falls back to `ceil(len/4)` when tiktoken is unavailable. `resolve_usage()` prefers provider counts from `StreamEnd.usage` but marks fields as `estimated` when missing.

`src/mmc/core/pricing.py` loads rows from the validated `PricingTable` in config. `compute_cost()` picks base or long-context tier when input tokens exceed configured thresholds (notably for Grok), applies per-million token rates, and rounds each USD component to six decimal places with `ROUND_HALF_UP`. Notes flag estimated tokens, xAI reasoning billing uncertainty, and "from" pricing tiers.

Totals across answers and judge attempts use `sum_costs()` so the CLI and UI show one subtotal with explicit estimated/unknown flags. In **mock** profile, `apply_profile_honesty()` in `src/mmc/honesty.py` stores displayed USD as zero and sets `pricing_disclosure` to `example_pricing_mock` on each `RunRecord` so API and UI never imply real billing.

## Code excerpt

Estimation fallback:

```python
# src/mmc/core/tokens.py
def estimate(self, text: str) -> tuple[int, str]:
    if self._encoding is not None and self._mode != "chars":
        return len(self._encoding.encode(text)), self._estimator_name
    return max(1, math.ceil(len(text) / 4)) if text else 0, "chars/4"
```

Cost rounding and tier selection:

```python
# src/mmc/core/pricing.py
if entry.long_context and usage.input_tokens > entry.long_context.above_input_tokens:
    tier = "long_context"
    in_price = entry.long_context.input_per_mtok
input_usd = _q(Decimal(usage.input_tokens) * in_price / Decimal(1_000_000))
```

## Why this design matters

Provider usage fields are sometimes absent on partial streams or certain error paths. Estimating from text keeps cost columns populated while `Cost.status` stays honest (`estimated` vs `known`). Fixed six-decimal quantization makes unit tests and scenario golden files reproducible across platforms.

Long-context tier logic lives in one function so adapter authors only supply token counts, not billing policy.

## Tests to run

Token estimation and usage resolution:

```bash
uv run pytest tests/unit/test_tokens.py -q
```

Pricing tables, rounding, and Grok tier notes:

```bash
uv run pytest tests/unit/test_pricing.py -q
```

Scenario tests assert mock-profile subtotals stay at zero while `tests/unit/test_pricing.py` checks hand-computed rates against `compute_cost()` using fixture pricing tables.
