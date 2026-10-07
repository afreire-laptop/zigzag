"""Deterministic transitions of the project record. Each takes a record and explicit inputs and returns a
new record or a `Rejected` outcome; nothing is mutated. A content change increments `revision`, which
leaves any earlier review behind. Model proposals arrive here only after `validate_proposal`."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from intent_harness.domain.handoff import render_exports
from intent_harness.domain.model import (
    Change,
    Decision,
    DecisionAction,
    Input,
    InputKind,
    IntentItem,
    ItemSource,
    OpenItem,
    Option,
    OptionSource,
    Project,
    QuoteSource,
    Review,
    StatusChange,
    is_reviewed,
)
from intent_harness.domain.proposal import Resolution, ValidProposal, proposed_statement
from intent_harness.domain.text import quote_found, title_from


@dataclass(frozen=True)
class Rejected:
    reason: Literal["not_found", "invalid", "conflict"]
    message: str


type Outcome = Project | Rejected


@dataclass
class _Draft:
    """Working copy used inside one transition. Never escapes it; `finish` returns a frozen record."""

    base: Project
    seq: dict[str, int] = field(init=False)
    inputs: list[Input] = field(init=False)
    intent: list[IntentItem] = field(init=False)
    open_items: list[OpenItem] = field(init=False)
    decisions: list[Decision] = field(init=False)
    reviews: list[Review] = field(init=False)
    focus_id: str | None = field(init=False)

    def __post_init__(self) -> None:
        self.seq = dict(self.base.seq)
        self.inputs = list(self.base.inputs)
        self.intent = list(self.base.intent)
        self.open_items = list(self.base.open_items)
        self.decisions = list(self.base.decisions)
        self.reviews = list(self.base.reviews)
        self.focus_id = self.base.focus_id

    def new_id(self, prefix: str) -> str:
        self.seq[prefix] = self.seq.get(prefix, 0) + 1
        return f"{prefix}{self.seq[prefix]}"

    def add_decision(
        self,
        at: str,
        action: DecisionAction,
        summary: str,
        *,
        input_id: str | None = None,
        question_id: str | None = None,
        option_id: str | None = None,
        reason: str | None = None,
        changes: Iterable[Change] = (),
        status_changes: Iterable[StatusChange] = (),
        supersedes: Iterable[str] = (),
    ) -> Decision:
        decision = Decision(
            id=self.new_id("d"),
            at=at,
            revision=self.base.revision + 1,
            action=action,
            summary=summary,
            input_id=input_id,
            question_id=question_id,
            option_id=option_id,
            reason=reason,
            changes=tuple(changes),
            status_changes=tuple(status_changes),
            supersedes=tuple(supersedes),
        )
        self.decisions.append(decision)
        return decision

    def set_status(self, item_id: str, status: Literal["answered", "deferred", "relied"], decision_id: str) -> None:
        self.open_items = [
            o.model_copy(update={"status": status, "decision_id": decision_id}) if o.id == item_id else o
            for o in self.open_items
        ]
        if self.focus_id == item_id:
            self.focus_id = None

    def finish(self, at: str, *, bump: bool = True) -> Project:
        return self.base.model_copy(
            update={
                "seq": tuple(self.seq.items()),
                "inputs": tuple(self.inputs),
                "intent": tuple(self.intent),
                "open_items": tuple(self.open_items),
                "focus_id": self.focus_id,
                "decisions": tuple(self.decisions),
                "reviews": tuple(self.reviews),
                "revision": self.base.revision + (1 if bump else 0),
                "updated_at": at,
            }
        )


def _quote(text: str) -> str:
    return f"“{text}”"


def _replaceable(p: Project, question: OpenItem | None) -> Decision | None:
    """The earlier decision a new answer replaces as a whole: only a selection or deferral about that one
    question. A reply that also recorded other statements stays current; its replaced part is derived."""
    d = p.decision(question.decision_id) if question and question.decision_id else None
    return d if d and d.action in ("select", "defer") else None


def _option_statements(p: Project, question_id: str) -> list[IntentItem]:
    return [i for i in p.intent if isinstance(i.source, OptionSource) and i.source.question_id == question_id]


def _withdrawn(items: Iterable[IntentItem]) -> list[Change]:
    return [Change(item_id=i.id, kind=i.kind, before=i.text, after=None) for i in items]


def _added(items: Iterable[IntentItem]) -> list[Change]:
    return [Change(item_id=i.id, kind=i.kind, before=None, after=i.text) for i in items]


def _input_id_for_quote(inputs: list[Input], quote: str, prefer: str | None) -> str | None:
    preferred = next((i for i in inputs if i.id == prefer), None) if prefer else None
    if preferred and quote_found(quote, preferred.text):
        return preferred.id
    return next((i.id for i in reversed(inputs) if quote_found(quote, i.text)), None)


def _add_proposal_items(
    d: _Draft, proposal: ValidProposal, proposed_by: str, new_input_id: str | None
) -> dict[str, str]:
    ref_to_id: dict[str, str] = {}
    for item in proposal.new_items:
        prefix = "q" if item.kind == "question" else "a" if item.kind == "assumption" else "n"
        item_id = d.new_id(prefix)
        ref_to_id[item.ref] = item_id
        input_id = _input_id_for_quote(d.inputs, item.quote, new_input_id) if item.quote else None
        d.open_items.append(
            OpenItem(
                id=item_id,
                kind=item.kind,
                text=item.text,
                basis=item.basis,
                effect=item.effect,
                source=ItemSource(input_id=input_id, quote=item.quote) if item.quote and input_id else None,
                options=tuple(
                    Option(
                        id=f"{item_id}.{n}",
                        label=o.label,
                        description=o.description,
                        tradeoff=o.tradeoff,
                        establishes=tuple(proposed_statement(s) for s in o.establishes),
                    )
                    for n, o in enumerate(item.options, start=1)
                ),
                defer_effect=item.defer_effect,
                status="open",
                decision_id=None,
                proposed_by=proposed_by,
            )
        )
    return ref_to_id


def _resolve_focus(focus: str | None, ref_to_id: dict[str, str]) -> str | None:
    return ref_to_id.get(focus, focus) if focus else None


def create_project(*, project_id: str, at: str, brief: str, proposal: ValidProposal, interpreted_by: str) -> Project:
    empty = Project(
        schema_version=1,
        id=project_id,
        title=title_from(brief),
        created_at=at,
        updated_at=at,
        revision=0,
        seq=(),
        inputs=(),
        intent=(),
        open_items=(),
        focus_id=None,
        decisions=(),
        reviews=(),
    )
    return apply_user_text(
        empty,
        at=at,
        kind="brief",
        text=brief,
        question_id=None,
        proposal=proposal,
        interpreted_by=interpreted_by,
    )


def _summarize_user_text(p: Project, kind: InputKind, statements: int, resolutions: Iterable[Resolution]) -> str:
    parts: list[str] = []
    if statements > 0:
        parts.append(f"recorded {statements} statement{'' if statements == 1 else 's'} in your words")
    for r in resolutions:
        q = p.item(r.question_id)
        parts.append(
            f"{'answered' if r.status == 'answered' else 'left open'} {_quote(q.text if q else r.question_id)}"
        )
    origin = "From your brief" if kind == "brief" else "From your reply"
    return f"{origin}: {'; '.join(parts)}."


def apply_user_text(
    p: Project,
    *,
    at: str,
    kind: InputKind,
    text: str,
    question_id: str | None,
    proposal: ValidProposal,
    interpreted_by: str,
) -> Project:
    """Record a brief or reply together with the model's validated reading of it."""
    d = _Draft(p)
    input_id = d.new_id("s")
    d.inputs.append(
        Input(id=input_id, kind=kind, text=text, at=at, question_id=question_id, interpreted_by=interpreted_by)
    )
    added = [
        IntentItem(
            id=d.new_id("i"),
            kind=e.kind,
            text=e.text,
            source=QuoteSource(input_id=input_id, quote=e.quote),
            decision_id="",
        )
        for e in proposal.extracted
    ]
    if added or proposal.resolutions:
        # Re-answering a question that a selected option answered withdraws that option's statements.
        withdrawn = [
            i
            for r in proposal.resolutions
            if (q := p.item(r.question_id)) and q.status == "answered"
            for i in _option_statements(p, q.id)
        ]
        supersedes = [rd.id for r in proposal.resolutions if (rd := _replaceable(p, p.item(r.question_id))) is not None]
        decision = d.add_decision(
            at,
            kind,
            _summarize_user_text(p, kind, len(added), proposal.resolutions),
            input_id=input_id,
            question_id=question_id,
            changes=[*_withdrawn(withdrawn), *_added(added)],
            status_changes=[StatusChange(item_id=r.question_id, to=r.status) for r in proposal.resolutions],
            supersedes=supersedes,
        )
        d.intent = [i for i in d.intent if i not in withdrawn]
        d.intent.extend(i.model_copy(update={"decision_id": decision.id}) for i in added)
        for r in proposal.resolutions:
            d.set_status(r.question_id, r.status, decision.id)
    ref_to_id = _add_proposal_items(d, proposal, interpreted_by, input_id)
    d.focus_id = _resolve_focus(proposal.focus, ref_to_id)
    return d.finish(at)


