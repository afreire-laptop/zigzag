# Live-model evaluation protocol

**Status:** Current · **Updated:** 2026-11-03 · **Evaluation records:** [live-model-observations.md](live-model-observations.md)

Live observations are kept separate from the deterministic tests. A schema-valid response is necessary, but it does not show that a reading is faithful, so each live run needs a human judgment, recorded with its reason in the evaluation records.

## Running

```sh
pnpm eval --budget-usd N --max-calls N [--repeats N] [--cases a,b]
```

This runs the evaluation cases in [apps/api/evals/cases.py](../../apps/api/evals/cases.py) through the configured OpenRouter model, using the app's own validation and state transitions. For example, `pnpm eval --budget-usd 2 --max-calls 40 --repeats 2` runs every case twice. Every run spends money, so it is never part of CI.

The run refuses to start without `--budget-usd` and `--max-calls`. It counts every request it submits, including automatic retries, and stops if any request's cost is unknown, including a request that timed out after it was sent.

It needs `ZIGZAG_MODEL_MODE=live`, `ZIGZAG_OPENROUTER_API_KEY`, and `ZIGZAG_MODEL`, read from the shell or the repository's `.env`; the shell wins. To evaluate another model without editing `.env`, run `ZIGZAG_MODEL=provider/other-model pnpm eval …`. A variable left exported from an earlier session also wins over `.env`, and the summary's heading names the model the run requested.

`--cases` takes case ids, and the run covers every case when it is omitted:

| Cases | What they cover |
| --- | --- |
| `clear-brief`, `ambiguous-brief`, `paraphrased-brief`, `second-paraphrase` | The journey briefs, and two paraphrases of the ambiguous one. |
| `detailed-reply`, `short-reply`, `deferring-reply` | The detailed, short, and deferring replies. |
| `select-then-reassess`, `defer-then-reassess` | Reassessment after the user selects an option or leaves the question open. |
| `reply-to-live-brief` | A reply chained to the model's own reading of the ambiguous brief. |
| `negation-control`, `uncertainty-control`, `conditional-control`, `suggestion-control` | Four negative controls: negation, uncertainty, a conditional, and a suggestion. |

## What each attempt records

- the requested and served model, and the provider;
- the prompt version;
- schema validity and validation issues;
- the result of each mechanical check;
- latency;
- the number of requests submitted, including automatic retries;
- the reported cost, or *unknown* when any request might have been charged without returning an answer;
- failures.

A case whose dependency failed is reported as blocked, and a case the budget stopped as `skipped-budget`; neither is dropped.

## Judging

The runner writes the raw results and a summary to the git-ignored `observations/`. The summary lists each case's pass and fail criteria, and leaves the human verdict empty. Mechanical checks catch what a rule can catch; whether a reading is faithful stays a human judgment.

## What still has to be shown with a real call

- Structured outputs: each intended model family, behind the OpenRouter route chosen with `provider.require_parameters`, must honour the strict `json_schema` response format.
- Response metadata: the served model, the provider, `finish_reason`, and usage including `cost` must arrive as the adapter expects.
- Errors: the real 402, 404 (no route for the required parameters), 429, and 503 responses must match the adapter's mapping. The adapter retries 429 and 503 automatically because OpenRouter documents them as rejections made before any model ran.
- Ambiguous failures: the adapter does not repeat a request that timed out after it was sent, so a charge for it is possible. Whether OpenRouter's activity page shows that charge has not been checked.

Stubbed-transport tests cannot establish any of these. Fixture output is not model evidence.

## Before regular live use

Implement [idempotent model starts](../specs/idempotent-model-starts.md) first. Until then, a lost `202` response or a resubmitted brief can start a second paid call.

## Recording a run

Add a row to the status table and a record in [live-model-observations.md](live-model-observations.md), using [the run template](../templates/evaluation-run.md): the observations file, each scenario, pass or fail, and one or two sentences of rationale. Commit only reviewed and sanitized excerpts, never raw responses.
