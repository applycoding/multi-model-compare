# Recorded provider fixtures

These files are **synthetic-from-docs**: hand-built response bodies shaped like each vendor’s streaming APIs (Anthropic SSE, OpenAI Responses SSE, Google `generateContent` JSON, xAI gRPC-shaped replay objects). They are **not** captured from live API keys.

Maintainers may replace them with output from `scripts/record_fixtures.py` locally; CI always uses these synthetic fixtures.

Each fixture has a sibling `.meta.json` with `source`, `sdk_version`, and `date`.
