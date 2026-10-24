"""Read models for the interface. They carry derived facts (statement basis, decision currency, permitted
actions) so the browser renders them without re-implementing domain rules."""

from typing import Literal

from pydantic import Field

from zigzag.domain.handoff import (
    HANDOFF_ADAPTER,
    build_handoff,
    current_exports,
    describe_source,
    diff_handoffs,
)
from zigzag.domain.history import later_status_changes
from zigzag.domain.model import (
    INTENT_KINDS,
    INTENT_LABELS,
    InputKind,
    IntentKind,
    OpenItem,
    Project,
    Value,
    is_reviewed,
    last_review,
    superseded_by,
)


class StatementView(Value):
    id: str
    text: str
    basis: str


class IntentSectionView(Value):
    kind: IntentKind
    label: str
    items: tuple[StatementView, ...]


class EstablishesView(Value):
    kind: IntentKind
    label: str
    text: str


class OptionView(Value):
    id: str
    label: str
    description: str
    tradeoff: str
    establishes: tuple[EstablishesView, ...]


class ResolutionView(Value):
    """How the question's current status was set: a selected option, the user's own words, or left open."""

    decision_id: str
    summary: str
    reason: str | None
    via: Literal["option", "ownWords", "leftOpen"]
    option_id: str | None


class QuestionActions(Value):
    select: bool
    answer_in_own_words: bool
    leave_open: bool


class QuestionView(Value):
    id: str
    text: str
    status: Literal["open", "deferred", "answered"]
    effect: str
    basis: str
    source_quote: str | None
    options: tuple[OptionView, ...]
    defer_effect: str | None
    proposed_by: str
    resolution: ResolutionView | None
    actions: QuestionActions


class AssumptionView(Value):
    id: str
    text: str
    basis: str
    effect: str
    relied: bool
    proposed_by: str


class NeededView(Value):
    id: str
    text: str
    basis: str
    effect: str


class PartlySupersededView(Value):
    item_id: str
    item_text: str
    by: str


class DecisionView(Value):
    id: str
    at: str
    revision: int
    action: str
    summary: str
    reason: str | None
    input_id: str | None
    superseded_by: str | None
    partly_superseded_by: tuple[PartlySupersededView, ...]


class InputView(Value):
    id: str
    kind: InputKind
    text: str
    at: str
    interpreted_by: str


class ProjectView(Value):
    id: str
    title: str
    revision: int
    status: Literal["draft", "reviewed"]
    created_at: str
    updated_at: str
    focus_id: str | None
    has_next_step: bool
    open_question_count: int
    intent: tuple[IntentSectionView, ...]
    questions: tuple[QuestionView, ...]
    assumptions: tuple[AssumptionView, ...]
    needed: tuple[NeededView, ...]
    decisions: tuple[DecisionView, ...]
    inputs: tuple[InputView, ...]


def _resolution(p: Project, q: OpenItem) -> ResolutionView | None:
    d = p.decision(q.decision_id) if q.status != "open" else None
    if d is None:
        return None
    via: Literal["option", "ownWords", "leftOpen"] = (
        "leftOpen" if q.status == "deferred" else "option" if d.action == "select" else "ownWords"
    )
    return ResolutionView(
        decision_id=d.id,
        summary=d.summary,
        reason=d.reason,
        via=via,
        option_id=d.option_id if via == "option" else None,
    )


def _actions(q: OpenItem, resolution: ResolutionView | None) -> QuestionActions:
    """Mirrors the transitions: an answer in the user's own words is corrected through its statements or by
    leaving the question open, never by silently selecting over it."""
    by_option = resolution is not None and resolution.via == "option"
    unanswered = q.status in ("open", "deferred")
    return QuestionActions(
        select=bool(q.options) and (unanswered or by_option),
        answer_in_own_words=unanswered or by_option,
        leave_open=q.status != "deferred",
    )