def apply_reassessment(p: Project, *, at: str, proposal: ValidProposal, proposed_by: str) -> Project:
    """Add agent proposals after a choice made through the interface. Never changes intent."""
    d = _Draft(p)
    ref_to_id = _add_proposal_items(d, proposal, proposed_by, None)
    d.focus_id = _resolve_focus(proposal.focus, ref_to_id)
    return d.finish(at, bump=bool(proposal.new_items))


def select_option(p: Project, *, at: str, question_id: str, option_id: str, reason: str | None) -> Outcome:
    q = p.question(question_id)
    if q is None:
        return Rejected("not_found", f"Question {question_id} does not exist.")
    option = next((o for o in q.options if o.id == option_id), None)
    if option is None:
        return Rejected("not_found", f"Option {option_id} does not exist.")
    previous = p.decision(q.decision_id)
    if q.status == "answered":
        if previous is None or previous.action != "select":
            return Rejected(
                "invalid",
                "This question was answered in your own words. Edit or remove those statements instead.",
            )
        if previous.option_id == option.id:
            return Rejected("invalid", "That option is already selected.")

    d = _Draft(p)
    # Replacing an earlier selection removes only the statements that selection established.
    replaced = _option_statements(p, q.id) if q.status == "answered" else []
    d.intent = [i for i in d.intent if i not in replaced]
    added = [
        IntentItem(
            id=d.new_id("i"),
            kind=s.kind,
            text=s.text,
            source=OptionSource(question_id=q.id, option_id=option.id),
            decision_id="",
        )
        for s in option.establishes
    ]
    verb = "Changed answer to" if previous is not None and previous.action == "select" else "Selected"
    replaceable = _replaceable(p, q)
    decision = d.add_decision(
        at,
        "select",
        f"{verb} {_quote(option.label)} for {_quote(q.text)}.",
        question_id=q.id,
        option_id=option.id,
        reason=reason,
        changes=[*_withdrawn(replaced), *_added(added)],
        status_changes=[StatusChange(item_id=q.id, to="answered")],
        supersedes=[replaceable.id] if replaceable else [],
    )
    d.intent.extend(i.model_copy(update={"decision_id": decision.id}) for i in added)
    d.set_status(q.id, "answered", decision.id)
    return d.finish(at)


