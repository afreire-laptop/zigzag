"""The contract for model output. The model only proposes; nothing here writes state.

A response must pass three separate checks before any transition runs:
1. structure: it parses and matches `RawProposal`;
2. source text: every quote appears in the user's wording and every reference resolves;
3. framing: an extracted commitment is not hedged, conditional, a suggestion, or negated in context.
Passing them does not establish faithful interpretation; that remains a human judgment.
"""

import json
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from pydantic.alias_generators import to_camel

from intent_harness.domain.model import IntentKind, OpenItemKind, Project, Statement
from intent_harness.domain.text import Hedge, hedge_around, normalize_for_match, quote_found

Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Text400 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
Text600 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class _Raw(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True, frozen=True)


class ProposedStatement(_Raw):
    kind: IntentKind
    text: Annotated[Text400, Field(description="The statement that would be recorded if the user selects this option.")]


class Extraction(_Raw):
    kind: IntentKind
    text: Annotated[Text400, Field(description="Concise restatement of the quote. Adds no meaning.")]
    quote: Annotated[Text600, Field(description="Exact contiguous excerpt copied from NEW USER TEXT.")]


class Resolution(_Raw):
    question_id: Annotated[str, Field(description="Id of an existing question the reply addresses.")]
    status: Literal["answered", "deferred"]
    quote: Annotated[Text600, Field(description="Exact reply wording that answers it or leaves it open.")]


class ProposedOption(_Raw):
    label: Text80
    description: Annotated[Text300, Field(description="What this direction focuses on.")]
    tradeoff: Annotated[Text300, Field(description="What it costs or leaves unexamined.")]
    establishes: Annotated[tuple[ProposedStatement, ...], Field(min_length=1, max_length=4)]


class NewItem(_Raw):
    ref: Annotated[str, Field(min_length=1, max_length=20, description="Temporary reference such as new1.")]
    kind: OpenItemKind
    text: Text400
    basis: Annotated[Text400, Field(description="Where this comes from and what supports it. No invented evidence.")]
    quote: Annotated[
        Text600 | None,
        Field(description="Exact user wording this item comes from, or null for an agent inference."),
    ]
    effect: Annotated[Text400, Field(description="What would change, or how it affects the next step.")]
    options: Annotated[
        tuple[ProposedOption, ...],
        Field(
            max_length=5,
            description="Real alternatives for a question. Empty for assumptions and needed items.",
        ),
    ]
    defer_effect: Annotated[
        Text300 | None,
        Field(description="For a question: what leaving it open means for the next step. Otherwise null."),
    ]


class RawProposal(_Raw):
    """What the model must return. Every field is required; unknown values are null or empty."""

    extracted: Annotated[
        tuple[Extraction, ...],
        Field(
            max_length=40,
            description="What NEW USER TEXT explicitly states. Empty when there is no new user text.",
        ),
    ]
    resolutions: Annotated[
        tuple[Resolution, ...],
        Field(
            max_length=20,
            description="Existing questions the reply answers or explicitly leaves open. Empty for a brief.",
        ),
    ]
    new_items: Annotated[tuple[NewItem, ...], Field(max_length=12)]
    focus: Annotated[
        str | None,
        Field(
            description="The one question worth asking now: a new item ref or an existing open question id. "
            "Null when none is needed."
        ),
    ]


@dataclass(frozen=True)
class ProposalContext:
    mode: Literal["brief", "reply", "reassess"]
    new_text: str | None
    project: Project | None
    # The question the user chose to answer in their own words. Only it may be re-answered.
    target_question_id: str | None = None


@dataclass(frozen=True)
class ValidProposal:
    extracted: tuple[Extraction, ...]
    resolutions: tuple[Resolution, ...]
    new_items: tuple[NewItem, ...]
    # An existing open question id, a new item ref, or None.
    focus: str | None


@dataclass(frozen=True)
class Valid:
    proposal: ValidProposal
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Invalid:
    issues: tuple[str, ...]


type Validation = Valid | Invalid

_HEDGE_WORDS: dict[str, str] = {
    "uncertain": "uncertain",
    "conditional": "conditional",
    "suggestion": "a suggestion or question",
    "negated": "negated",
}


def _hedge_note(quote: str, hedge: Hedge, what: str) -> str:
    return (
        f"Not recorded {what}: “{quote}” reads as {_HEDGE_WORDS[hedge.kind]} in your text (“{hedge.marker}”). "
        "State it as an instruction to record it."
    )


def _schema_issues(error: ValidationError) -> tuple[str, ...]:
    return tuple(f"{'.'.join(str(part) for part in e['loc']) or 'response'}: {e['msg']}" for e in error.errors()[:6])


