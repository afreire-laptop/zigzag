"""Milestone 1 journeys through the HTTP API with the fixture model and isolated temporary data."""

from pathlib import Path
from typing import Any

import pytest

from tests.api.harness import running
from tests.support import AMBIGUOUS, CLEAR, FOCUS_QUESTION, SOFTWARE_QUESTION, text

pytestmark = pytest.mark.anyio


def question(project: dict[str, Any], question_text: str) -> dict[str, Any]:
    return next(q for q in project["questions"] if q["text"] == question_text)


def section(project: dict[str, Any], kind: str) -> list[str]:
    return [i["text"] for s in project["intent"] if s["kind"] == kind for i in s["items"]]


async def test_clear_brief_carries_existing_direction_without_questions(tmp_path: Path) -> None:
    async with running(tmp_path) as api:
        status = (await api.get("/api/status")).json()
        assert status["mode"] == "fixture"
        assert [b["label"] for b in status["fixtures"]["briefs"]][:2] == [CLEAR, AMBIGUOUS]
        project = await api.create(text(CLEAR))
        assert project["questions"] == []
        assert project["focusId"] is None
        assert section(project, "nextStep") == ["Prepare a design brief, not an implementation."]
        assert project["assumptions"][0]["basis"] == "Stated as untested in your brief."
        assert [n["text"] for n in project["needed"]] == ["The release's changelog and migration documentation."]
        reviewed = (await api.post(f"/api/projects/{project['id']}/reviews", {"revision": 1})).json()
        assert reviewed["status"] == "reviewed"


async def test_ambiguous_brief_choice_reassessment_deferral_review_and_reload(tmp_path: Path) -> None:
    async with running(tmp_path) as api:
        project = await api.create(text(AMBIGUOUS))
        focus = question(project, FOCUS_QUESTION)
        assert project["focusId"] == focus["id"]
        assert focus["actions"] == {"select": True, "answerInOwnWords": True, "leaveOpen": True}
        assert section(project, "audience") == []

        coordination = next(o for o in focus["options"] if o["label"] == "Coordination during service")
        chosen = await api.decide(
            project, type="select", questionId=focus["id"], optionId=coordination["id"], reason="Service hurts."
        )
        assert chosen.status_code == 200
        project = chosen.json()
        assert section(project, "direction") == ["Investigate how incidents are coordinated during service."]

        done = await api.finish(
            await api.post(f"/api/projects/{project['id']}/assessments", {"baseRevision": project["revision"]})
        )
        assert done["status"] == "succeeded"
        project = (await api.get(f"/api/projects/{project['id']}")).json()
        follow_up = next(q for q in project["questions"] if q["id"] == project["focusId"])
        assert follow_up["text"] == "Whose coordination should the interviews focus on first?"

        project = (await api.decide(project, type="defer", questionId=follow_up["id"], reason=None)).json()
        assert section(project, "audience") == []
        assert question(project, SOFTWARE_QUESTION)["status"] == "open"

        reviewed = (await api.post(f"/api/projects/{project['id']}/reviews", {"revision": project["revision"]})).json()
        md = await api.get(f"/api/projects/{project['id']}/exports/markdown")
        js = await api.get(f"/api/projects/{project['id']}/exports/json")
        assert f'-r{reviewed["revision"]}-reviewed.md"' in md.headers["content-disposition"]
        assert md.headers["content-type"].startswith("text/markdown")
        assert f"**Status: Reviewed. Revision {reviewed['revision']}," in md.text
        assert js.json()["revision"] == reviewed["revision"]
        assert sorted(q["status"] for q in js.json()["openQuestions"]) == ["deferred", "open"]

    async with running(tmp_path) as restarted:  # a new process on the same data directory
        current = (await restarted.get("/api/projects/current")).json()
        assert current["state"] == "ready"
        assert current["project"] == reviewed
        assert (await restarted.get(f"/api/projects/{project['id']}/exports/markdown")).text == md.text
        assert (await restarted.get(f"/api/projects/{project['id']}/exports/json")).text == js.text


@pytest.mark.parametrize(
    ("reply_label", "focus_status", "direction"),
    [
        ("Detailed reply", "answered", ["Investigate coordination during service first."]),
        ("Short reply", "answered", ["Investigate coordination first."]),
        ("Defer reply", "deferred", []),
    ],
)
async def test_replies_in_the_users_words(
    tmp_path: Path, reply_label: str, focus_status: str, direction: list[str]
) -> None:
    async with running(tmp_path) as api:
        project = await api.create(text(AMBIGUOUS))
        focus = question(project, FOCUS_QUESTION)
        done = await api.finish(
            await api.post(
                f"/api/projects/{project['id']}/replies",
                {"text": text(reply_label), "questionId": focus["id"], "baseRevision": project["revision"]},
            )
        )
        assert done["status"] == "succeeded"
        assert done["result"]["revision"] == project["revision"] + 1
        project = (await api.get(f"/api/projects/{project['id']}")).json()
        assert question(project, FOCUS_QUESTION)["status"] == focus_status
        assert section(project, "direction") == direction
        if reply_label == "Detailed reply":
            assert question(project, SOFTWARE_QUESTION)["status"] == "deferred"
            assert section(project, "audience") == ["Shift managers, as the primary user to explore."]
        else:
            assert question(project, SOFTWARE_QUESTION)["status"] == "open"
            assert section(project, "audience") == []


async def test_correcting_a_selected_answer(tmp_path: Path) -> None:
    async with running(tmp_path) as api:
        project = await api.create(text(AMBIGUOUS))
        focus = question(project, FOCUS_QUESTION)
        first, second = focus["options"]
        project = (await api.decide(project, type="select", questionId=focus["id"], optionId=first["id"])).json()
        selection = project["decisions"][-1]["id"]

        project = (await api.decide(project, type="defer", questionId=focus["id"], reason="Not yet.")).json()
        assert question(project, FOCUS_QUESTION)["status"] == "deferred"
        assert section(project, "direction") == []
        assert project["decisions"][1]["supersededBy"] == project["decisions"][-1]["id"]
        assert project["decisions"][1]["id"] == selection

        project = (await api.decide(project, type="select", questionId=focus["id"], optionId=second["id"])).json()
        assert section(project, "direction") == [
            "Investigate how owners understand incidents and follow up afterwards."
        ]
        resolution = question(project, FOCUS_QUESTION)["resolution"]
        assert (resolution["via"], resolution["optionId"]) == ("option", second["id"])

        repeat = await api.decide(project, type="select", questionId=focus["id"], optionId=second["id"])
        assert repeat.status_code == 400
        assert repeat.json()["detail"] == "That option is already selected."
        history = [d["summary"] for d in project["decisions"]]
        assert len(history) == 4  # nothing erased
