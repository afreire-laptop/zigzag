"""Fixture mode makes no external calls and answers only its journey texts; the composition root and the
contract export wire the real adapters."""

import json
from pathlib import Path

import pytest

from tests.support import AMBIGUOUS, CLEAR, FIXTURES, FOCUS_QUESTION, project_from, question, text
from zigzag.adapters.model.fixture import FIXTURE_LABEL, FixtureAssessor, load_fixtures
from zigzag.application.assessment import render_user_message
from zigzag.application.ports import AssessRequest, CallAttempt, ModelCallError
from zigzag.contract import main as export_contract
from zigzag.contract import openapi_document
from zigzag.main import create_app

pytestmark = pytest.mark.anyio


def fixtures() -> FixtureAssessor:
    return FixtureAssessor(load_fixtures(FIXTURES / "journeys.json"))


async def test_fixture_rules_answer_journey_texts_and_resolve_question_ids() -> None:
    f = fixtures()
    attempts: list[CallAttempt] = []
    brief = await f.assess(AssessRequest(mode="brief", project=None, text=text(CLEAR)), attempts)
    assert brief.interpreted_by == FIXTURE_LABEL
    assert attempts == [CallAttempt(1, "answered")]  # no network and no reported cost
    project = project_from(AMBIGUOUS, "ambiguous brief")
    reply = await f.assess(AssessRequest(mode="reply", project=project, text=text("Short reply")), [])
    assert json.loads(reply.raw)["resolutions"][0]["questionId"] == question(project, FOCUS_QUESTION).id
    after = await f.assess(AssessRequest(mode="reassess", project=project, event="x"), [])
    assert json.loads(after.raw)["newItems"] == []


async def test_fixture_mode_refuses_texts_it_does_not_know() -> None:
    attempts: list[CallAttempt] = []
    with pytest.raises(ModelCallError) as error:
        await fixtures().assess(AssessRequest(mode="brief", project=None, text=text("paraphrasedBrief")), attempts)
    assert (error.value.kind, error.value.retryable) == ("fixture-miss", False)
    assert attempts == []
    with pytest.raises(ModelCallError):
        await fixtures().assess(
            AssessRequest(mode="reply", project=project_from(CLEAR, "clear brief"), text="Hi."), attempts
        )


def test_prompt_messages_carry_state_and_the_new_text() -> None:
    project = project_from(AMBIGUOUS, "ambiguous brief")
    focus = question(project, FOCUS_QUESTION)
    brief = render_user_message(AssessRequest(mode="brief", project=None, text="A brief."))
    assert brief == "CURRENT STATE: empty (this is a new brief).\n\nNEW USER TEXT (brief):\n<<<\nA brief.\n>>>"
    reply = render_user_message(AssessRequest(mode="reply", project=project, text="Yes.", question_id=focus.id))
    assert f"NEW USER TEXT (reply replying to question {focus.id}: “{FOCUS_QUESTION}”):" in reply
    assert '"earlierUserText"' in reply
    reassess = render_user_message(AssessRequest(mode="reassess", project=project, event="Selected X."))
    assert reassess.endswith("NEW USER TEXT: none. The user just acted through the interface: Selected X.")


def test_invalid_configuration_exits_with_status_2() -> None:
    with pytest.raises(SystemExit) as stopped:
        create_app({"ZIGZAG_MODEL_MODE": "fixtur"})
    assert stopped.value.code == 2


def test_live_mode_builds_without_calling_out(tmp_path: Path) -> None:
    app = create_app(
        {
            "ZIGZAG_MODEL_MODE": "live",
            "ZIGZAG_OPENROUTER_API_KEY": "sk-or-test",
            "ZIGZAG_MODEL": "anthropic/claude-opus-5.5",
            "ZIGZAG_DATA_DIR": str(tmp_path),
        }
    )
    assert app.title == "zigzag API"
    fixture_app = create_app(
        {"ZIGZAG_FIXTURES_PATH": str(FIXTURES / "journeys.json"), "ZIGZAG_DATA_DIR": str(tmp_path)}
    )
    assert fixture_app.title == "zigzag API"


def test_the_committed_contract_matches_the_code(tmp_path: Path) -> None:
    committed = (Path(__file__).resolve().parents[2] / "openapi.json").read_text()
    assert openapi_document(FIXTURES / "journeys.json") == committed
    target = tmp_path / "openapi.json"
    assert export_contract(["contract", str(target)]) == 0
    assert target.read_text() == committed
