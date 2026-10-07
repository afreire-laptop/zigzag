"""The operation runner: deadline, bounded concurrency, shutdown, restart recovery, and unexpected errors."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from intent_harness.adapters.persistence.files import FileOperationStore, FileProjectStore, JsonlCallLog
from intent_harness.application.errors import ApplicationError
from intent_harness.application.operations import CommitMarker, ModelCall, Operation, OperationRecord, OperationRunner
from intent_harness.application.ports import Assessor, AssessRequest, Loaded
from intent_harness.application.projects import ProjectLocks
from intent_harness.domain.model import Project
from tests.api.harness import Counter, ScriptedAssessor, Ticker, call_log, gateway, wait_until
from tests.support import CLEAR, canned, failing_fsync, project_from, text

pytestmark = pytest.mark.anyio
CLEAR_RAW = json.dumps(canned("clear brief"))
EMPTY = json.dumps({"extracted": [], "resolutions": [], "newItems": [], "focus": None})
# A reassessment that repeats an open item of the clear brief: valid, with a note that it was skipped.
REPEATED = json.dumps(
    {"extracted": [], "resolutions": [], "newItems": canned("clear brief")["newItems"][:1], "focus": None}
)


MAY_HAVE_RUN = "may still have processed the request and charged for it"


def runner(
    tmp_path: Path,
    assessor: Assessor,
    *,
    deadline: float = 30.0,
    concurrent: int = 2,
    projects: FileProjectStore | None = None,
    operations: FileOperationStore | None = None,
) -> OperationRunner:
    return OperationRunner(
        projects=projects or FileProjectStore(tmp_path),
        operations=operations or FileOperationStore(tmp_path),
        locks=ProjectLocks(),
        assessor=assessor,
        call_log=JsonlCallLog(tmp_path),
        clock=Ticker(),
        new_id=Counter("x"),
        deadline_seconds=deadline,
        max_concurrent=concurrent,
    )


async def finished(r: OperationRunner, operation_id: str) -> str:
    states = [state async for state in r.watch(operation_id)]
    return states[-1].status


async def test_the_deadline_covers_the_whole_call(tmp_path: Path) -> None:
    async def never(_: AssessRequest) -> str:
        await asyncio.sleep(10)
        return EMPTY

    r = runner(tmp_path, ScriptedAssessor([never]), deadline=0.05)
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "failed"
    error = r.get(op.id).error
    assert error is not None
    assert (error.kind, error.retryable) == ("deadline-exceeded", True)
    assert error.message.endswith("Nothing was changed.")  # nothing was submitted, so nothing can be charged
    assert r.get(op.id).model_call is None


async def hang(_: httpx.Request) -> httpx.Response:
    """A provider that received the request and has not answered yet."""
    await asyncio.sleep(10)
    raise AssertionError("the request should have been cut off")


async def test_a_deadline_that_cuts_off_a_request_is_logged_as_ambiguous(tmp_path: Path) -> None:
    FileProjectStore(tmp_path).save(project_from(CLEAR, "clear brief", project_id="p1"))
    before = (tmp_path / "projects" / "p1.json").read_bytes()
    r = runner(tmp_path, gateway(hang), deadline=0.05)
    op = await r.start_reassess("p1", 1)
    assert await finished(r, op.id) == "failed"
    after = r.get(op.id)
    assert after.error is not None
    assert (after.error.kind, after.error.retryable) == ("deadline-exceeded", True)
    assert MAY_HAVE_RUN in after.error.message
    assert after.model_call is not None
    assert (after.model_call.attempts, after.model_call.ambiguous_attempts) == (1, 1)
    assert (after.model_call.cost, after.model_call.cost_status) == (None, "unknown")
    assert (tmp_path / "projects" / "p1.json").read_bytes() == before
    [entry] = call_log(tmp_path)
    assert (entry["operationId"], entry["attempt"], entry["outcome"], entry["failure"]) == (
        op.id,
        1,
        "ambiguous",
        "cancelled",
    )
    assert (entry["cost"], entry["costStatus"], entry["error"]) == (
        None,
        "unknown-may-have-been-charged",
        "deadline exceeded",
    )


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
async def test_stopping_a_request_in_flight_says_it_may_have_been_charged(tmp_path: Path, stop: str) -> None:
    FileProjectStore(tmp_path).save(project_from(CLEAR, "clear brief", project_id="p1"))
    before = (tmp_path / "projects" / "p1.json").read_bytes()
    received = asyncio.Event()

    async def receive_and_hang(request: httpx.Request) -> httpx.Response:
        received.set()
        return await hang(request)

    r = runner(tmp_path, gateway(receive_and_hang))
    op = await r.start_reassess("p1", 1)
    await asyncio.wait_for(received.wait(), timeout=2)
    if stop == "cancel":
        await r.cancel(op.id)
    else:
        await r.shutdown()
    after = r.get(op.id)
    assert after.status == ("cancelled" if stop == "cancel" else "interrupted")
    assert after.error is not None
    assert after.error.retryable
    assert MAY_HAVE_RUN in after.error.message
    assert after.model_call is not None
    assert (after.model_call.attempts, after.model_call.ambiguous_attempts) == (1, 1)
    assert (tmp_path / "projects" / "p1.json").read_bytes() == before
    [entry] = call_log(tmp_path)
    assert (entry["attempt"], entry["outcome"], entry["costStatus"]) == (
        1,
        "ambiguous",
        "unknown-may-have-been-charged",
    )


async def test_concurrency_is_bounded_and_queued_work_can_be_cancelled(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def held(_: AssessRequest) -> str:
        await gate.wait()
        return CLEAR_RAW

    store = FileProjectStore(tmp_path)
    store.save(project_from(CLEAR, "clear brief", project_id="p1"))
    store.save(project_from(CLEAR, "clear brief", project_id="p2"))
    r = runner(tmp_path, ScriptedAssessor([held, held]), concurrent=1)
    first = await r.start_create(text(CLEAR))
    second = await r.start_reassess("p1", 1)
    await wait_until(lambda: r.get(first.id).status == "running")
    await asyncio.sleep(0.02)
    assert r.get(second.id).status == "queued"
    cancelled = await r.cancel(second.id)
    assert cancelled.status == "cancelled"
    gate.set()
    assert await finished(r, first.id) == "succeeded"


async def test_shutdown_marks_running_work_interrupted(tmp_path: Path) -> None:
    async def never(_: AssessRequest) -> str:
        await asyncio.sleep(10)
        return EMPTY

    r = runner(tmp_path, ScriptedAssessor([never]))
    op = await r.start_create(text(CLEAR))
    await wait_until(lambda: r.get(op.id).status == "running")
    await r.shutdown()
    after = r.get(op.id)
    assert after.status == "interrupted"
    assert after.error is not None
    assert after.error.retryable


async def test_restart_recovery_uses_the_commit_marker(tmp_path: Path) -> None:
    store, operations = FileProjectStore(tmp_path), FileOperationStore(tmp_path)
    project = project_from(CLEAR, "clear brief", project_id="p1")
    store.save(project)
    (tmp_path / "projects" / "p2.json").write_text("{ damaged")
    r = runner(tmp_path, ScriptedAssessor([]))
    running_without_marker = await _record(operations, "op-a", None)
    committed = await _record(operations, "op-b", CommitMarker(at=project.updated_at, project_id="p1", revision=1))
    marker_not_written = await _record(
        operations, "op-c", CommitMarker(at="2030-01-01T00:00:00.000Z", project_id="p1", revision=2)
    )
    unreadable = await _record(operations, "op-d", CommitMarker(at=project.updated_at, project_id="p2", revision=2))
    r.recover()
    assert r.get(running_without_marker).status == "interrupted"
    succeeded = r.get(committed)
    assert succeeded.status == "succeeded"
    assert succeeded.result is not None
    assert succeeded.result.revision == 1
    assert r.get(marker_not_written).status == "interrupted"
    unconfirmed = r.get(unreadable)
    assert unconfirmed.status == "interrupted"
    assert unconfirmed.error is not None
    assert "Nothing was changed" not in unconfirmed.error.message
    assert unconfirmed.error.retryable is False
    assert r.active() == []


async def _record(operations: FileOperationStore, op_id: str, marker: CommitMarker | None) -> str:
    op = Operation(
        id=op_id,
        kind="reassess",
        status="running",
        version=2,
        project_id="p1",
        base_revision=1,
        question_id=None,
        text=None,
        created_at="2026-10-06T10:00:00.000Z",
        updated_at="2026-10-06T10:00:01.000Z",
        deadline_at="2026-10-06T10:03:00.000Z",
        result=None,
        error=None,
        model_call=None,
    )
    operations.save(OperationRecord(operation=op, base_updated_at=None, commit=marker))
    return op_id


async def test_a_damaged_operation_record_pauses_model_work_until_it_is_moved(tmp_path: Path) -> None:
    FileProjectStore(tmp_path).save(project_from(CLEAR, "clear brief", project_id="p1"))
    damaged = tmp_path / "operations" / "op-z.json"
    damaged.parent.mkdir(parents=True)
    damaged.write_text('{"operation": {"id": "op-z", "status": "runn')  # its project write may have landed
    r = runner(tmp_path, ScriptedAssessor([EMPTY]))
    r.recover()
    assert damaged.read_text() == '{"operation": {"id": "op-z", "status": "runn'  # never modified or skipped
    assert [d.file for d in r.damaged()] == [str(damaged)]
    for start in (lambda: r.start_create(text(CLEAR)), lambda: r.start_reassess("p1", 1)):
        with pytest.raises(ApplicationError) as refused:
            await start()
        assert (refused.value.kind, refused.value.retryable) == ("corrupt-record", False)
        assert str(damaged) in refused.value.message
    assert r.active() == []
    damaged.rename(tmp_path / "op-z.json.moved")  # the user checked the brief and moved the record aside
    op = await r.start_reassess("p1", 1)
    assert await finished(r, op.id) == "succeeded"


async def test_unexpected_errors_fail_the_operation_without_changes(tmp_path: Path) -> None:
    r = runner(tmp_path, ScriptedAssessor([RuntimeError("boom")]))
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "failed"
    error = r.get(op.id).error
    assert error is not None
    assert error.kind == "internal"
    assert list((tmp_path / "projects").iterdir()) == []


async def test_a_failing_directory_sync_does_not_orphan_an_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_fsync(monkeypatch, directories=True)  # every write is visible, but its rename may not survive a crash
    r = runner(tmp_path, ScriptedAssessor([CLEAR_RAW]))
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "succeeded"
    assert r.active() == []
    assert len(list((tmp_path / "projects").iterdir())) == 1


class SavesThenFails(FileProjectStore):
    """Breaks the save contract: the new record is written and visible, then the save raises. The runner still
    reports what was saved."""

    def save(self, project: Project) -> None:
        super().save(project)
        raise OSError("directory fsync failed")


class FailsBeforeSaving(FileProjectStore):
    def save(self, project: Project) -> None:
        raise OSError("disk full")


class SavesThenCannotRead(FileProjectStore):
    """Breaks the save contract as SavesThenFails does, and then the record cannot be read back, so whether the
    save landed cannot be told."""

    def __init__(self, data_dir: Path, *, damage: bool) -> None:
        super().__init__(data_dir)
        self._damage, self._failed = damage, False

    def save(self, project: Project) -> None:
        super().save(project)
        self._failed = True
        if self._damage:
            (self._dir / f"{project.id}.json").write_text("{ torn")
        raise OSError("directory fsync failed")

    def load(self, project_id: str) -> Loaded:
        if self._failed and not self._damage:
            raise OSError("input/output error")
        return super().load(project_id)


class FailsOnceToFinish(FileOperationStore):
    """The first attempt to record success fails before anything is written. Keeps the record written just
    before the project save, which is what a crash at that point would leave behind."""

    def __init__(self, data_dir: Path, *, fail: bool = True) -> None:
        super().__init__(data_dir)
        self.failed = not fail
        self.marked: OperationRecord | None = None

    def save(self, record: OperationRecord) -> None:
        if record.commit is not None and record.operation.status == "running":
            self.marked = record
        if record.operation.status == "succeeded" and not self.failed:
            self.failed = True
            raise OSError("disk full")
        super().save(record)


async def test_a_project_saved_before_an_error_is_reported_as_succeeded(tmp_path: Path) -> None:
    r = runner(tmp_path, ScriptedAssessor([CLEAR_RAW]), projects=SavesThenFails(tmp_path))
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "succeeded"  # not "failed, nothing was changed", which invites a duplicate
    done = r.get(op.id)
    assert done.error is None
    assert done.result is not None
    [saved] = (tmp_path / "projects").iterdir()
    assert (saved.stem, done.result.revision) == (done.result.project_id, 1)
    assert done.model_call is not None
    assert (done.model_call.attempts, done.model_call.requested_model) == (1, "stub-model")


async def reassessed(data_dir: Path, operations: FailsOnceToFinish) -> Operation:
    """Reassesses a saved clear brief with a reply that earns a validation note; returns the final operation."""
    FileProjectStore(data_dir).save(project_from(CLEAR, "clear brief", project_id="p1"))
    r = runner(data_dir, ScriptedAssessor([REPEATED]), operations=operations)
    op = await r.start_reassess("p1", 1)
    assert await finished(r, op.id) == "succeeded"
    return r.get(op.id)


def without_latency(call: ModelCall | None) -> ModelCall | None:
    return call.model_copy(update={"latency_ms": 0}) if call else None


async def test_a_success_that_failed_to_be_recorded_keeps_its_notes_and_model_call(tmp_path: Path) -> None:
    (tmp_path / "normal").mkdir()
    reference = await reassessed(tmp_path / "normal", FailsOnceToFinish(tmp_path / "normal", fail=False))
    failing = FailsOnceToFinish(tmp_path)
    done = await reassessed(tmp_path, failing)
    assert failing.failed
    assert done.result is not None
    assert done.result.notes  # the validation note survives
    assert done.result == reference.result
    assert done.model_call is not None
    assert without_latency(done.model_call) == without_latency(reference.model_call)


async def test_restart_recovery_restores_the_exact_result_and_model_call(tmp_path: Path) -> None:
    operations = FailsOnceToFinish(tmp_path, fail=False)
    succeeded = await reassessed(tmp_path, operations)
    assert operations.marked is not None
    FileOperationStore(tmp_path).save(operations.marked)  # as left by a crash after the project was saved
    restarted = runner(tmp_path, ScriptedAssessor([]))
    restarted.recover()
    recovered = restarted.get(succeeded.id)
    assert recovered.status == "succeeded"
    assert recovered.result == succeeded.result
    assert recovered.model_call == succeeded.model_call


async def test_an_error_before_the_project_is_saved_still_reports_nothing_changed(tmp_path: Path) -> None:
    r = runner(tmp_path, ScriptedAssessor([CLEAR_RAW]), projects=FailsBeforeSaving(tmp_path))
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "failed"
    error = r.get(op.id).error
    assert error is not None
    assert (error.kind, error.retryable, error.message) == (
        "internal",
        True,
        "The server failed while working on this. Nothing was changed.",
    )
    assert list((tmp_path / "projects").iterdir()) == []
    assert r.get(op.id).model_call is not None  # the call was made and is still accounted for


@pytest.mark.parametrize("damage", [False, True], ids=["unreadable", "damaged"])
async def test_a_commit_that_cannot_be_confirmed_never_claims_nothing_changed(tmp_path: Path, damage: bool) -> None:
    r = runner(tmp_path, ScriptedAssessor([CLEAR_RAW]), projects=SavesThenCannotRead(tmp_path, damage=damage))
    op = await r.start_create(text(CLEAR))
    assert await finished(r, op.id) == "interrupted"
    error = r.get(op.id).error
    assert error is not None
    assert "Nothing was changed" not in error.message
    assert "could not confirm" in error.message
    assert error.retryable is False  # a blind retry could create the project twice
    assert r.get(op.id).model_call is not None


async def test_a_stale_operation_fails_before_paying_for_a_call(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    store.save(project_from(CLEAR, "clear brief", project_id="p1"))
    gate = asyncio.Event()

    async def held(_: AssessRequest) -> str:
        await gate.wait()
        return EMPTY

    assessor = ScriptedAssessor([held, EMPTY])
    r = runner(tmp_path, assessor, concurrent=1)
    blocker = await r.start_create(text(CLEAR))
    queued = await r.start_reassess("p1", 1)
    project = project_from(CLEAR, "clear brief", project_id="p1").model_copy(
        update={"updated_at": "2026-10-06T11:00:00.000Z"}
    )
    store.save(project)  # changed while the reassessment waited in the queue
    gate.set()
    assert await finished(r, blocker.id) == "succeeded"
    assert await finished(r, queued.id) == "failed"
    assert len(assessor.calls) == 1


async def test_reply_requests_are_checked_before_starting(tmp_path: Path) -> None:
    FileProjectStore(tmp_path).save(project_from(CLEAR, "clear brief", project_id="p1"))
    r = runner(tmp_path, ScriptedAssessor([]))
    with pytest.raises(ApplicationError) as missing:
        await r.start_reply("p1", 1, "Answer.", "q9")
    assert missing.value.kind == "not-found"
    with pytest.raises(ApplicationError) as unknown:
        r.get("nope")
    assert unknown.value.kind == "not-found"
