"""Quotes appearing in the input do not by themselves authorize a commitment. Extractions framed as
uncertain, conditional, suggested, or negated in context stay proposals, with a visible note."""

import json

import pytest

from intent_harness.domain.model import IntentKind
from intent_harness.domain.proposal import ProposalContext, Valid, validate_proposal
from intent_harness.domain.text import hedge_around
from tests.support import AMBIGUOUS, FOCUS_QUESTION, project_from, question


def extract(text: str, kind: IntentKind, quote: str) -> Valid:
    raw = {
        "extracted": [{"kind": kind, "text": quote, "quote": quote}],
        "resolutions": [],
        "newItems": [],
        "focus": None,
    }
    result = validate_proposal(json.dumps(raw), ProposalContext("brief", text, None))
    assert isinstance(result, Valid)
    return result


@pytest.mark.parametrize(
    ("text", "kind", "quote", "framing"),
    [
        (
            "I don't know whether we need new software or a better process.",
            "direction",
            "we need new software",
            "uncertain",
        ),
        (
            "Maybe shift managers are the right audience.",
            "audience",
            "shift managers are the right audience",
            "uncertain",
        ),
        ("If owners want it, add weekly reporting.", "scope", "add weekly reporting", "conditional"),
        ("We could consider an SMS channel.", "direction", "an SMS channel", "uncertain"),
        ("What about a dashboard for owners?", "direction", "a dashboard for owners", "suggestion"),
        ("Focus on shift managers?", "audience", "shift managers", "suggestion"),
        ("For example, a shared checklist might help.", "direction", "a shared checklist", "suggestion"),
        ("We do not want a mobile app.", "direction", "a mobile app", "negated"),
    ],
)
def test_hedged_extractions_are_not_recorded(text: str, kind: IntentKind, quote: str, framing: str) -> None:
    result = extract(text, kind, quote)
    assert result.proposal.extracted == ()
    assert len(result.notes) == 1
    assert f"reads as {'a suggestion or question' if framing == 'suggestion' else framing}" in result.notes[0]
    assert result.notes[0].startswith(f"Not recorded as your choice: “{quote}”")


@pytest.mark.parametrize(
    ("text", "kind", "quote"),
    [
        ("We do not want a mobile app.", "exclusion", "a mobile app"),
        (
            "Exclude automated code changes, application scanning, and analytics.",
            "exclusion",
            "application scanning",
        ),
        (
            "The next step is a design brief, not implementation.",
            "nextStep",
            "The next step is a design brief, not implementation",
        ),
        (
            "Leave the channel undecided; I want interviews before deciding whether to build software.",
            "nextStep",
            "I want interviews before deciding whether to build software",
        ),
        (
            "Record incidents with no network available.",
            "constraint",
            "Record incidents with no network available",
        ),
    ],
)
def test_plain_instructions_are_recorded(text: str, kind: IntentKind, quote: str) -> None:
    result = extract(text, kind, quote)
    assert len(result.proposal.extracted) == 1
    assert result.notes == ()


def reply_resolution(reply: str, status: str, quote: str) -> Valid:
    p = project_from(AMBIGUOUS, "ambiguous brief")
    q = question(p, FOCUS_QUESTION)
    raw = {
        "extracted": [],
        "resolutions": [{"questionId": q.id, "status": status, "quote": quote}],
        "newItems": [],
        "focus": None,
    }
    result = validate_proposal(json.dumps(raw), ProposalContext("reply", reply, p, q.id))
    assert isinstance(result, Valid)
    return result


def test_a_hedged_answer_leaves_the_question_open() -> None:
    result = reply_resolution("Maybe coordination first, I'm not sure.", "answered", "coordination first")
    assert result.proposal.resolutions == ()
    assert "Not recorded as an answer" in result.notes[0]


def test_an_uncertain_reply_can_still_leave_a_question_open() -> None:
    result = reply_resolution("I'm not sure yet, so leave it open.", "deferred", "leave it open")
    assert len(result.proposal.resolutions) == 1


def test_hedge_detection_ignores_quotes_missing_from_the_text() -> None:
    assert hedge_around("absent", "Something else entirely.", negation_expected=False) is None
    assert hedge_around("", "Anything.", negation_expected=False) is None
