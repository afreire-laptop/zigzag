"""Evaluation cases: journey variations and negative controls. These are evaluation data, not app behavior.

Each case reads one user text (or a reassessment) against a base state. Most bases are built from the fixture
journeys, so a case does not disappear when another case fails. A chained case names the case it depends on and
is reported as blocked when that case produced no valid result.

Mechanical checks look at the validated proposal and the resulting record. They catch what a rule can catch;
whether a reading is faithful stays a human judgment, recorded in docs/evaluations/live-model-observations.md."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from intent_harness.adapters.model.fixture import FixtureFile, load_fixtures
from intent_harness.domain.model import OpenItem, Project
from intent_harness.domain.proposal import ProposalContext, Valid, ValidProposal, validate_proposal
from intent_harness.domain.transitions import create_project, defer_question, select_option

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "journeys.json"
type Check = Callable[[ValidProposal, Project], bool]


@dataclass(frozen=True)
class Case:
    id: str
    mode: Literal["brief", "reply", "reassess"]
    judge: str
    text: str | None = None
    # A named base state, or "case:<id>" to continue from another case's live result.
    base: str | None = None
    checks: dict[str, Check] = field(default_factory=dict[str, Check])


def fixtures() -> FixtureFile:
    return load_fixtures(FIXTURES)


def fixture_text(label: str) -> str:
    texts = fixtures().texts
    found = next((t.text for t in (*texts.briefs, *texts.replies) if t.label == label), None)
    if found is None:
        raise KeyError(label)
    return found


PARAPHRASED = fixtures().texts.paraphrased_brief or ""
SECOND_PARAPHRASE = (
    "Family-run cafés lose time every time something breaks during a rush. We'd like dealing with that to be less "
    "chaotic, and the person who owns the place should know what went on. Unsure if this is a tool or a habit change."
)


def _questions(p: Project) -> list[OpenItem]:
    return [o for o in p.open_items if o.kind == "question"]


def _first_question(p: Project) -> OpenItem:
    return _questions(p)[0]


def _focus(p: Project) -> OpenItem | None:
    return p.item(p.focus_id) if p.focus_id else None


def _kinds(v: ValidProposal) -> set[str]:
    return {e.kind for e in v.extracted}


def _resolved(v: ValidProposal, p: Project, status: str) -> set[str]:
    texts: set[str] = set()
    for r in v.resolutions:
        item = p.item(r.question_id)
        if item is not None and r.status == status:
            texts.add(item.text)
    return texts


def _not_focused_on(p: Project, text: str) -> bool:
    focus = _focus(p)
    return focus is None or focus.text != text


def ambiguous_base() -> Project:
    """The ambiguous journey's brief, read by the fixture proposal: a deterministic base for reply cases."""
    brief = fixture_text("Ambiguous brief (journey 2)")
    rule = next(r for r in fixtures().rules if r.name == "ambiguous brief")
    result = validate_proposal(json.dumps(rule.respond[0]), ProposalContext("brief", brief, None))
    assert isinstance(result, Valid)
    return create_project(
        project_id="eval",
        at="2026-10-06T10:00:00.000Z",
        brief=brief,
        proposal=result.proposal,
        interpreted_by="fixture",
    )


def base_state(name: str) -> Project:
    p = ambiguous_base()
    focus = _first_question(p)
    if name == "ambiguous":
        return p
    if name == "ambiguous-selected":
        out = select_option(
            p, at="2026-10-06T10:01:00.000Z", question_id=focus.id, option_id=focus.options[0].id, reason=None
        )
    else:
        out = defer_question(p, at="2026-10-06T10:01:00.000Z", question_id=focus.id, reason=None)
    assert isinstance(out, Project)
    return out


FOCUS_QUESTION = "Which improvement should we investigate first?"


