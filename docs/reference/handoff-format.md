# Handoff export format: `zigzag.handoff/v0`

**Status:** Current · **Implemented in:** [domain/handoff.py](../../apps/api/src/zigzag/domain/handoff.py), which is authoritative if this page disagrees.

Each saved revision has one handoff object. The API renders both the Markdown and the JSON export from it, so the two cannot disagree. A reviewed revision keeps fixed copies of both, exactly as they were at review time.

## JSON

| Field | Meaning |
| --- | --- |
| `format`, `projectId`, `title`, `revision` | Identity and version. `format` is `zigzag.handoff/v0`. |
| `status`, `reviewedAt`, `reviewer` | `draft` with nulls, or `reviewed` with a time and `local user`. A draft must not be treated as reviewed direction. |
| `intent[]` | One entry per kind, in a fixed order: `outcome`, `audience`, `direction`, `scope`, `exclusion`, `constraint`, `nextStep`. Each entry has its `kind`, a display `label`, and `items[]`; an empty list means not established. Each item has an `id`, its `text`, and its `basis`, which is the source wording or the selected option. |
| `openQuestions[]` | Questions not answered (`status: "open"`) or left open by the user (`"deferred"`). Each has its `text`, what the answer changes (`effect`), the options considered (`optionsConsidered`), what leaving the question open means (`deferEffect`, or null), and its `basis`. |
| `assumptions[]` | Always `support: "untested"`. `reliance` records whether the user accepted the assumption for the next step: `accepted for the next step` or `not accepted`. |
| `neededLater[]` | Inputs a later step needs that do not block this one, each with its `effect` and `basis`. |
| `decisions[]` | The append-only history, described below. |
| `sources[]` | The user's own text, with its `kind` (`brief` or `reply`), and the model or fixture that read it (`interpretedBy`). |

Each `decisions[]` entry has an `id` and an `action` (`brief`, `reply`, `select`, `defer`, `edit`, `remove`, or `rely`). It records what was decided (`summary`), when (`at`), why (`reason`, null if no reason was given), and which source wording it came from (`sourceWording`, or null).

- `supersededBy` names the decision that replaced this one entirely, or is null.
- `partlySupersededBy` is present only when a later decision replaced part of this one. For example, a reply left a question open and the user answered it later; the statements from that reply stay current. Each element names the item (`itemId`, `itemText`) and the decision that replaced it (`by`).

## Markdown

The Markdown export has the same sections, in the same order, under a status line. The status line reads either `DRAFT. Revision N has not been reviewed.` or `Reviewed. Revision N, reviewed <YYYY-MM-DD HH:MM> UTC by local user.` A draft also says that it may change and must not be treated as reviewed direction, and the footer repeats the format name, the project, and the status.
