# Overview

Multi-model-compare (mmc) is a Python application that sends one user prompt to several large language models at the same time, collects their answers, runs an LLM-as-judge pass with structured scoring, and stores an immutable snapshot of each run in SQLite. The same core logic powers a Typer-style CLI (`mmc`) and a local FastAPI web UI bound to loopback by default.

## What the system does

At the center is `CompareService` in `src/mmc/service.py`. It assigns a run id, computes a wall-clock deadline from config limits, fans out contestant calls through `run_contestants`, optionally calls `run_judge`, builds a `RunRecord`, redacts secrets, and persists via `RunRepository`. Vendor access goes through a small provider interface (`TextDelta` streaming events plus a terminal `StreamEnd`) so Anthropic, OpenAI, Google Gemini, xAI Grok, and a deterministic mock can share one runner.

Supporting packages split concerns cleanly: `core/` validates requests and runs concurrent tasks; `providers/` holds adapters and a registry; `judge/` anonymises answers and parses verdict JSON; `storage/` keeps full JSON snapshots plus a queryable summary index; `web/` exposes HTML and JSON APIs with CSRF and CSP.

## Code excerpt

The orchestration path is explicit: contestants first, judge second, then persistence.

```python
# src/mmc/service.py
answers = await run_contestants(
    resolved.contestants,
    resolved.requests,
    self._registry,
    self._clock,
    deadline,
    self._estimator,
    on,
    self._config.pricing,
)
if resolved.judge is not None:
    judge_out = await run_judge(
        resolved.prompt,
        answers,
        resolved.judge,
        resolved.judge_settings,
        self._config.rubric,
        resolved.seed,
        run_id,
        self._registry,
        self._clock,
        deadline,
        self._estimator,
        self._config.pricing,
        on,
    )
red = redact_record(record, self._redactor)
self._repo.save(red)
```

## Why this layout matters

A single service type avoids duplicating run lifecycle rules in the CLI and web layers. Both entry points call `resolve_request()` so validation, model selection, and vendor disclosure stay identical. Immutable snapshots make history trustworthy: exports and the UI read the same JSON the runner produced, without recomputing scores or costs later.

Mock-first defaults (`MMC_PROFILE=mock`) let CI and local development exercise the full pipeline without network calls, while live mode swaps in real SDK clients when API keys are present.

## Tests to run

Sanity-check environment wiring and settings parsing:

```bash
uv run pytest tests/unit/test_settings.py -q
```

Broader smoke of documentation and repo invariants:

```bash
uv run pytest tests/unit/test_docs.py -q
```
