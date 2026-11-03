# Upgrade guide

**Status:** Current · **Updated:** 2026-11-03

For a checkout that ran an earlier version: intent-harness, as zigzag was called before 2026-10-24, or the Express version that preceded the Python API. Its `.env` stops startup until you change it. Edit the file in place, because copying `.env.example` over it discards your settings.

## From intent-harness

The project was renamed from intent-harness to zigzag. An existing checkout needs two changes:

1. In `.env`, rename every `INTENT_` variable to `ZIGZAG_`, for example `INTENT_MODEL` to `ZIGZAG_MODEL`. Startup names every leftover `INTENT_` variable with its replacement. `INTENT_EFFORT` and `INTENT_MAX_TOKENS` are retired rather than renamed; see [From the Express version](#from-the-express-version).
2. To keep the projects in the old `intent-harness_intent-data` volume, copy them into the new `zigzag_data` volume before the first start. These commands stop the old stack without deleting its volume, create an empty `zigzag_data` volume, copy the old projects into it with the API image, and start zigzag; each runs only if the previous one succeeded:

   ```sh
   docker compose -p intent-harness down &&
   docker compose up --no-start --build &&
   docker volume inspect intent-harness_intent-data >/dev/null &&
   docker run --rm --user 0 --entrypoint sh -v intent-harness_intent-data:/from:ro -v zigzag_data:/to zigzag-api:local \
     -c 'if [ -n "$(ls -A /to)" ]; then echo "zigzag_data is not empty: nothing copied" >&2; exit 1; fi; cp -a /from/. /to/' &&
   docker compose up
   ```

   If the old volume does not exist, or `zigzag_data` already holds data, for example from an earlier start, nothing is copied and zigzag does not start. The old volume stays until you delete it with `docker volume rm intent-harness_intent-data`.

Exports now name their format `zigzag.handoff/v0`. Copies reviewed before the rename keep `intent-harness.handoff/v0`; see [the handoff format](../reference/handoff-format.md).

## From the Express version

An `.env` written for the earlier Express version does not start the API. Change each line as follows:

| Old line | Change |
| --- | --- |
| `ANTHROPIC_API_KEY=…` | Not read, and startup does not mention it. Live mode now goes through OpenRouter: add `ZIGZAG_OPENROUTER_API_KEY`, and delete the Anthropic key if nothing else uses it. |
| `INTENT_EFFORT=…` | Retired, and startup names it. Replace it with `ZIGZAG_REASONING_EFFORT`, set to `low`, `medium`, `high`, or empty; `xhigh` and `max` are not accepted. |
| `INTENT_MAX_TOKENS=…` | Retired, and startup names it. Replace it with `ZIGZAG_MAX_OUTPUT_TOKENS`. |
| `INTENT_MODEL=<Anthropic model id>` | Rename it to `ZIGZAG_MODEL`, set to an OpenRouter slug (`provider/model-name`) or empty. Startup checks the value even in fixture mode, but only after the names are fixed, and it reports only a pattern mismatch. |
| `INTENT_MODEL_MODE=…` | Rename it to `ZIGZAG_MODEL_MODE`. The values are unchanged: `fixture` or `live`. |

Then compare your file with `.env.example` for new optional settings.

## When it fails

Startup lists the problems it finds in three stages: names, then values, then combinations. A stage runs only after the earlier ones pass, so a start after you fix the names can report problems with the values. [Configuration](../../README.md#configuration) in the README describes each stage.
