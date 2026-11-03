"""The domain reproduces the golden snapshots in fixtures/golden/: for every step of every scenario, the stored
record, the validation notes, both exports, and the changes since the last review."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.goldens import (
    GOLDEN,
    SCENARIOS,
    VALIDATION,
    read,
    replay,
    snapshot,
    validation_outcome,
    validation_projects,
)
from tests.support import AMBIGUOUS, CLEAR, canned, text, validated
from zigzag.domain.handoff import current_exports
from zigzag.domain.invariants import check_invariants
from zigzag.domain.proposal import ProposalContext

VALIDATION_GOLDEN = read(VALIDATION)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: Path(p).stem)
def test_replay_reproduces_every_snapshot(path: Path) -> None:
    scenario = read(path)
    states = replay(scenario["steps"])
    assert [check_invariants(project) for project, _ in states] == [()] * len(states)
    assert [snapshot(state) for state in states] == scenario["snapshots"]


@pytest.mark.parametrize("case", VALIDATION_GOLDEN["cases"], ids=lambda c: c["name"])
def test_validation_outcome_matches_its_snapshot(case: dict[str, Any]) -> None:
    assert validation_outcome(case, validation_projects(VALIDATION_GOLDEN)) == case["result"]


def test_a_deferral_inside_a_reply_is_partly_superseded_once_the_question_is_answered() -> None:
    (project, _) = replay(read(GOLDEN / "ambiguous-deferred-by-reply-then-selected.json")["steps"])[-1]
    exports = current_exports(project)
    handoff = json.loads(exports.json)
    reply_decision = next(d for d in handoff["decisions"] if d["action"] == "reply")
    answer = next(d for d in handoff["decisions"] if d["action"] == "select")
    assert reply_decision["supersededBy"] is None  # its statement stays current
    assert reply_decision["partlySupersededBy"] == [
        {"itemId": "q1", "itemText": "Which improvement should we investigate first?", "by": answer["id"]}
    ]
    assert f"(partly superseded: “Which improvement should we investigate first?” by {answer['id']})" in (
        exports.markdown
    )


def test_fixture_proposals_validate() -> None:
    validated(canned("clear brief"), ProposalContext("brief", text(CLEAR), None))
    validated(canned("ambiguous brief"), ProposalContext("brief", text(AMBIGUOUS), None))