def defer_question(p: Project, *, at: str, question_id: str, reason: str | None) -> Outcome:
    """Leave a question open. From an answered question this withdraws the answer: a selected option's
    statements are removed and that selection is superseded. Statements the user wrote stay."""
    q = p.question(question_id)
    if q is None:
        return Rejected("not_found", f"Question {question_id} does not exist.")
    if q.status == "deferred":
        return Rejected("invalid", "This question is already deferred.")
    d = _Draft(p)
    withdrawn = _option_statements(p, q.id) if q.status == "answered" else []
    replaceable = _replaceable(p, q) if q.status == "answered" else None
    d.intent = [i for i in d.intent if i not in withdrawn]
    summary = f"Left open: {_quote(q.text)}."
    if q.status == "answered":
        summary += " The earlier answer no longer applies."
    decision = d.add_decision(
        at,
        "defer",
        summary,
        question_id=q.id,
        reason=reason,
        changes=_withdrawn(withdrawn),
        status_changes=[StatusChange(item_id=q.id, to="deferred")],
        supersedes=[replaceable.id] if replaceable else [],
    )
    d.set_status(q.id, "deferred", decision.id)
    return d.finish(at)


def _kind_word(kind: str) -> str:
    return "next step" if kind == "nextStep" else kind


def edit_statement(p: Project, *, at: str, item_id: str, text: str) -> Outcome:
    item = next((i for i in p.intent if i.id == item_id), None)
    if item is None:
        return Rejected("not_found", f"Statement {item_id} does not exist.")
    new_text = text.strip()
    if not new_text:
        return Rejected("invalid", "A corrected statement cannot be empty. Remove it instead.")
    if new_text == item.text:
        return Rejected("invalid", "The statement is unchanged.")
    d = _Draft(p)
    decision = d.add_decision(
        at,
        "edit",
        f"Corrected {_kind_word(item.kind)}: {_quote(item.text)} → {_quote(new_text)}.",
        changes=[Change(item_id=item.id, kind=item.kind, before=item.text, after=new_text)],
    )
    d.intent = [
        i.model_copy(update={"text": new_text, "decision_id": decision.id}) if i.id == item.id else i for i in d.intent
    ]
    return d.finish(at)


