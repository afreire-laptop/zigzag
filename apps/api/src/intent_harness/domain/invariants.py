"""Invariants checked when a record is read and before every save. A violation means a bug or a damaged
file, so nothing is written."""

from pydantic import BaseModel, ValidationError

from intent_harness.domain.model import Project, QuoteSource
from intent_harness.domain.text import quote_found


class _ReviewCopyHeader(BaseModel):
    revision: int
    status: str


def check_invariants(p: Project) -> tuple[str, ...]:
    problems: list[str] = []
    ids = [
        *(x.id for x in p.inputs),
        *(x.id for x in p.intent),
        *(x.id for x in p.open_items),
        *(x.id for x in p.decisions),
    ]
    if len(set(ids)) != len(ids):
        problems.append("Duplicate ids.")

    decisions = {d.id: d for d in p.decisions}

    # Intent must equal the result of the recorded changes: no decision without its intent update,
    # and no intent update without a decision.
    replayed: dict[str, str | None] = {}
    for d in p.decisions:
        for c in d.changes:
            replayed[c.item_id] = c.after
    current = {i.id: i.text for i in p.intent}
    problems += [f"Intent {i} disagrees with its decisions." for i, text in replayed.items() if text != current.get(i)]
    problems += [f"Intent {i} has no decision." for i in current if i not in replayed]

    for item in p.intent:
        d = decisions.get(item.decision_id)
        if d is None or not any(c.item_id == item.id and c.after == item.text for c in d.changes):
            problems.append(f"Intent {item.id} points to the wrong decision.")
        if isinstance(item.source, QuoteSource):
            source_input = p.input(item.source.input_id)
            if source_input is None or not quote_found(item.source.quote, source_input.text):
                problems.append(f"Intent {item.id} quote is not in its source.")
        else:
            q = p.item(item.source.question_id)
            answer = decisions.get(q.decision_id) if q and q.decision_id else None
            if q is None or q.status != "answered" or answer is None or answer.option_id != item.source.option_id:
                problems.append(f"Intent {item.id} comes from an option that is not the current answer.")

    superseded = {s for d in p.decisions for s in d.supersedes}
    for o in p.open_items:
        if o.status == "open":
            if o.decision_id is not None:
                problems.append(f"Open item {o.id} has a decision.")
        else:
            d = decisions.get(o.decision_id) if o.decision_id else None
            if d is None or not any(s.item_id == o.id and s.to == o.status for s in d.status_changes):
                problems.append(f"Open item {o.id} status has no matching decision.")
            elif d.id in superseded:
                problems.append(f"Open item {o.id} rests on superseded decision {d.id}.")
        if o.source and not any(i.id == o.source.input_id and quote_found(o.source.quote, i.text) for i in p.inputs):
            problems.append(f"Open item {o.id} quote is not in its source.")

    if p.focus_id is not None:
        f = p.item(p.focus_id)
        if f is None or f.kind != "question" or f.status != "open":
            problems.append("Focus is not an open question.")

    reviewed: set[int] = set()
    for r in p.reviews:
        if r.revision > p.revision or r.revision in reviewed:
            problems.append(f"Review of {r.revision} is invalid.")
        reviewed.add(r.revision)
        try:
            header = _ReviewCopyHeader.model_validate_json(r.json_copy)
        except ValidationError as error:
            unreadable = any(e["type"] == "json_invalid" for e in error.errors())
            problems.append(
                f"Review copy for {r.revision} {'is not JSON' if unreadable else 'does not match its revision'}."
            )
        else:
            if header.revision != r.revision or header.status != "reviewed":
                problems.append(f"Review copy for {r.revision} does not match its revision.")
        if f"Revision {r.revision}" not in r.markdown:
            problems.append(f"Review Markdown for {r.revision} is unlabeled.")
    problems += [f"Decision {d.id} is from a future revision." for d in p.decisions if d.revision > p.revision]
    return tuple(problems)
