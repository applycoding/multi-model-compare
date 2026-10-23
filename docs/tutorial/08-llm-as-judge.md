# LLM-as-judge

After contestants respond, mmc optionally sends an anonymised bundle to a judge model that must return structured scores against a YAML rubric.

## What these modules do

`src/mmc/judge/judge.py` orchestrates eligibility filtering, label assignment, provider calls with native structured output, retries on parse failures, and cost accounting for each attempt. Answers that failed, were blocked, or share the judge vendor are excluded unless settings allow self-judging or incomplete inclusion.

`src/mmc/judge/anonymise.py` shuffles model keys with a deterministic seed, assigns labels A through H, strips vendor and model-id terms from text, and builds labelled answer maps for the payload.

`src/mmc/judge/payload.py` and `schema_builder.py` construct the judge `ProviderRequest` including JSON schema for the verdict object. `src/mmc/judge/parser.py` validates parsed JSON strictly with Pydantic (`VerdictError` on mismatch).

Judge outcomes attach to the `RunRecord` with per-criterion scores, attempt history, and excluded-model reasons for the UI.

## Code excerpt

Self-judging guard and eligibility:

```python
# src/mmc/judge/judge.py
for ans in answers:
    if ans.status not in ("ok",) and not (settings.include_incomplete and ans.status == "incomplete"):
        excluded[ans.model.key] = f"status={ans.status}"
        continue
    if ans.model.vendor == judge_spec.vendor and not settings.allow_self_judging:
        excluded[ans.model.key] = "same vendor as judge"
        continue
    eligible.append(ans)
```

Deterministic anonymised labels:

```python
# src/mmc/judge/anonymise.py
rng = random.Random(seed)
rng.shuffle(keys)
labels = [chr(ord("A") + i) for i in range(len(keys))]
return {label: key for label, key in zip(labels, keys, strict=True)}
```

## Why this design matters

Anonymisation reduces bias from model branding in answers. Seeded shuffles make runs reproducible for tests and debugging while still hiding which label maps to which vendor in the judge prompt. Structured output lowers fragile free-form JSON parsing, and retry requests can narrow instructions after a `VerdictError`.

Excluding same-vendor judge/contestant pairs by default avoids obvious conflicts of interest unless operators opt in.

## Tests to run

Parser strictness:

```bash
uv run pytest tests/unit/test_judge_parser.py -q
```

End-to-end judge orchestration (mock providers):

```bash
uv run pytest tests/unit/test_judge.py -q
```

Anonymisation and payload helpers:

```bash
uv run pytest tests/unit/test_anonymise.py tests/unit/test_judge_payload.py -q
```
