"""Characterization: the Python domain reproduces the legacy implementation's records and exports for
the same steps. Captured from the Express POC; see fixtures/legacy-golden/README.md."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.support import GOLDEN, as_current_format, validated
from zigzag.domain.handoff import (
    HANDOFF_ADAPTER,
    build_handoff,
    current_exports,
    diff_handoffs,
)
from zigzag.domain.invariants import check_invariants
from zigzag.domain.model import Project, last_review
from zigzag.domain.proposal import Invalid, ProposalContext, Valid, validate_proposal
from zigzag.domain.transitions import (
    Rejected,
    apply_reassessment,
    apply_user_text,
    create_project,
    defer_question,
    edit_statement,
    mark_reviewed,
    rely_on_assumption,
    remove_statement,
    select_option,
)

SCENARIOS = sorted(p for p in GOLDEN.glob("*.json") if p.name != "validation.json")
F3 = "ambiguous-deferred-by-reply-then-selected"


def apply(p: Project | None, s: dict[str, Any]) -> tuple[Project, tuple[str, ...]]:
    op = s["op"]
    if op == "create":
        result = validate_proposal(json.dumps(s["proposal"]), ProposalContext("brief", s["brief"], None))
        assert isinstance(result, Valid)
        project = create_project(
            project_id=s["id"],
            at=s["at"],
            brief=s["brief"],
            proposal=result.proposal,
            interpreted_by=s["interpretedBy"],
        )
        return project, result.notes
    assert p is not None
    if op == "reply":
        ctx = ProposalContext("reply", s["text"], p, s["questionId"])
        result = validate_proposal(json.dumps(s["proposal"]), ctx)
        assert isinstance(result, Valid)
        next_p = apply_user_text(
            p,
            at=s["at"],
            kind="reply",
            text=s["text"],
            question_id=s["questionId"],
            proposal=result.proposal,
            interpreted_by=s["interpretedBy"],
        )
        return next_p, result.notes
    if op == "reassess":
        result = validate_proposal(json.dumps(s["proposal"]), ProposalContext("reassess", None, p))
        assert isinstance(result, Valid)
        return apply_reassessment(p, at=s["at"], proposal=result.proposal, proposed_by=s["proposedBy"]), result.notes
    outcome = {
        "select": lambda: select_option(
            p, at=s["at"], question_id=s["questionId"], option_id=s["optionId"], reason=s["reason"]
        ),
        "defer": lambda: defer_question(p, at=s["at"], question_id=s["questionId"], reason=s["reason"]),
        "edit": lambda: edit_statement(p, at=s["at"], item_id=s["itemId"], text=s["text"]),
        "remove": lambda: remove_statement(p, at=s["at"], item_id=s["itemId"]),
        "rely": lambda: rely_on_assumption(p, at=s["at"], item_id=s["itemId"]),
        "review": lambda: mark_reviewed(p, at=s["at"], revision=s["revision"]),
    }[op]()
    assert not isinstance(outcome, Rejected), outcome
    return outcome, ()


def without_partial(document: str) -> str:
    """Remove the F3 correction so the remaining output can be compared with the legacy bytes."""
    if document.startswith("{"):
        data = json.loads(document)
        for d in data["decisions"]:
            d.pop("partlySupersededBy", None)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    marker = " _(partly superseded: "
    return "\n".join(line.split(marker)[0] + ("  " if marker in line else "") for line in document.split("\n"))


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: Path(p).stem)
def test_replay_reproduces_legacy_records_and_exports(path: Path) -> None:
    scenario = json.loads(as_current_format(path.read_text()))
    project: Project | None = None
    for step, snap in zip(scenario["steps"], scenario["snapshots"], strict=True):
        project, notes = apply(project, step)
        assert check_invariants(project) == ()
        assert list(notes) == snap["notes"]

        stored = json.loads(snap["storedFile"])
        mine = project.model_dump(mode="json")
        exports = current_exports(project)
        legacy = snap["exports"]
        if scenario["name"] == F3:
            for review in [*stored["reviews"], *mine["reviews"]]:
                review["markdown"], review["json"] = (
                    without_partial(review["markdown"]),
                    without_partial(review["json"]),
                )
            assert without_partial(exports.markdown) == legacy["markdown"]
            assert without_partial(exports.json) == legacy["json"]
        else:
            assert exports.markdown == legacy["markdown"]
            assert exports.json == legacy["json"]
        assert mine == stored
        assert (exports.revision, exports.status) == (legacy["revision"], legacy["status"])

        last = last_review(project)
        changes = (
            diff_handoffs(HANDOFF_ADAPTER.validate_json(last.json_copy), build_handoff(project, review_at=None))
            if last and last.revision != project.revision
            else None
        )
        expected = snap["handoffChanges"]
        if expected is None:
            assert changes is None
        else:
            assert changes is not None
            assert [
                {"section": c.section, "added": list(c.added), "removed": list(c.removed)} for c in changes
            ] == expected


def test_f3_is_corrected_the_deferral_inside_a_reply_is_marked_partly_superseded() -> None:
    scenario = json.loads((GOLDEN / f"{F3}.json").read_text())
    project: Project | None = None
    for step in scenario["steps"]:
        project, _ = apply(project, step)
    assert project is not None
    handoff = json.loads(current_exports(project).json)
    reply_decision = next(d for d in handoff["decisions"] if d["action"] == "reply")
    answer = next(d for d in handoff["decisions"] if d["action"] == "select")
    assert reply_decision["supersededBy"] is None  # its statement stays current
    assert reply_decision["partlySupersededBy"] == [
        {"itemId": "q1", "itemText": "Which improvement should we investigate first?", "by": answer["id"]}
    ]
    assert f"(partly superseded: “Which improvement should we investigate first?” by {answer['id']})" in (
        current_exports(project).markdown
    )


def test_validation_outcomes_match_legacy() -> None:
    golden = json.loads((GOLDEN / "validation.json").read_text())
    projects = {name: Project.model_validate_json(raw) for name, raw in golden["projects"].items()}
    for case in golden["cases"]:
        project = projects.get(case["project"])
        ctx = ProposalContext(case["context"], case["newText"], project)
        result = validate_proposal(case["raw"], ctx)
        expected = case["result"]
        if expected["ok"]:
            assert isinstance(result, Valid), case["name"]
            assert list(result.notes) == expected["notes"]
            assert len(result.proposal.new_items) == expected["keptNewItems"]
            assert result.proposal.focus == expected["focus"]
        else:
            assert isinstance(result, Invalid), case["name"]
            if case["name"] != "missing fields":  # schema wording differs between Zod and Pydantic
                assert list(result.issues) == expected["issues"], case["name"]


def test_fixture_proposals_validate() -> None:
    from tests.support import AMBIGUOUS, CLEAR, canned, text

    validated(canned("clear brief"), ProposalContext("brief", text(CLEAR), None))
    validated(canned("ambiguous brief"), ProposalContext("brief", text(AMBIGUOUS), None))