def validate_proposal(raw: str, ctx: ProposalContext) -> Validation:
    try:
        data: object = json.loads(raw)
    except ValueError:
        return Invalid(("The response was not valid JSON.",))
    try:
        proposal = RawProposal.model_validate(data)
    except ValidationError as error:
        return Invalid(_schema_issues(error))

    issues: list[str] = []
    notes: list[str] = []
    project = ctx.project

    if ctx.mode == "reassess":
        if proposal.extracted:
            issues.append("Statements were extracted without any new user text.")
        if proposal.resolutions:
            issues.append("Questions were resolved without any new user text.")
    if ctx.mode == "brief" and proposal.resolutions:
        issues.append("A new brief cannot resolve existing questions.")

    # An explicit instruction may establish intent only in the user's own words, framed as an instruction.
    extracted: list[Extraction] = []
    for e in proposal.extracted:
        if ctx.new_text is None or not quote_found(e.quote, ctx.new_text):
            issues.append(f"Quoted wording “{e.quote}” does not appear in your text.")
            continue
        hedge = hedge_around(e.quote, ctx.new_text, negation_expected=e.kind == "exclusion")
        if hedge:
            notes.append(_hedge_note(e.quote, hedge, "as your choice"))
            continue
        extracted.append(e)

    questions = {o.id: o for o in (project.open_items if project else ()) if o.kind == "question"}
    resolved: set[str] = set()
    resolutions: list[Resolution] = []
    for r in proposal.resolutions:
        q = questions.get(r.question_id)
        quote_ok = ctx.new_text is not None and quote_found(r.quote, ctx.new_text)
        if q is None:
            issues.append(f"Resolution refers to unknown question {r.question_id}.")
        elif q.status not in ("open", "deferred") and not _may_reanswer(project, q.id, ctx):
            issues.append(f"Question {r.question_id} is already {q.status}.")
        elif r.question_id in resolved:
            issues.append(f"Question {r.question_id} is resolved twice.")
        elif r.status == "deferred" and q.status == "deferred":
            issues.append(f"Question {r.question_id} is already left open.")
        if not quote_ok:
            issues.append(f"Resolution wording “{r.quote}” does not appear in your reply.")
        resolved.add(r.question_id)
        hedge = (
            hedge_around(r.quote, ctx.new_text, negation_expected=False)
            if quote_ok and ctx.new_text is not None and r.status == "answered"
            else None
        )
        if hedge:
            notes.append(_hedge_note(r.quote, hedge, "as an answer"))
            continue
        resolutions.append(r)

    all_text = [ctx.new_text or "", *(i.text for i in (project.inputs if project else ()))]
    existing_text = {
        normalize_for_match(o.text) for o in (project.open_items if project else ()) if o.status != "answered"
    }
    refs: set[str] = set()
    kept: list[NewItem] = []
    focus = proposal.focus
    for item in proposal.new_items:
        if item.ref in refs or item.ref in questions:
            issues.append(f"Reference {item.ref} is not unique.")
        refs.add(item.ref)
        if item.kind != "question" and (item.options or item.defer_effect is not None):
            issues.append(f"Only questions can have options ({item.ref}).")
        if item.quote is not None and not any(quote_found(item.quote, t) for t in all_text):
            issues.append(f"Quoted wording “{item.quote}” does not appear in any of your text.")
        if normalize_for_match(item.text) in existing_text:
            notes.append(f"Skipped a repeated open item: “{item.text}”.")
            if focus == item.ref:
                focus = None
            continue
        kept.append(item)

    if focus is not None:
        new_question = next((i for i in kept if i.ref == focus), None)
        existing = questions.get(focus)
        if new_question is not None:
            if new_question.kind != "question":
                issues.append(f"Focus {focus} is not a question.")
        elif existing is not None:
            if existing.status != "open" or focus in {r.question_id for r in resolutions}:
                issues.append(
                    f"Focus {focus} is not an open question; deferred and answered questions are not re-asked."
                )
        else:
            issues.append(f"Focus {focus} does not refer to any question.")

    if issues:
        return Invalid(tuple(issues))
    return Valid(
        ValidProposal(tuple(extracted), tuple(resolutions), tuple(kept), focus),
        tuple(notes),
    )


def _may_reanswer(project: Project | None, question_id: str, ctx: ProposalContext) -> bool:
    """An answered question may be re-answered only when the user replied to that question explicitly,
    and only if a selected option answered it. Words the user wrote earlier are corrected directly."""
    if project is None or ctx.mode != "reply" or ctx.target_question_id != question_id:
        return False
    q = project.question(question_id)
    answer = project.decision(q.decision_id) if q else None
    return q is not None and q.status == "answered" and answer is not None and answer.action == "select"


def proposed_statement(s: ProposedStatement) -> Statement:
    return Statement(kind=s.kind, text=s.text)
