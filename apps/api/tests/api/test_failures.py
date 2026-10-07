"""Invalid responses, model failures, stale results, cancellation, and damaged files all preserve the last
valid state. Overlapping requests apply one at a time against the revision they were based on."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from intent_harness.application.ports import AssessRequest, ModelCallError
from tests.api.harness import ScriptedAssessor, call_log, completion, gateway, running, scripted, unavailable
from tests.support import AMBIGUOUS, CLEAR, FOCUS_QUESTION, SOFTWARE_QUESTION, canned, text

pytestmark = pytest.mark.anyio
EMPTY = json.dumps({"extracted": [], "resolutions": [], "newItems": [], "focus": None})


def brief_proposal(label: str = AMBIGUOUS) -> str:
    return json.dumps(canned("ambiguous brief" if label == AMBIGUOUS else "clear brief"))


def q(project: dict[str, Any], question_text: str) -> dict[str, Any]:
    return next(x for x in project["questions"] if x["text"] == question_text)


async def test_bad_responses_change_nothing_and_a_valid_retry_applies(tmp_path: Path) -> None:
    reply = "Coordination during service first."

    async def valid(request: AssessRequest) -> str:
        assert request.project is not None
        focus = next(o for o in request.project.open_items if o.text == FOCUS_QUESTION)
        return json.dumps(
            {
                "extracted": [{"kind": "direction", "text": "Coordination during service first.", "quote": reply}],
                "resolutions": [{"questionId": focus.id, "status": "answered", "quote": reply}],
                "newItems": [],
                "focus": None,
            }
        )

    bad_quote = {
        "extracted": [{"kind": "audience", "text": "Owners.", "quote": "owners are the primary user"}],
        "resolutions": [],
        "newItems": [],
        "focus": None,
    }
    assessor = ScriptedAssessor(
        [brief_proposal(), "{ not json", json.dumps({"extracted": "nope"}), json.dumps(bad_quote), unavailable(), valid]
    )
    async with running(tmp_path, assessor) as api:
        project = await api.create(text(AMBIGUOUS))
        saved = api.project_file(project["id"])
        body = {"text": reply, "questionId": project["focusId"], "baseRevision": project["revision"]}
        for kind in ["invalid-output", "invalid-output", "invalid-output", "model-unavailable"]:
            done = await api.finish(await api.post(f"/api/projects/{project['id']}/replies", body))
            assert done["status"] == "failed"
            assert done["error"]["kind"] == kind
            assert done["error"]["retryable"] is True
            assert done["text"] == reply  # kept for a retry after reload
            assert api.project_file(project["id"]) == saved
        done = await api.finish(await api.post(f"/api/projects/{project['id']}/replies", body))
        assert done["status"] == "succeeded"
        after = (await api.get(f"/api/projects/{project['id']}")).json()
        assert q(after, FOCUS_QUESTION)["status"] == "answered"
        assert q(after, SOFTWARE_QUESTION)["status"] == "open"

    log = [json.loads(line) for line in (tmp_path / "model-calls.jsonl").read_text().splitlines()]
    assert [e["outcome"] for e in log] == ["valid", "rejected", "rejected", "rejected", "call-failed", "valid"]
    assert log[1]["raw"] == "{ not json"
    assert log[3]["issues"] == ["Quoted wording “owners are the primary user” does not appear in your text."]
    assert log[-1]["model"]["costStatus"] == "unknown"


async def test_every_submitted_attempt_is_logged_and_an_ambiguous_cost_stays_unknown(tmp_path: Path) -> None:
    clear = brief_proposal(CLEAR)
    transport = scripted(
        [
            httpx.ConnectError("refused"),  # never sent: retried automatically
            httpx.ReadTimeout("no answer"),  # sent and maybe processed: not retried
            httpx.Response(429),  # the user's retry: rejected before processing, retried automatically
            completion(clear, cost=0.02),
        ]
    )
    async with running(tmp_path, gateway(transport)) as api:
        failed = await api.finish(await api.post("/api/projects", {"brief": text(CLEAR)}))
        assert (failed["status"], failed["error"]["kind"], failed["error"]["retryable"]) == (
            "failed",
            "model-timeout",
            True,
        )
        assert "may still have processed the request and charged for it" in failed["error"]["message"]
        call = failed["modelCall"]
        assert (call["attempts"], call["ambiguousAttempts"], call["cost"], call["costStatus"]) == (
            2,
            1,
            None,
            "unknown",
        )
        assert (await api.get("/api/projects/current")).json()["state"] == "empty"

        done = await api.finish(await api.post("/api/projects", {"brief": text(CLEAR)}))  # the explicit retry
        assert done["status"] == "succeeded"
        call = done["modelCall"]
        assert (call["attempts"], call["ambiguousAttempts"], call["cost"], call["costStatus"]) == (
            2,
            0,
            0.02,
            "reported",
        )
        assert (call["servedModel"], call["provider"]) == ("test/model-1", "TestCloud")
        assert len(list((tmp_path / "projects").iterdir())) == 1

    log = call_log(tmp_path)
    assert [
        (e["operationId"], e["attempt"], e["outcome"], e["httpStatus"], e["failure"], e["cost"], e["costStatus"])
        for e in log
    ] == [
        (failed["id"], 1, "not-processed", None, "ConnectError", None, "not-charged"),
        (failed["id"], 2, "ambiguous", None, "ReadTimeout", None, "unknown-may-have-been-charged"),
        (done["id"], 1, "not-processed", 429, None, None, "not-charged"),
        (done["id"], 2, "valid", 200, None, 0.02, "reported"),
    ]
    assert log[1]["error"] == failed["error"]["message"]
    assert log[1]["model"]["ambiguousAttempts"] == 1
    assert [e["raw"] for e in log] == [None, None, None, clear]


async def test_invalid_output_reports_its_issues(tmp_path: Path) -> None:
    assessor = ScriptedAssessor(["{ not json"])
    async with running(tmp_path, assessor) as api:
        done = await api.finish(await api.post("/api/projects", {"brief": text(CLEAR)}))
        assert done["error"] == {
            "kind": "invalid-output",
            "message": "The model's response did not pass validation, so nothing was changed.",
            "retryable": True,
            "issues": ["The response was not valid JSON."],
        }
        assert done["modelCall"]["requestedModel"] == "stub-model"
        assert (await api.get("/api/projects/current")).json() == {"state": "empty", "project": None, "recovery": None}


async def test_a_failed_first_call_creates_no_project(tmp_path: Path) -> None:
    error = ModelCallError("model-credentials", "The model gateway rejected the credentials.", retryable=False)
    async with running(tmp_path, ScriptedAssessor([error])) as api:
        done = await api.finish(await api.post("/api/projects", {"brief": text(CLEAR)}))
        assert (done["status"], done["error"]["kind"], done["error"]["retryable"]) == (
            "failed",
            "model-credentials",
            False,
        )
        assert (await api.get("/api/projects/current")).json()["state"] == "empty"
        assert list((tmp_path / "projects").iterdir()) == []


async def test_a_result_is_not_applied_if_the_project_changed_meanwhile(tmp_path: Path) -> None:
    holder: dict[str, Any] = {}

    async def edit_meanwhile(request: AssessRequest) -> str:
        assert request.project is not None
        api, project = holder["api"], holder["project"]
        edited = await api.decide(
            project, type="edit", itemId=project["intent"][0]["items"][0]["id"], text="Edited meanwhile."
        )
        assert edited.status_code == 200
        return EMPTY

    async with running(tmp_path, ScriptedAssessor([brief_proposal(CLEAR), edit_meanwhile])) as api:
        project = await api.create(text(CLEAR))
        holder.update(api=api, project=project)
        done = await api.finish(
            await api.post(
                f"/api/projects/{project['id']}/replies",
                {"text": "Also cover Select.", "questionId": None, "baseRevision": project["revision"]},
            )
        )
        assert (done["status"], done["error"]["kind"]) == ("failed", "conflict")
        now = (await api.get(f"/api/projects/{project['id']}")).json()
        assert now["revision"] == project["revision"] + 1
        assert now["intent"][0]["items"][0]["text"] == "Edited meanwhile."
        assert len(now["inputs"]) == 1


async def test_stale_starts_and_commands_are_refused(tmp_path: Path) -> None:
    async with running(tmp_path, ScriptedAssessor([brief_proposal(CLEAR)])) as api:
        project = await api.create(text(CLEAR))
        stale = {**project, "revision": project["revision"] - 1}
        removed = await api.decide(stale, type="remove", itemId=project["intent"][0]["items"][0]["id"])
        assert removed.status_code == 409
        assert removed.headers["content-type"] == "application/problem+json"
        assert removed.json()["kind"] == "conflict"
        started = await api.post(f"/api/projects/{project['id']}/assessments", {"baseRevision": 0})
        assert started.status_code == 409
        review = await api.post(f"/api/projects/{project['id']}/reviews", {"revision": 0})
        assert review.status_code == 409


async def test_one_model_operation_at_a_time_per_project_and_cancellation(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def slow(_: AssessRequest) -> str:
        await release.wait()
        return EMPTY

    async with running(tmp_path, ScriptedAssessor([brief_proposal(), slow])) as api:
        project = await api.create(text(AMBIGUOUS))
        base = {"baseRevision": project["revision"]}
        started = (await api.post(f"/api/projects/{project['id']}/assessments", base)).json()
        busy = await api.post(f"/api/projects/{project['id']}/assessments", base)
        assert busy.status_code == 409
        assert busy.json()["kind"] == "busy"
        assert busy.json()["activeOperationId"] == started["id"]
        active = (await api.get("/api/operations")).json()
        assert [o["id"] for o in active] == [started["id"]]

        cancelled = (await api.post(f"/api/operations/{started['id']}/cancel")).json()
        assert (cancelled["status"], cancelled["error"]["kind"]) == ("cancelled", "cancelled")
        assert (await api.get(f"/api/operations/{started['id']}")).json()["status"] == "cancelled"
        again = (await api.post(f"/api/operations/{started['id']}/cancel")).json()
        assert again == cancelled
        assert (await api.get(f"/api/projects/{project['id']}")).json() == project
        assert (await api.get("/api/operations")).json() == []
        release.set()


async def test_sse_replays_the_current_state_and_never_repeats_the_model_call(tmp_path: Path) -> None:
    assessor = ScriptedAssessor([brief_proposal(CLEAR)])
    async with running(tmp_path, assessor) as api:
        started = await api.post("/api/projects", {"brief": text(CLEAR)})
        events = await api.events(started.json()["id"])
        versions = [e["version"] for e in events]
        assert versions == sorted(set(versions))
        assert events[-1]["status"] == "succeeded"
        assert events[-1]["result"]["projectId"]
        reconnect = await api.events(started.json()["id"])
        assert reconnect == [events[-1]]
        assert len(assessor.calls) == 1
        missing = await api.get("/api/operations/nope/events")
        assert missing.status_code == 404


async def test_overlapping_commands_apply_one_at_a_time(tmp_path: Path) -> None:
    async with running(tmp_path, ScriptedAssessor([brief_proposal(CLEAR)])) as api:
        project = await api.create(text(CLEAR))
        items = [i["id"] for s in project["intent"] for i in s["items"]]
        same_base = await asyncio.gather(*(api.decide(project, type="remove", itemId=i) for i in items[:4]))
        assert sorted(r.status_code for r in same_base) == [200, 409, 409, 409]
        winner = next(r.json() for r in same_base if r.status_code == 200)

        async def edit(n: int) -> int:
            for _ in range(20):
                current = (await api.get(f"/api/projects/{project['id']}")).json()
                response = await api.decide(current, type="edit", itemId=items[4 + n], text=f"Edited {n}.")
                if response.status_code == 200:
                    return response.json()["revision"]
            raise AssertionError("never applied")

        revisions = await asyncio.gather(*(edit(n) for n in range(3)))
        assert sorted(revisions) == [winner["revision"] + 1, winner["revision"] + 2, winner["revision"] + 3]
        final = (await api.get(f"/api/projects/{project['id']}")).json()
        assert final["revision"] == winner["revision"] + 3
        assert len(final["decisions"]) == 1 + 1 + 3


async def test_a_damaged_record_is_reported_and_left_untouched(tmp_path: Path) -> None:
    async with running(tmp_path, ScriptedAssessor([brief_proposal(CLEAR), brief_proposal()])) as api:
        older = await api.create(text(CLEAR))
        damaged = await api.create(text(AMBIGUOUS))
        path = tmp_path / "projects" / f"{damaged['id']}.json"
        path.write_text(path.read_text().replace('"revision": 1', '"revision": "one"', 1))
        before = path.read_bytes()

        current = (await api.get("/api/projects/current")).json()
        assert current["state"] == "corrupt"
        assert current["project"] is None  # an older project is not presented as current
        assert current["recovery"]["projectId"] == damaged["id"]
        assert current["recovery"]["file"].endswith(f"{damaged['id']}.json")
        assert "revision" in current["recovery"]["reason"]

        read = await api.get(f"/api/projects/{damaged['id']}")
        assert (read.status_code, read.json()["kind"]) == (500, "corrupt-record")
        command = await api.post(f"/api/projects/{damaged['id']}/reviews", {"revision": 1})
        assert command.status_code == 500
        assert path.read_bytes() == before
        assert (await api.get(f"/api/projects/{older['id']}")).status_code == 200


async def test_a_damaged_operation_record_is_reported_and_model_work_waits(tmp_path: Path) -> None:
    damaged = tmp_path / "operations" / "op-z.json"
    damaged.parent.mkdir(parents=True)
    damaged.write_text("{ torn")
    async with running(tmp_path, ScriptedAssessor([])) as api:
        status = (await api.get("/api/status")).json()
        [entry] = status["damagedOperations"]
        assert entry["file"] == str(damaged)
        assert entry["reason"]
        refused = await api.post("/api/projects", {"brief": text(CLEAR)})
        assert (refused.status_code, refused.json()["kind"], refused.json()["retryable"]) == (
            500,
            "corrupt-record",
            False,
        )
        assert str(damaged) in refused.json()["detail"]
        assert damaged.read_text() == "{ torn"


async def test_requests_from_other_hosts_and_malformed_bodies_are_refused(tmp_path: Path) -> None:
    async with running(tmp_path, ScriptedAssessor([])) as api:
        foreign = await api.client.get("/api/status", headers={"host": "attacker.example"})
        assert foreign.status_code == 400
        invalid = await api.post("/api/projects", {"brief": "   "})
        assert invalid.status_code == 422
        assert invalid.json()["kind"] == "invalid-request"
        assert invalid.json()["issues"]
        unknown = await api.get("/api/projects/does-not-exist")
        assert (unknown.status_code, unknown.json()["kind"]) == (404, "not-found")
        no_route = await api.get("/api/nothing-here")
        assert no_route.status_code == 404
        assert no_route.headers["content-type"] == "application/problem+json"
        missing_op = await api.post("/api/operations/zzz/cancel")
        assert missing_op.status_code == 404
        health = await api.get("/api/health")
        assert health.json() == {"status": "ok"}


async def test_exports_of_reviewed_and_unknown_revisions(tmp_path: Path) -> None:
    async with running(tmp_path, ScriptedAssessor([brief_proposal(CLEAR)])) as api:
        project = await api.create(text(CLEAR))
        await api.post(f"/api/projects/{project['id']}/reviews", {"revision": 1})
        fixed = (await api.get(f"/api/projects/{project['id']}/exports/json?revision=1")).text
        project = (await api.get(f"/api/projects/{project['id']}")).json()
        project = (
            await api.decide(project, type="edit", itemId=project["intent"][0]["items"][0]["id"], text="Changed.")
        ).json()
        draft = await api.get(f"/api/projects/{project['id']}/exports/markdown")
        assert "-r2-draft.md" in draft.headers["content-disposition"]
        assert "DRAFT. Revision 2 has not been reviewed." in draft.text
        assert (await api.get(f"/api/projects/{project['id']}/exports/json?revision=1")).text == fixed
        unknown = await api.get(f"/api/projects/{project['id']}/exports/json?revision=7")
        assert unknown.status_code == 404
        view = (await api.get(f"/api/projects/{project['id']}/handoff")).json()
        assert view["lastReviewed"]["revision"] == 1
        assert view["changes"][0]["section"] == "Desired outcome"
        assert view["current"]["status"] == "draft"
