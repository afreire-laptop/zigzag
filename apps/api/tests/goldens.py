"""Golden snapshots: scenario steps replayed through the domain, and what each step must produce.

`tests/domain/test_goldens.py` compares a replay with the snapshots in `fixtures/golden/`. After an intentional
change to stored records, exports, or validation, regenerate the snapshots from apps/api and review the diff:

    uv run --frozen python -m tests.goldens
"""

import json
from collections.abc import Mapping, Sequence
from functools import reduce
from pathlib import Path
from typing import Any

from tests.support import FIXTURES
from zigzag.adapters.persistence.files import project_text
from zigzag.domain.handoff import HANDOFF_ADAPTER, build_handoff, current_exports, diff_handoffs
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

GOLDEN = FIXTURES / "golden"
VALIDATION = GOLDEN / "validation.json"
SCENARIOS = tuple(sorted(p for p in GOLDEN.glob("*.json") if p != VALIDATION))

type Step = Mapping[str, Any]
# The project after a step, and the validation notes that step produced.
type State = tuple[Project, tuple[str, ...]]


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def document_text(data: object) -> str:
    """The fixture file format, which is also the stored-record format."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _proposal(raw: object, ctx: ProposalContext) -> Valid:
    result = validate_proposal(json.dumps(raw), ctx)
    assert isinstance(result, Valid), result
    return result


def apply(project: Project | None, step: Step) -> State:
    """The state after one step. A step that validation or a transition rejects fails the replay."""
    if step["op"] == "create":
        return _create(step)
    assert project is not None, f"{step['op']} needs an earlier create"
    return _transition(project, step)


def _create(step: Step) -> State:
    valid = _proposal(step["proposal"], ProposalContext("brief", step["brief"], None))
    project = create_project(
        project_id=step["id"],
        at=step["at"],
        brief=step["brief"],
        proposal=valid.proposal,
        interpreted_by=step["interpretedBy"],
    )
    return project, valid.notes


def _transition(project: Project, step: Step) -> State:
    at = step["at"]
    match step["op"]:
        case "reply":
            valid = _proposal(step["proposal"], ProposalContext("reply", step["text"], project, step["questionId"]))
            replied = apply_user_text(
                project,
                at=at,
                kind="reply",
                text=step["text"],
                question_id=step["questionId"],
                proposal=valid.proposal,
                interpreted_by=step["interpretedBy"],
            )
            return replied, valid.notes
        case "reassess":
            valid = _proposal(step["proposal"], ProposalContext("reassess", None, project))
            return apply_reassessment(
                project, at=at, proposal=valid.proposal, proposed_by=step["proposedBy"]
            ), valid.notes
        case "select":
            outcome = select_option(
                project, at=at, question_id=step["questionId"], option_id=step["optionId"], reason=step["reason"]
            )
        case "defer":
            outcome = defer_question(project, at=at, question_id=step["questionId"], reason=step["reason"])
        case "edit":
            outcome = edit_statement(project, at=at, item_id=step["itemId"], text=step["text"])
        case "remove":
            outcome = remove_statement(project, at=at, item_id=step["itemId"])
        case "rely":
            outcome = rely_on_assumption(project, at=at, item_id=step["itemId"])
        case "review":
            outcome = mark_reviewed(project, at=at, revision=step["revision"])
        case op:
            raise AssertionError(f"unknown step {op!r}")
    assert not isinstance(outcome, Rejected), outcome
    return outcome, ()


def replay(steps: Sequence[Step]) -> tuple[State, ...]:
    """The state after each step, in order."""

    def then(states: tuple[State, ...], step: Step) -> tuple[State, ...]:
        return (*states, apply(states[-1][0] if states else None, step))

    start: tuple[State, ...] = ()
    return reduce(then, steps, start)


def handoff_changes(project: Project) -> list[dict[str, Any]] | None:
    """What changed since the last review, or None when the current revision is reviewed or none is."""
    last = last_review(project)
    if last is None or last.revision == project.revision:
        return None
    changes = diff_handoffs(HANDOFF_ADAPTER.validate_json(last.json_copy), build_handoff(project, review_at=None))
    return [{"section": c.section, "added": list(c.added), "removed": list(c.removed)} for c in changes]


def snapshot(state: State) -> dict[str, Any]:
    project, notes = state
    exports = current_exports(project)
    return {
        "storedFile": project_text(project),
        "notes": list(notes),
        "exports": {
            "markdown": exports.markdown,
            "json": exports.json,
            "revision": exports.revision,
            "status": exports.status,
        },
        "handoffChanges": handoff_changes(project),
    }


def validation_outcome(case: Mapping[str, Any], projects: Mapping[str, Project]) -> dict[str, Any]:
    ctx = ProposalContext(case["context"], case["newText"], projects.get(case["project"]))
    match validate_proposal(case["raw"], ctx):
        case Valid(proposal=proposal, notes=notes):
            return {"ok": True, "notes": list(notes), "keptNewItems": len(proposal.new_items), "focus": proposal.focus}
        case Invalid(issues=issues):
            return {"ok": False, "issues": list(issues)}


def validation_projects(golden: Mapping[str, Any]) -> dict[str, Project]:
    return {name: Project.model_validate_json(raw) for name, raw in golden["projects"].items()}


def regenerated_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    return {**scenario, "snapshots": [snapshot(state) for state in replay(scenario["steps"])]}


def regenerated_validation(golden: Mapping[str, Any]) -> dict[str, Any]:
    projects = validation_projects(golden)
    return {**golden, "cases": [{**case, "result": validation_outcome(case, projects)} for case in golden["cases"]]}


def main() -> None:
    for path in SCENARIOS:
        path.write_text(document_text(regenerated_scenario(read(path))), encoding="utf-8")
    VALIDATION.write_text(document_text(regenerated_validation(read(VALIDATION))), encoding="utf-8")


if __name__ == "__main__":
    main()
