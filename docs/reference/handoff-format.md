# Handoff export format: `intent-harness.handoff/v0`

**Status:** Current · **Implemented in:** [domain/handoff.py](../../apps/api/src/intent_harness/domain/handoff.py), which is authoritative if this page disagrees.

Each saved revision has one handoff object. The API renders both the Markdown and the JSON export from it, so the two cannot disagree. A reviewed revision keeps fixed copies of both, exactly as they were at review time.

## JSON

| Field | Meaning |
| --- | --- |
| `format`, `projectId`, `title`, `revision` | Identity and version. |
| `status`, `reviewedAt`, `reviewer` | `draft` with nulls, or `reviewed` with a time and `local user`. A draft must not be treated as reviewed direction. |
| `intent[]` | One entry per kind, in a fixed order: outcome, audience, direction, scope, exclusion, constraint, next step. Each item has its `text` and its `basis`, which is the source wording or the selected option. An empty list means not established. |
| `openQuestions[]` | Questions not answered (`open`) or left open by the user (`deferred`), with the options considered and what leaving the question open means. |
| `assumptions[]` | Always `support: "untested"`. `reliance` records whether the user accepted the assumption for the next step. |
| `neededLater[]` | Inputs a later step needs that do not block this one. |
| `decisions[]` | The append-only history, described below. |
| `sources[]` | The user's own text, with the model or fixture that read it. |

Each `decisions[]` entry records what was decided, when, why (if a reason was given), and which source wording it came from:

- `supersededBy` names the decision that replaced this one entirely.
- `partlySupersededBy` is present only when a later decision replaced part of this one. For example, a reply left a question open and the user answered it later. The statements from that reply stay current.

`partlySupersededBy` was added during the migration. The field is optional and additive, and records that never had a partial supersession export exactly as before.

## Markdown

The Markdown export has the same sections, in the same order, under a status line. The status line reads either `DRAFT. Revision N has not been reviewed.` or `Reviewed. Revision N, reviewed <time> by local user.` The footer repeats the format name, the project, and the status.
