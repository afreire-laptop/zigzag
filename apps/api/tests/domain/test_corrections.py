"""Correcting a selected answer: another selection, the user's own words, or leaving it open again.
The affected decision is superseded; history and unrelated decisions stay."""

import json

from tests.support import (
    AMBIGUOUS,
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
from zigzag.domain.handoff import HANDOFF_ADAPTER, Handoff, current_exports
from zigzag.domain.invariants import check_invariants
from zigzag.domain.model import Project
from zigzag.domain.proposal import Invalid, ProposalContext, Valid, validate_proposal
from zigzag.domain.transitions import Rejected, apply_user_text, defer_question, select_option


def ambiguous() -> Project:
    return project_from(AMBIGUOUS, "ambiguous brief")


def selected(p: Project, label: str = "Coordination during service") -> Project:
    q = question(p, FOCUS_QUESTION)
    out = select_option(p, at=at(1), question_id=q.id, option_id=option(p, FOCUS_QUESTION, label).id, reason=None)
    assert isinstance(out, Project)
    return out


def ok(outcome: Project | Rejected) -> Project:
    assert isinstance(outcome, Project), outcome
    assert check_invariants(outcome) == ()
    return outcome


def handoff(p: Project) -> Handoff:
    return HANDOFF_ADAPTER.validate_json(current_exports(p).json)


def test_leaving_a_selected_answer_open_withdraws_its_statements_and_supersedes_the_selection() -> None:
    p = selected(ambiguous())
    selection = p.decisions[-1]
    reopened = ok(defer_question(p, at=at(2), question_id=question(p, FOCUS_QUESTION).id, reason="Too early."))

    assert question(reopened, FOCUS_QUESTION).status == "deferred"
    assert not any(i.kind == "direction" for i in reopened.intent)
    deferral = reopened.decisions[-1]
    assert deferral.supersedes == (selection.id,)
    assert [(c.before, c.after) for c in deferral.changes] == [
        ("Investigate how incidents are coordinated during service.", None)
    ]
    assert deferral.summary.endswith("The earlier answer no longer applies.")
    assert reopened.decisions[: len(p.decisions)] == p.decisions  # append-only
    entry = handoff(reopened)["decisions"][1]
    assert (entry["id"], entry["supersededBy"]) == (selection.id, deferral.id)
    assert question(reopened, SOFTWARE_QUESTION).status == "open"  # unrelated question untouched


def test_a_deferred_answer_can_be_answered_again() -> None:
    p = selected(ambiguous())
    reopened = ok(defer_question(p, at=at(2), question_id=question(p, FOCUS_QUESTION).id, reason=None))
    again = ok(
        select_option(
            reopened,
            at=at(3),
            question_id=question(p, FOCUS_QUESTION).id,
            option_id=option(p, FOCUS_QUESTION, "Owner visibility afterwards").id,
            reason=None,
        )
    )
    assert again.decisions[-1].supersedes == (reopened.decisions[-1].id,)
    assert again.decisions[-1].summary.startswith("Selected")


def test_answering_a_selected_question_in_your_own_words_replaces_the_selection() -> None:
    p = selected(ambiguous())
    q = question(p, FOCUS_QUESTION)
    reply = "Owner follow-up first."
    raw = {
        "extracted": [{"kind": "direction", "text": "Investigate owner follow-up first.", "quote": reply}],
        "resolutions": [{"questionId": q.id, "status": "answered", "quote": reply}],
        "newItems": [],
        "focus": None,
    }
    proposal = validated(raw, ProposalContext("reply", reply, p, target_question_id=q.id))
    after = ok(
        apply_user_text(
            p, at=at(2), kind="reply", text=reply, question_id=q.id, proposal=proposal, interpreted_by="stub"
        )
    )
    directions = [i.text for i in after.intent if i.kind == "direction"]
    assert directions == ["Investigate owner follow-up first."]
    decision = after.decisions[-1]
    assert decision.supersedes == (p.decisions[-1].id,)
    assert [(c.before, c.after) for c in decision.changes] == [
        ("Investigate how incidents are coordinated during service.", None),
        (None, "Investigate owner follow-up first."),
    ]


def test_an_answered_question_cannot_be_re_answered_from_an_untargeted_reply() -> None:
    p = selected(ambiguous())
    q = question(p, FOCUS_QUESTION)
    reply = "Owner follow-up first."
    raw = json.dumps(
        {
            "extracted": [],
            "resolutions": [{"questionId": q.id, "status": "answered", "quote": reply}],
            "newItems": [],
            "focus": None,
        }
    )
    assert validate_proposal(raw, ProposalContext("reply", reply, p)) == Invalid(
        (f"Question {q.id} is already answered.",)
    )
    assert isinstance(validate_proposal(raw, ProposalContext("reply", reply, p, target_question_id=q.id)), Valid)


def test_leaving_open_a_question_answered_in_your_own_words_keeps_your_statements() -> None:
    p = ambiguous()
    q = question(p, FOCUS_QUESTION)
    reply_text = text("Short reply")
    proposal = validated(canned("short reply", p), ProposalContext("reply", reply_text, p, q.id))
    answered = ok(
        apply_user_text(
            p,
            at=at(1),
            kind="reply",
            text=reply_text,
            question_id=q.id,
            proposal=proposal,
            interpreted_by="stub",
        )
    )
    reopened = ok(defer_question(answered, at=at(2), question_id=q.id, reason=None))

    assert [i.text for i in reopened.intent if i.kind == "direction"] == ["Investigate coordination first."]
    assert reopened.decisions[-1].supersedes == ()
    reply_entry = handoff(reopened)["decisions"][1]
    assert reply_entry["supersededBy"] is None
    assert reply_entry.get("partlySupersededBy") == [
        {"itemId": q.id, "itemText": FOCUS_QUESTION, "by": reopened.decisions[-1].id}
    ]


def test_selecting_over_an_answer_in_your_own_words_is_refused() -> None:
    p = ambiguous()
    q = question(p, FOCUS_QUESTION)
    reply_text = text("Short reply")
    proposal = validated(canned("short reply", p), ProposalContext("reply", reply_text, p, q.id))
    answered = ok(
        apply_user_text(
            p,
            at=at(1),
            kind="reply",
            text=reply_text,
            question_id=q.id,
            proposal=proposal,
            interpreted_by="stub",
        )
    )
    out = select_option(
        answered,
        at=at(2),
        question_id=q.id,
        option_id=option(p, FOCUS_QUESTION, "Owner visibility afterwards").id,
        reason=None,
    )
    assert out == Rejected(
        "invalid", "This question was answered in your own words. Edit or remove those statements instead."
    )


def test_a_deferred_question_cannot_be_deferred_twice() -> None:
    p = ambiguous()
    q = question(p, FOCUS_QUESTION)
    once = ok(defer_question(p, at=at(1), question_id=q.id, reason=None))
    assert defer_question(once, at=at(2), question_id=q.id, reason=None) == Rejected(
        "invalid", "This question is already deferred."
    )