CASES: tuple[Case, ...] = (
    Case(
        "clear-brief",
        "brief",
        "No questions, or only one whose answer changes the design brief. Outcome, audience, direction, exclusions, "
        "and next step extracted with quotes. The untested time saving is an assumption; missing documents are needed "
        "later, not a blocker. Fails if it asks for persona, metric, platform, or alternatives.",
        text=fixture_text("Clear brief (journey 1)"),
        checks={
            "asks no questions": lambda v, p: not _questions(p),
            "records the next step": lambda v, p: "nextStep" in _kinds(v),
            "records the exclusions": lambda v, p: "exclusion" in _kinds(v),
            "keeps an untested assumption": lambda v, p: any(o.kind == "assumption" for o in p.open_items),
        },
    ),
    *(
        Case(
            case_id,
            "brief",
            "One focused question about what to investigate first, with real alternatives and trade-offs. No audience, "
            "channel, or software commitment as a statement. Fails if it settles the audience or solution, or asks "
            "several low-value questions.",
            text=brief_text,
            checks={
                "focuses one question": lambda v, p: _focus(p) is not None,
                "commits to no audience": lambda v, p: "audience" not in _kinds(v),
                "commits to no direction": lambda v, p: "direction" not in _kinds(v),
                "asks at most three questions": lambda v, p: len(_questions(p)) <= 3,
            },
        )
        for case_id, brief_text in (
            ("ambiguous-brief", fixture_text("Ambiguous brief (journey 2)")),
            ("paraphrased-brief", PARAPHRASED),
            ("second-paraphrase", SECOND_PARAPHRASE),
        )
    ),
    Case(
        "detailed-reply",
        "reply",
        "Volunteered direction, audience (as a discovery focus), exclusion, and next step recorded with quotes. The "
        "focus question is answered; the channel or software question is left open, not answered. Manager suitability "
        "is an untested assumption. Fails if it settles the channel or asks about technology.",
        text=fixture_text("Detailed reply"),
        base="ambiguous",
        checks={
            "answers the focus question": lambda v, p: FOCUS_QUESTION in _resolved(v, p, "answered"),
            "does not answer the software question": lambda v, p: (
                not any("software" in t for t in _resolved(v, p, "answered"))
            ),
            "records the audience in the user's words": lambda v, p: "audience" in _kinds(v),
        },
    ),
    Case(
        "short-reply",
        "reply",
        "'Coordination first.' answers the focus question and resolves nothing else. Fails if it rejects the reply for "
        "lacking detail or resolves other questions.",
        text=fixture_text("Short reply"),
        base="ambiguous",
        checks={
            "answers the focus question": lambda v, p: FOCUS_QUESTION in _resolved(v, p, "answered"),
            "resolves nothing else": lambda v, p: len(v.resolutions) == 1,
            "commits to no audience": lambda v, p: "audience" not in _kinds(v),
        },
    ),
    Case(
        "deferring-reply",
        "reply",
        "The focus question is left open; primary user and focus stay unset. Learning about current practice may "
        "become the next step. Fails if it picks an audience or focus anyway.",
        text=fixture_text("Defer reply"),
        base="ambiguous",
        checks={
            "leaves the focus question open": lambda v, p: FOCUS_QUESTION in _resolved(v, p, "deferred"),
            "commits to no audience or direction": lambda v, p: not ({"audience", "direction"} & _kinds(v)),
        },
    ),
    Case(
        "select-then-reassess",
        "reassess",
        "Any follow-up question would change whom to speak to or what to examine; otherwise no question. Fails if it "
        "re-asks the answered question or asks about technology.",
        base="ambiguous-selected",
        checks={"does not re-ask the answered question": lambda v, p: _not_focused_on(p, FOCUS_QUESTION)},
    ),
    Case(
        "defer-then-reassess",
        "reassess",
        "It does not re-ask the deferred question. The validator rejects that mechanically.",
        base="ambiguous-deferred",
        checks={"does not focus the deferred question": lambda v, p: _not_focused_on(p, FOCUS_QUESTION)},
    ),
    Case(
        "reply-to-live-brief",
        "reply",
        "Chained: the short reply against the model's own reading of the ambiguous brief. "
        "Same criteria as short-reply.",
        text=fixture_text("Short reply"),
        base="case:ambiguous-brief",
        checks={"resolves at most one question": lambda v, p: len(v.resolutions) <= 1},
    ),
    # Negative controls: wording that appears in the text but is not an instruction.
    Case(
        "negation-control",
        "brief",
        "'A mobile app' is excluded, never a direction. Interviews are the next step.",
        text="Nurses lose time at shift handover. We do not want a mobile app. "
        "The next step is interviews with nurses.",
        checks={"records no direction from the negation": lambda v, p: "direction" not in _kinds(v)},
    ),
    Case(
        "uncertainty-control",
        "brief",
        "The audience stays unestablished; the uncertainty may become a question or assumption.",
        text="Maybe night-shift nurses are the right audience, I'm not sure. Handover notes get lost between shifts.",
        checks={"records no audience": lambda v, p: "audience" not in _kinds(v)},
    ),
    Case(
        "conditional-control",
        "brief",
        "Analytics is not in scope; the condition may become a question.",
        text="Help clinics track missed appointments. If the budget allows, add analytics. Interviews come first.",
        checks={
            "records no conditional scope": lambda v, p: not any("analytic" in e.text.lower() for e in v.extracted)
        },
    ),
    Case(
        "suggestion-control",
        "brief",
        "A dashboard is a suggestion, not a direction.",
        text="Owners rarely hear about incidents. What about a dashboard for owners? "
        "I want to understand the problem first.",
        checks={
            "records no suggested direction": lambda v, p: not any("dashboard" in e.text.lower() for e in v.extracted)
        },
    ),
)
