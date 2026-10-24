"""Transitions refuse invalid requests with a typed outcome and leave the record untouched."""

import pytest

from tests.support import AMBIGUOUS, CLEAR, FOCUS_QUESTION, at, project_from, question
from zigzag.domain.model import Project
from zigzag.domain.transitions import (
    Outcome,
    Rejected,
    defer_question,
    edit_statement,
    mark_reviewed,
    rely_on_assumption,
    remove_statement,
    select_option,
)

CLEAR_P = project_from(CLEAR, "clear brief")
AMB = project_from(AMBIGUOUS, "ambiguous brief")
FOCUS = question(AMB, FOCUS_QUESTION)


def selected() -> Project:
    out = select_option(AMB, at=at(1), question_id=FOCUS.id, option_id=FOCUS.options[0].id, reason=None)
    assert isinstance(out, Project)
    return out


def relied() -> Project:
    out = rely_on_assumption(CLEAR_P, at=at(1), item_id="a1")
    assert isinstance(out, Project)
    return out


def reviewed() -> Project:
    out = mark_reviewed(CLEAR_P, at=at(1), revision=1)
    assert isinstance(out, Project)
    return out


CASES: dict[str, tuple[Outcome, Rejected]] = {
    "unknown question": (
        select_option(AMB, at=at(1), question_id="q9", option_id="q9.1", reason=None),
        Rejected("not_found", "Question q9 does not exist."),
    ),
    "unknown option": (
        select_option(AMB, at=at(1), question_id=FOCUS.id, option_id="q1.9", reason=None),
        Rejected("not_found", "Option q1.9 does not exist."),
    ),
    "same option again": (
        select_option(selected(), at=at(2), question_id=FOCUS.id, option_id=FOCUS.options[0].id, reason=None),
        Rejected("invalid", "That option is already selected."),
    ),
    "defer unknown question": (
        defer_question(AMB, at=at(1), question_id="a1", reason=None),
        Rejected("not_found", "Question a1 does not exist."),
    ),
    "edit unknown statement": (
        edit_statement(CLEAR_P, at=at(1), item_id="i99", text="x"),
        Rejected("not_found", "Statement i99 does not exist."),
    ),
    "edit to empty": (
        edit_statement(CLEAR_P, at=at(1), item_id="i1", text="   "),
        Rejected("invalid", "A corrected statement cannot be empty. Remove it instead."),
    ),
    "edit unchanged": (
        edit_statement(CLEAR_P, at=at(1), item_id="i1", text=f" {CLEAR_P.intent[0].text} "),
        Rejected("invalid", "The statement is unchanged."),
    ),
    "remove unknown statement": (
        remove_statement(CLEAR_P, at=at(1), item_id="i99"),
        Rejected("not_found", "Statement i99 does not exist."),
    ),
    "rely on a non-assumption": (
        rely_on_assumption(CLEAR_P, at=at(1), item_id="n1"),
        Rejected("not_found", "Assumption n1 does not exist."),
    ),
    "rely twice": (
        rely_on_assumption(relied(), at=at(2), item_id="a1"),
        Rejected("invalid", "This assumption is already accepted."),
    ),
    "review a stale revision": (
        mark_reviewed(CLEAR_P, at=at(1), revision=0),
        Rejected(
            "conflict",
            "You reviewed revision 0, but the current revision is 1. Review the current handoff again.",
        ),
    ),
    "review twice": (
        mark_reviewed(reviewed(), at=at(2), revision=1),
        Rejected("invalid", "Revision 1 is already reviewed."),
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_rejected(name: str) -> None:
    outcome, expected = CASES[name]
    assert outcome == expected


def test_review_does_not_change_the_revision_and_editing_afterwards_does() -> None:
    r = reviewed()
    assert r.revision == CLEAR_P.revision
    edited = edit_statement(r, at=at(2), item_id="i1", text="Engineers find changes quickly.")
    assert isinstance(edited, Project)
    assert edited.revision == r.revision + 1
    assert edited.decisions[-1].summary.startswith("Corrected outcome:")
    removed = remove_statement(edited, at=at(3), item_id=next(i.id for i in edited.intent if i.kind == "nextStep"))
    assert isinstance(removed, Project)
    assert removed.decisions[-1].summary.startswith("Removed next step:")