def _question(p: Project, q: OpenItem) -> QuestionView:
    resolution = _resolution(p, q)
    status: Literal["open", "deferred", "answered"] = (
        "answered" if q.status == "answered" else ("deferred" if q.status == "deferred" else "open")
    )
    return QuestionView(
        id=q.id,
        text=q.text,
        status=status,
        effect=q.effect,
        basis=q.basis,
        source_quote=q.source.quote if q.source else None,
        options=tuple(
            OptionView(
                id=o.id,
                label=o.label,
                description=o.description,
                tradeoff=o.tradeoff,
                establishes=tuple(
                    EstablishesView(kind=s.kind, label=INTENT_LABELS[s.kind], text=s.text) for s in o.establishes
                ),
            )
            for o in q.options
        ),
        defer_effect=q.defer_effect,
        proposed_by=q.proposed_by,
        resolution=resolution,
        actions=_actions(q, resolution),
    )


def project_view(p: Project) -> ProjectView:
    questions = tuple(_question(p, o) for o in p.open_items if o.kind == "question")
    return ProjectView(
        id=p.id,
        title=p.title,
        revision=p.revision,
        status="reviewed" if is_reviewed(p) else "draft",
        created_at=p.created_at,
        updated_at=p.updated_at,
        focus_id=p.focus_id,
        has_next_step=any(i.kind == "nextStep" for i in p.intent),
        open_question_count=sum(1 for q in questions if q.status != "answered"),
        intent=tuple(
            IntentSectionView(
                kind=kind,
                label=INTENT_LABELS[kind],
                items=tuple(
                    StatementView(id=i.id, text=i.text, basis=describe_source(p, i)) for i in p.intent if i.kind == kind
                ),
            )
            for kind in INTENT_KINDS
        ),
        questions=questions,
        assumptions=tuple(
            AssumptionView(
                id=o.id,
                text=o.text,
                basis=o.basis,
                effect=o.effect,
                relied=o.status == "relied",
                proposed_by=o.proposed_by,
            )
            for o in p.open_items
            if o.kind == "assumption"
        ),
        needed=tuple(
            NeededView(id=o.id, text=o.text, basis=o.basis, effect=o.effect) for o in p.open_items if o.kind == "needed"
        ),
        decisions=tuple(
            DecisionView(
                id=d.id,
                at=d.at,
                revision=d.revision,
                action=d.action,
                summary=d.summary,
                reason=d.reason,
                input_id=d.input_id,
                superseded_by=(by := superseded_by(p, d.id)),
                partly_superseded_by=()
                if by
                else tuple(
                    PartlySupersededView(item_id=c.item_id, item_text=c.item_text, by=c.by)
                    for c in later_status_changes(p, n)
                ),
            )
            for n, d in enumerate(p.decisions)
        ),
        inputs=tuple(
            InputView(id=i.id, kind=i.kind, text=i.text, at=i.at, interpreted_by=i.interpreted_by) for i in p.inputs
        ),
    )


class ExportView(Value):
    revision: int
    status: Literal["draft", "reviewed"]
    markdown: str
    json_copy: str = Field(alias="json")


class ReviewRef(Value):
    revision: int
    reviewed_at: str


class HandoffChangeView(Value):
    section: str
    added: tuple[str, ...]
    removed: tuple[str, ...]


class HandoffView(Value):
    project_id: str
    current: ExportView
    last_reviewed: ReviewRef | None
    reviews: tuple[ReviewRef, ...]
    changes: tuple[HandoffChangeView, ...] | None


def handoff_view(p: Project) -> HandoffView:
    last = last_review(p)
    changes = (
        tuple(
            HandoffChangeView(section=c.section, added=c.added, removed=c.removed)
            for c in diff_handoffs(HANDOFF_ADAPTER.validate_json(last.json_copy), build_handoff(p, review_at=None))
        )
        if last and last.revision != p.revision
        else None
    )
    exports = current_exports(p)
    return HandoffView(
        project_id=p.id,
        current=ExportView(
            revision=exports.revision, status=exports.status, markdown=exports.markdown, json=exports.json
        ),
        last_reviewed=ReviewRef(revision=last.revision, reviewed_at=last.reviewed_at) if last else None,
        reviews=tuple(ReviewRef(revision=r.revision, reviewed_at=r.reviewed_at) for r in p.reviews),
        changes=changes,
    )