def remove_statement(p: Project, *, at: str, item_id: str) -> Outcome:
    item = next((i for i in p.intent if i.id == item_id), None)
    if item is None:
        return Rejected("not_found", f"Statement {item_id} does not exist.")
    d = _Draft(p)
    d.add_decision(
        at,
        "remove",
        f"Removed {_kind_word(item.kind)}: {_quote(item.text)}.",
        changes=_withdrawn([item]),
    )
    d.intent = [i for i in d.intent if i.id != item.id]
    return d.finish(at)


def rely_on_assumption(p: Project, *, at: str, item_id: str) -> Outcome:
    """Accepting an assumption permits reliance on it; it stays untested."""
    a = next((o for o in p.open_items if o.id == item_id and o.kind == "assumption"), None)
    if a is None:
        return Rejected("not_found", f"Assumption {item_id} does not exist.")
    if a.status != "open":
        return Rejected("invalid", "This assumption is already accepted.")
    d = _Draft(p)
    decision = d.add_decision(
        at,
        "rely",
        f"Accepted for the next step (still untested): {_quote(a.text)}.",
        status_changes=[StatusChange(item_id=a.id, to="relied")],
    )
    d.set_status(a.id, "relied", decision.id)
    return d.finish(at)


def mark_reviewed(p: Project, *, at: str, revision: int) -> Outcome:
    """Review fixes a copy of exactly this revision. It is not a content change."""
    if revision != p.revision:
        return Rejected(
            "conflict",
            f"You reviewed revision {revision}, but the current revision is {p.revision}. "
            "Review the current handoff again.",
        )
    if is_reviewed(p):
        return Rejected("invalid", f"Revision {p.revision} is already reviewed.")
    copies = render_exports(p, review_at=at)
    d = _Draft(p)
    d.reviews.append(
        Review(
            revision=p.revision,
            reviewed_at=at,
            reviewer="local user",
            markdown=copies.markdown,
            json=copies.json,
        )
    )
    return d.finish(at, bump=False)
