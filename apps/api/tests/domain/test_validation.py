"""Model output is untrusted. Each structural, source, and reference problem rejects the whole proposal
before any state changes."""

import json
from typing import Any

import pytest

from tests.support import AMBIGUOUS, FOCUS_QUESTION, SOFTWARE_QUESTION, at, project_from, question, text
from zigzag.domain.proposal import Invalid, ProposalContext, Valid, validate_proposal
from zigzag.domain.transitions import Rejected, defer_question

AMB = project_from(AMBIGUOUS, "ambiguous brief")
FOCUS = question(AMB, FOCUS_QUESTION).id
SOFTWARE = question(AMB, SOFTWARE_QUESTION).id


def none(**update: Any) -> str:
    return json.dumps({"extracted": [], "resolutions": [], "newItems": [], "focus": None} | update)


def item(ref: str, kind: str = "question", **update: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ref": ref,
        "kind": kind,
        "text": f"Item {ref}?",
        "basis": "Agent inference; no supporting evidence supplied.",
        "quote": None,
        "effect": "Changes whom to interview.",
        "options": [],
        "deferEffect": None,
    }
    return base | update


def issues(raw: str, ctx: ProposalContext) -> tuple[str, ...]:
    result = validate_proposal(raw, ctx)
    assert isinstance(result, Invalid)
    return result.issues


REPLY = ProposalContext("reply", "Yes, the second one.", AMB)


@pytest.mark.parametrize(
    ("raw", "ctx", "expected"),
    [
        (
            none(resolutions=[{"questionId": FOCUS, "status": "answered", "quote": "brief"}]),
            ProposalContext("brief", "A brief.", None),
            "A new brief cannot resolve existing questions.",
        ),
        (
            none(
                resolutions=[
                    {"questionId": FOCUS, "status": "answered", "quote": "Yes"},
                    {"questionId": FOCUS, "status": "deferred", "quote": "Yes"},
                ]
            ),
            REPLY,
            f"Question {FOCUS} is resolved twice.",
        ),
        (
            none(resolutions=[{"questionId": FOCUS, "status": "answered", "quote": "No way"}]),
            REPLY,
            "does not appear in your reply",
        ),
        (none(newItems=[item("new1"), item("new1")]), REPLY, "Reference new1 is not unique."),
        (none(newItems=[item(FOCUS)]), REPLY, f"Reference {FOCUS} is not unique."),
        (none(newItems=[item("new1", quote="never written anywhere")]), REPLY, "does not appear in any of your text"),
        (none(newItems=[item("new1", kind="assumption")], focus="new1"), REPLY, "Focus new1 is not a question."),
        (none(focus="q42"), REPLY, "Focus q42 does not refer to any question."),
        (
            none(resolutions=[{"questionId": FOCUS, "status": "answered", "quote": "Yes"}], focus=FOCUS),
            REPLY,
            f"Focus {FOCUS} is not an open question",
        ),
        ('{"extracted": "nope"}', REPLY, "extracted"),
    ],
)
def test_rejected(raw: str, ctx: ProposalContext, expected: str) -> None:
    assert expected in " ".join(issues(raw, ctx))


def test_resolving_an_already_deferred_question_as_deferred_is_rejected() -> None:
    deferred = defer_question(AMB, at=at(1), question_id=FOCUS, reason=None)
    assert not isinstance(deferred, Rejected)
    raw = none(resolutions=[{"questionId": FOCUS, "status": "deferred", "quote": "Keep it open"}])
    assert issues(raw, ProposalContext("reply", "Keep it open.", deferred)) == (
        f"Question {FOCUS} is already left open.",
    )


def test_an_item_may_quote_earlier_user_text_and_repeats_lose_focus() -> None:
    earlier = "I don't know whether we need new software or a better process"
    repeated = item("new2", text=SOFTWARE_QUESTION)
    raw = none(newItems=[item("new1", kind="needed", quote=earlier), repeated], focus="new2")
    result = validate_proposal(raw, ProposalContext("reply", "Fine.", AMB))
    assert isinstance(result, Valid)
    assert [i.ref for i in result.proposal.new_items] == ["new1"]
    assert result.proposal.focus is None


def test_text_fields_are_trimmed_and_bounded() -> None:
    raw = none(newItems=[item("new1", text="   Padded question?   ")])
    result = validate_proposal(raw, ProposalContext("brief", text(AMBIGUOUS), None))
    assert isinstance(result, Valid)
    assert result.proposal.new_items[0].text == "Padded question?"
    too_long = none(newItems=[item("new1", text="x" * 401)])
    assert "newItems.0.text" in issues(too_long, ProposalContext("brief", "b", None))[0]
