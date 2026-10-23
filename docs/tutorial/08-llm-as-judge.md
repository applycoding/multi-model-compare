# LLM-as-judge

## Modules
- `src/mmc/judge/judge.py` — build payload, call judge model, retries, persist attempts
- `src/mmc/judge/parser.py` — strict pydantic validation of verdict JSON
- `src/mmc/judge/anonymise.py` — labels A–H, shuffle seed, redact vendor terms

## Self-judging
Default: exclude judge vendor from scored answers unless `allow_self_judging`.

## Checkpoint
```bash
uv run pytest tests/unit/test_judge_parser.py tests/unit/test_judge.py tests/unit/test_anonymise.py -q
```

