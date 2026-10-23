# Live model IDs (configure before `MMC_PROFILE=live`)

This repository ships **illustrative** `model_id` strings in `src/mmc/defaults/models.yaml` so the architecture demo can compile without pinning to a single vendor release date. They are **not** guaranteed to exist on provider APIs.

Before calling live providers:

1. Copy defaults into your config dir (or set `MMC_CONFIG_DIR`).
2. For each model you use, set `model_id` to the identifier from the vendor's **current** public documentation.
3. Re-run contract tests or a single `mmc run` with one model to confirm the ID is accepted.

| Config key | Vendor docs (verify `model_id` here) |
|------------|--------------------------------------|
| `anthropic:*` | [Claude models overview](https://docs.anthropic.com/en/docs/about-claude/models) |
| `openai:*` | [OpenAI models](https://platform.openai.com/docs/models) |
| `google:*` | [Gemini models](https://ai.google.dev/gemini-api/docs/models/gemini) |
| `xai:*` | [xAI models](https://docs.x.ai/docs/models) |

The default names (for example `claude-sonnet-5-5`, `gpt-6.1-sol`, `gemini-3.8-flash`, `grok-4.7`) are **portfolio placeholders**. Replace them with whatever your API key can access; do not treat this repo as an authoritative model catalog.
