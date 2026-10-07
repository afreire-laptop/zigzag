# Live-model evaluation protocol

**Status:** Current · **Updated:** 2026-10-06 · **Run records:** [live-model-observations.md](live-model-observations.md)

Live observations are kept separate from the deterministic tests. A schema-valid response is necessary, but it does not show that a reading is faithful. Each live run needs a human judgment, recorded with its reason in the run records.

## Running

`pnpm eval --budget-usd N --max-calls N [--repeats N] [--cases a,b]` runs the evaluation cases in [apps/api/evals/cases.py](../../apps/api/evals/cases.py) through the configured OpenRouter model, using the app's own validation and state transitions. Every run spends money, so it is never part of CI. The cases are:

- the journey briefs and two paraphrases;
- the detailed, short, and deferring replies;
- choose-then-reassess and defer-then-reassess;
- a reply chained to the model's own reading;
- four negative controls: negation, uncertainty, a conditional, and a suggestion.

For each attempt, the runner records:

- the requested and served model, and the provider;
- the prompt version;
- schema validity and validation issues;
- the result of each mechanical check;
- latency;
- the number of requests submitted, including automatic retries;
- the reported cost, or *unknown*. It is unknown when any request might have been charged without returning an answer, and the run then stops;
- failures.

A case whose dependency failed is reported as blocked, never dropped. The summary that the runner writes to `observations/` lists each case's pass and fail criteria, and leaves the human verdict empty. Raw output in `observations/` is git-ignored.

## What still has to be shown with a real call

- **Structured outputs.** Each intended model family, behind the OpenRouter route chosen with `provider.require_parameters`, must honour the strict `json_schema` response format.
- **Response metadata.** The served model, the provider, `finish_reason`, and usage including `cost` must arrive as the adapter expects.
- **Errors.** The real 402, 404 (no route for the required parameters), 429, and 503 responses must match the adapter's mapping. The adapter retries 429 and 503 automatically because OpenRouter documents them as rejections made before any model ran.
- **Ambiguous failures.** The adapter does not repeat a request that timed out after it was sent, so a charge for it is possible. Whether OpenRouter's activity page shows that charge has not been checked.

Stubbed-transport tests cannot establish any of these. Fixture output is not model evidence.

## Before regular live use

Implement [idempotent model starts](../specs/idempotent-model-starts.md) first. Until then, a lost `202` response or a resubmitted brief can start a second paid call.

## Recording a run

Add a row to the status table and a record in [live-model-observations.md](live-model-observations.md), using [the run template](../templates/evaluation-run.md): the observations file, each scenario, pass or fail, and one or two sentences of rationale. Commit only reviewed and sanitized excerpts, never raw responses.
