"""The project view carries the derived facts the UI shows, so the UI never re-implements domain rules."""

import pytest

from intent_harness.domain.model import Project
from intent_harness.domain.proposal import ProposalContext
from intent_harness.domain.transitions import (
    Rejected,
    apply_user_text,
    defer_question,
    edit_statement,
    mark_reviewed,
    rely_on_assumption,
    select_option,
)
from intent_harness.domain.view import handoff_view, project_view
from tests.support import (
    AMBIGUOUS,
    CLEAR,
    FOCUS_QUESTION,
    SOFTWARE_QUESTION,
    at,
    canned,
    option,
    project_from,
    question,
    text,
    validated,
)


def project(outcome: Project | Rejected) -> Project:
    assert isinstance(outcome, Project)
    return outcome


def states() -> list[Project]:
    """Projects covering every question state: open, deferred, answered by option, answered in words."""
    p = project_from(AMBIGUOUS, "ambiguous brief")
    q = question(p, FOCUS_QUESTION)
    chosen = project(select_option(p, at=at(1), question_id=q.id, option_id=q.options[0].id, reason=None))
    deferred = project(defer_question(p, at=at(1), question_id=q.id, reason=None))
    reply = text("Short reply")
    worded = apply_user_text(
        p,
        at=at(1),
        kind="reply",
        text=reply,
        question_id=q.id,
        proposal=validated(canned("short reply", p), ProposalContext("reply", reply, p, q.id)),
        interpreted_by="stub",
    )
    return [p, chosen, deferred, worded]


@pytest.mark.parametrize("p", states(), ids=["open", "selected", "deferred", "own-words"])
def test_question_actions_agree_with_the_transitions(p: Project) -> None:
    view = project_view(p)
    for qv in view.questions:
        q = question(p, qv.text)
        other = next((o for o in q.options if qv.resolution is None or o.id != qv.resolution.option_id), None)
        if other is not None:
            can_select = isinstance(
                select_option(p, at=at(9), question_id=q.id, option_id=other.id, reason=None), Project
            )
            assert qv.actions.select == can_select, qv.id
        assert qv.actions.leave_open == isinstance(defer_question(p, at=at(9), question_id=q.id, reason=None), Project)
        own_words_allowed = q.status in ("open", "deferred") or (
            qv.resolution is not None and qv.resolution.via == "option"
        )
        assert qv.actions.answer_in_own_words == own_words_allowed


def test_view_of_an_ambiguous_brief() -> None:
    p = project_from(AMBIGUOUS, "ambiguous brief")
    view = project_view(p)
    assert (view.status, view.revision, view.focus_id) == ("draft", 1, question(p, FOCUS_QUESTION).id)
    assert view.open_question_count == 2
    assert not view.has_next_step
    labels = [s.label for s in view.intent]
    assert labels[:2] == ["Desired outcome", "Audience and circumstances"]
    outcome = view.intent[0].items[0]
    assert outcome.basis == "From your brief: “Help independent restaurants deal with operational incidents”"
    focus = next(qv for qv in view.questions if qv.text == FOCUS_QUESTION)
    assert [o.label for o in focus.options] == ["Coordination during service", "Owner visibility afterwards"]
    assert focus.options[0].establishes[0].label == "Direction to pursue"
    software = next(qv for qv in view.questions if qv.text == SOFTWARE_QUESTION)
    assert software.source_quote == "I don't know whether we need new software or a better process"
    assert view.assumptions[0].relied is False


def test_view_marks_resolution_supersession_and_reliance() -> None:
    p = project_from(AMBIGUOUS, "ambiguous brief")
    q = question(p, FOCUS_QUESTION)
    first = project(
        select_option(
            p,
            at=at(1),
            question_id=q.id,
            option_id=option(p, FOCUS_QUESTION, "Coordination during service").id,
            reason="Busy.",
        )
    )
    second = project(defer_question(first, at=at(2), question_id=q.id, reason=None))
    relied = project(
        rely_on_assumption(second, at=at(3), item_id=next(o.id for o in p.open_items if o.kind == "assumption"))
    )
    view = project_view(relied)
    focus = next(qv for qv in view.questions if qv.id == q.id)
    assert focus.resolution is not None
    assert (focus.resolution.via, focus.resolution.decision_id) == ("leftOpen", second.decisions[-1].id)
    assert view.decisions[1].superseded_by == second.decisions[-1].id
    assert view.decisions[1].reason == "Busy."
    assert view.assumptions[0].relied is True
    assert view.inputs[0].kind == "brief"


def test_handoff_view_lists_changes_since_the_last_review() -> None:
    p = project_from(CLEAR, "clear brief")
    reviewed = project(mark_reviewed(p, at=at(1), revision=1))
    assert project_view(reviewed).status == "reviewed"
    unchanged = handoff_view(reviewed)
    assert unchanged.current.status == "reviewed"
    assert unchanged.changes is None
    item = reviewed.intent[0]
    edited = project(edit_statement(reviewed, at=at(2), item_id=item.id, text="Engineers find changes quickly."))
    view = handoff_view(edited)
    assert view.current.status == "draft"
    assert view.last_reviewed is not None
    assert view.last_reviewed.revision == 1
    assert [r.revision for r in view.reviews] == [1]
    assert view.changes is not None
    assert view.changes[0].section == "Desired outcome"
    assert view.changes[0].added == ("Engineers find changes quickly.",)
