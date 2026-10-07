"""Each invariant detects the damage it names. A violation blocks the save, or marks a file unreadable."""

from collections.abc import Callable

import pytest

from intent_harness.domain.invariants import check_invariants
from intent_harness.domain.model import OptionSource, Project, QuoteSource
from intent_harness.domain.transitions import Rejected, defer_question, mark_reviewed, select_option
from tests.support import AMBIGUOUS, CLEAR, FOCUS_QUESTION, at, project_from, question


def ok(outcome: Project | Rejected) -> Project:
    assert isinstance(outcome, Project)
    return outcome


CLEAR_P = project_from(CLEAR, "clear brief")
AMB = project_from(AMBIGUOUS, "ambiguous brief")
FOCUS = question(AMB, FOCUS_QUESTION)
SELECTED = ok(select_option(AMB, at=at(1), question_id=FOCUS.id, option_id=FOCUS.options[0].id, reason=None))
REVIEWED = ok(mark_reviewed(CLEAR_P, at=at(1), revision=1))
REOPENED = ok(defer_question(SELECTED, at=at(2), question_id=FOCUS.id, reason=None))


def first_intent(p: Project, **update: object) -> Project:
    return p.model_copy(update={"intent": (p.intent[0].model_copy(update=update), *p.intent[1:])})


def focus_item(p: Project, **update: object) -> Project:
    items = tuple(o.model_copy(update=update) if o.id == FOCUS.id else o for o in p.open_items)
    return p.model_copy(update={"open_items": items})


def review(p: Project, **update: object) -> Project:
    return p.model_copy(update={"reviews": (p.reviews[0].model_copy(update=update),)})


CASES: dict[str, tuple[Callable[[], Project], str]] = {
    "duplicate ids": (lambda: first_intent(CLEAR_P, id="s1"), "Duplicate ids."),
    "intent edited without a decision": (
        lambda: first_intent(CLEAR_P, text="Silently changed."),
        "disagrees with its decisions",
    ),
    "intent with no decision": (
        lambda: CLEAR_P.model_copy(
            update={
                "decisions": (CLEAR_P.decisions[0].model_copy(update={"changes": CLEAR_P.decisions[0].changes[1:]}),)
            }
        ),
        "has no decision",
    ),
    "intent points to the wrong decision": (
        lambda: first_intent(CLEAR_P, decision_id="d9"),
        "points to the wrong decision",
    ),
    "quote missing from its source": (
        lambda: first_intent(CLEAR_P, source=QuoteSource(input_id="s1", quote="words never written")),
        "quote is not in its source",
    ),
    "option that is not the current answer": (
        lambda: first_intent(SELECTED, source=OptionSource(question_id=FOCUS.id, option_id=FOCUS.options[1].id)),
        "not the current answer",
    ),
    "open item with a decision": (lambda: focus_item(AMB, decision_id="d1"), "has a decision"),
    "status without its decision": (
        lambda: focus_item(AMB, status="answered", decision_id="d1"),
        "status has no matching decision",
    ),
    "status resting on a superseded decision": (
        lambda: focus_item(REOPENED, status="answered", decision_id=SELECTED.decisions[-1].id),
        "rests on superseded decision",
    ),
    "open item quote missing": (
        lambda: AMB.model_copy(
            update={
                "open_items": tuple(
                    o.model_copy(update={"source": o.source.model_copy(update={"quote": "never said"})})
                    if o.source
                    else o
                    for o in AMB.open_items
                )
            }
        ),
        "Open item q2 quote is not in its source.",
    ),
    "focus on a non-question": (lambda: AMB.model_copy(update={"focus_id": "a1"}), "Focus is not an open question."),
    "review of a future revision": (lambda: review(REVIEWED, revision=5), "Review of 5 is invalid."),
    "review copy that is not JSON": (lambda: review(REVIEWED, json_copy="{oops"), "is not JSON"),
    "review copy for another revision": (
        lambda: review(REVIEWED, json_copy='{"revision": 2, "status": "reviewed"}'),
        "does not match its revision",
    ),
    "unlabeled review Markdown": (
        lambda: review(REVIEWED, markdown="# no label"),
        "Review Markdown for 1 is unlabeled.",
    ),
    "decision from a future revision": (
        lambda: CLEAR_P.model_copy(update={"decisions": (CLEAR_P.decisions[0].model_copy(update={"revision": 3}),)}),
        "Decision d1 is from a future revision.",
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_invariant_detects_damage(name: str) -> None:
    damaged, expected = CASES[name]
    problems = " ".join(check_invariants(damaged()))
    assert expected in problems


@pytest.mark.parametrize(
    "p", [CLEAR_P, AMB, SELECTED, REVIEWED, REOPENED], ids=["clear", "ambiguous", "selected", "reviewed", "reopened"]
)
def test_valid_records_have_no_problems(p: Project) -> None:
    assert check_invariants(p) == ()
