"""Asynchronous model operations.

A request starts an operation and returns at once. The operation record is persisted at every state change
and is the authority; watchers are only woken to re-read it. Results are applied under the project lock and
only against the revision the operation started from. Success is announced after both the project and the
operation are saved. A commit marker written just before the project save lets restart recovery tell a
completed write from an interrupted one."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import Field

from zigzag.application.errors import ApplicationError, ErrorKind
from zigzag.application.ports import (
    Assessor,
    AssessRequest,
    CallAttempt,
    CallLog,
    Clock,
    Found,
    Missing,
    ModelCallError,
    ModelReply,
    NewId,
    ProjectStore,
    known_cost,
)
from zigzag.application.projects import ProjectLocks, check_base, require
from zigzag.domain.model import Project, Value
from zigzag.domain.proposal import Invalid, ProposalContext, Valid, validate_proposal
from zigzag.domain.transitions import apply_reassessment, apply_user_text, create_project

log = logging.getLogger("zigzag.operations")

OperationKind = Literal["create", "reply", "reassess"]
OperationStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted"]
TERMINAL: frozenset[OperationStatus] = frozenset({"succeeded", "failed", "cancelled", "interrupted"})
SIGNAL_RECHECK_SECONDS = 5.0


class OperationError(Value):
    kind: ErrorKind
    message: str
    retryable: bool
    issues: tuple[str, ...] = ()


class OperationResult(Value):
    project_id: str
    revision: int
    notes: tuple[str, ...]


class ModelCall(Value):
    requested_model: str
    served_model: str | None
    provider: str | None
    prompt_version: str | None
    attempts: int = Field(description="Requests submitted, including any repeated automatically or cut off.")
    ambiguous_attempts: int = Field(
        description="Requests that may have been processed and charged although no usable answer came back."
    )
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    cost: float | None = Field(
        description="Credits reported across all attempts. Empty unless one was reported and none is unknown."
    )
    cost_status: Literal["reported", "not-charged", "unknown"] = Field(
        description="unknown when any attempt's cost is unknown, including one that may have been charged; "
        "not-charged when every attempt was rejected before a model processed it."
    )


class Operation(Value):
    """The public state of one model operation, also sent as each SSE notification."""

    id: str
    kind: OperationKind
    status: OperationStatus
    version: int
    project_id: str | None
    base_revision: int | None
    question_id: str | None
    # The user's own text, kept so an interrupted or failed operation can be retried after a reload.
    text: str | None
    created_at: str
    updated_at: str
    deadline_at: str
    result: OperationResult | None
    error: OperationError | None
    model_call: ModelCall | None


class CommitMarker(Value):
    """Written just before the project save, so recovery can tell whether that save landed, and then report the
    operation exactly as it would have finished: with its notes and its model call."""

    at: str
    project_id: str
    revision: int
    notes: tuple[str, ...] = ()
    model_call: ModelCall | None = None


class OperationRecord(Value):
    """What is stored: the public state plus what recovery and the stale-result check need."""

    operation: Operation
    base_updated_at: str | None
    commit: CommitMarker | None


class DamagedOperation(Value):
    """An operation file that cannot be read. It is never modified or skipped: whether its work reached the
    project is unknown until someone checks, so model work waits until the file is moved aside."""

    file: str
    reason: str
    modified_at: str


class OperationStore(Protocol):
    def save(self, record: OperationRecord) -> None:
        """Atomically replace the record. Raises only if the stored record is unchanged."""
        ...

    def load(self, operation_id: str) -> OperationRecord | None: ...

    def all(self) -> list[OperationRecord]:
        """Every readable record. Unreadable ones are reported by `damaged`."""
        ...

    def damaged(self) -> list[DamagedOperation]: ...


class _Signals:
    """Wakes watchers of one operation after its record changes. Carries no state of its own."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def current(self, operation_id: str) -> asyncio.Event:
        return self._events.setdefault(operation_id, asyncio.Event())

    def notify(self, operation_id: str) -> None:
        self._events.pop(operation_id, asyncio.Event()).set()


def _plus_seconds(iso: str, seconds: float) -> str:
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OperationRunner:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        operations: OperationStore,
        locks: ProjectLocks,
        assessor: Assessor,
        call_log: CallLog,
        clock: Clock,
        new_id: NewId,
        deadline_seconds: float,
        max_concurrent: int,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._projects = projects
        self._operations = operations
        self._locks = locks
        self._assessor = assessor
        self._call_log = call_log
        self._clock = clock
        self._new_id = new_id
        self._deadline_seconds = deadline_seconds
        self._monotonic = monotonic
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._signals = _Signals()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subjects: dict[str, str] = {}
        self._cancel_requested: set[str] = set()
        self._deadlines: dict[str, float] = {}

    # --- Starting ---------------------------------------------------------------------------------

    async def start_create(self, brief: str) -> Operation:
        return self._spawn("create", subject="new-project", project=None, text=brief)

    async def start_reply(self, project_id: str, base_revision: int, text: str, question_id: str | None) -> Operation:
        project = require(self._projects.load(project_id))
        check_base(project, base_revision)
        if question_id is not None and project.question(question_id) is None:
            raise ApplicationError("not-found", f"Question {question_id} does not exist.")
        return self._spawn("reply", subject=project_id, project=project, text=text, question_id=question_id)

    async def start_reassess(self, project_id: str, base_revision: int) -> Operation:
        project = require(self._projects.load(project_id))
        check_base(project, base_revision)
        return self._spawn("reassess", subject=project_id, project=project)

    def _spawn(
        self,
        kind: OperationKind,
        *,
        subject: str,
        project: Project | None,
        text: str | None = None,
        question_id: str | None = None,
    ) -> Operation:
        damaged = self._operations.damaged()
        if damaged:
            files = "; ".join(f"{d.file} ({d.reason})" for d in damaged)
            raise ApplicationError(
                "corrupt-record",
                "Model work is paused because an operation record cannot be read, so whether its work was applied "
                f"is unknown: {files}. Check the brief, then move that file out of the data directory and retry.",
            )
        active = self._subjects.get(subject)
        if active is not None:
            raise ApplicationError(
                "busy",
                "The model is already working on this. Wait for it to finish or cancel it.",
                active_operation_id=active,
            )
        now = self._clock()
        operation = Operation(
            id=self._new_id(),
            kind=kind,
            status="queued",
            version=1,
            project_id=project.id if project else None,
            base_revision=project.revision if project else None,
            question_id=question_id,
            text=text,
            created_at=now,
            updated_at=now,
            deadline_at=_plus_seconds(now, self._deadline_seconds),
            result=None,
            error=None,
            model_call=None,
        )
        record = OperationRecord(
            operation=operation, base_updated_at=project.updated_at if project else None, commit=None
        )
        self._operations.save(record)
        self._subjects[subject] = operation.id
        self._deadlines[operation.id] = self._monotonic() + self._deadline_seconds
        task = asyncio.get_running_loop().create_task(self._run(record), name=f"operation-{operation.id}")
        self._tasks[operation.id] = task
        task.add_done_callback(lambda _: self._forget(operation.id, subject))
        return operation

    def _forget(self, operation_id: str, subject: str) -> None:
        self._tasks.pop(operation_id, None)
        self._deadlines.pop(operation_id, None)
        self._cancel_requested.discard(operation_id)
        if self._subjects.get(subject) == operation_id:
            del self._subjects[subject]

    # --- Reading and control ----------------------------------------------------------------------

    def get(self, operation_id: str) -> Operation:
        record = self._operations.load(operation_id)
        if record is None:
            raise ApplicationError("not-found", f"Operation {operation_id} does not exist.")
        return record.operation

    def active(self) -> list[Operation]:
        live = [r.operation for r in self._operations.all() if r.operation.status not in TERMINAL]
        return sorted(live, key=lambda o: o.created_at)

    async def cancel(self, operation_id: str) -> Operation:
        operation = self.get(operation_id)
        task = self._tasks.get(operation_id)
        if operation.status in TERMINAL or task is None:
            return operation
        self._cancel_requested.add(operation_id)
        task.cancel()
        await asyncio.wait({task}, timeout=5)
        return self.get(operation_id)

    async def watch(self, operation_id: str) -> AsyncIterator[Operation]:
        """Each persisted state once, from the current one, until a terminal state."""
        last = 0
        while True:
            woken = self._signals.current(operation_id)
            operation = self.get(operation_id)
            if operation.version > last:
                last = operation.version
                yield operation
            if operation.status in TERMINAL:
                return
            with suppress(TimeoutError):
                await asyncio.wait_for(woken.wait(), timeout=SIGNAL_RECHECK_SECONDS)

    def recover(self) -> None:
        """After a restart nothing is running. Unfinished operations become interrupted, unless their
        commit marker shows the project write completed, in which case they succeeded. Unreadable records
        are left as they are."""
        for record in self._operations.all():
            if record.operation.status not in TERMINAL:
                self._reconcile(record, "interrupted", _interrupted())
        for damaged in self._operations.damaged():
            log.error(
                "operation record %s cannot be read (%s); model work waits until it is moved",
                damaged.file,
                damaged.reason,
            )

    def damaged(self) -> list[DamagedOperation]:
        return self._operations.damaged()

    async def shutdown(self, grace_seconds: float = 10.0) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=grace_seconds)

    # --- Running ----------------------------------------------------------------------------------

    def _save(self, record: OperationRecord, **changes: object) -> OperationRecord:
        operation = record.operation.model_copy(
            update={**changes, "version": record.operation.version + 1, "updated_at": self._clock()}
        )
        updated = record.model_copy(update={"operation": operation})
        self._operations.save(updated)
        self._signals.notify(operation.id)
        return updated

    def _finish(
        self,
        record: OperationRecord,
        status: OperationStatus,
        *,
        result: OperationResult | None = None,
        error: OperationError | None = None,
        model_call: ModelCall | None = None,
    ) -> OperationRecord:
        changes: dict[str, object] = {"status": status, "result": result, "error": error}
        if model_call is not None:
            changes["model_call"] = model_call
        finished = self._save(record, **changes)
        op = finished.operation
        log.info(
            "operation finished id=%s kind=%s status=%s project=%s error=%s",
            op.id,
            op.kind,
            op.status,
            op.project_id or (result.project_id if result else None),
            error.kind if error else None,
        )
        return finished

    def _request(self, op: Operation, project: Project | None) -> AssessRequest:
        if op.kind == "create":
            return AssessRequest(mode="brief", project=None, text=op.text)
        if op.kind == "reply":
            return AssessRequest(mode="reply", project=project, text=op.text, question_id=op.question_id)
        last = project.decisions[-1].summary if project and project.decisions else "No recent choice."
        return AssessRequest(mode="reassess", project=project, event=last)

    async def _run(self, record: OperationRecord) -> None:
        op_id = record.operation.id
        try:
            async with self._semaphore:
                record = self._save(record, status="running")
                await self._assess_and_commit(record)
        except asyncio.CancelledError:
            current = self._operations.load(op_id) or record
            if current.operation.status not in TERMINAL:
                self._stop(current)
        except Exception:
            log.exception("operation %s failed unexpectedly", op_id)
            current = self._operations.load(op_id) or record
            if current.operation.status not in TERMINAL:
                # The error may have come after the project was saved, so the saved state decides, as at startup.
                self._reconcile(
                    current,
                    "failed",
                    OperationError(
                        kind="internal",
                        message="The server failed while working on this. Nothing was changed.",
                        retryable=True,
                    ),
                )

    async def _assess_and_commit(self, record: OperationRecord) -> None:
        op = record.operation
        project: Project | None = None
        if op.project_id is not None:
            project = require(self._projects.load(op.project_id))
            if project.revision != op.base_revision or project.updated_at != record.base_updated_at:
                self._finish(record, "failed", error=_stale())
                return
        request = self._request(op, project)
        started = self._monotonic()
        remaining = self._deadlines.get(op.id, started) - started
        attempts: list[CallAttempt] = []
        try:
            async with asyncio.timeout(max(remaining, 0.0)):
                reply = await self._assessor.assess(request, attempts)
        except TimeoutError:
            call = self._model_call(attempts, None, started) if attempts else None
            self._log_call(op, attempts, call, outcome="call-failed", error="deadline exceeded")
            self._finish(record, "failed", error=_deadline_exceeded(_maybe_charged(call)), model_call=call)
            return
        except ModelCallError as e:
            call = self._model_call(attempts, None, started) if attempts else None
            self._log_call(op, attempts, call, outcome="call-failed", error=e.message)
            error = OperationError(kind=e.kind, message=e.message, retryable=e.retryable)
            self._finish(record, "failed", error=error, model_call=call)
            return
        except asyncio.CancelledError:
            # Cancelled or shut down while the model was working: account for what was sent before stopping.
            call = self._model_call(attempts, None, started) if attempts else None
            reason = "cancelled" if op.id in self._cancel_requested else "interrupted"
            self._log_call(op, attempts, call, outcome=reason, error=reason)
            self._stop(record, call)
            raise

        model_call = self._model_call(attempts, reply, started)
        ctx = ProposalContext(
            mode=request.mode, new_text=request.text, project=project, target_question_id=request.question_id
        )
        validation = validate_proposal(reply.raw, ctx)
        self._log_call(
            op,
            attempts,
            model_call,
            outcome="valid" if isinstance(validation, Valid) else "rejected",
            reply=reply,
            validation=validation,
        )
        if isinstance(validation, Invalid):
            self._finish(
                record,
                "failed",
                model_call=model_call,
                error=OperationError(
                    kind="invalid-output",
                    message="The model's response did not pass validation, so nothing was changed.",
                    retryable=True,
                    issues=validation.issues,
                ),
            )
            return
        await self._commit(record, reply, validation, model_call)

    async def _commit(self, record: OperationRecord, reply: ModelReply, valid: Valid, model_call: ModelCall) -> None:
        op = record.operation
        project_id = op.project_id or self._new_id()
        async with self._locks(project_id):
            # No awaits below: the commit cannot be interrupted part-way by cancellation.
            at = self._clock()
            if op.kind == "create":
                changed = create_project(
                    project_id=project_id,
                    at=at,
                    brief=op.text or "",
                    proposal=valid.proposal,
                    interpreted_by=reply.interpreted_by,
                )
            else:
                loaded = self._projects.load(project_id)
                current = loaded.project if isinstance(loaded, Found) else None
                if (
                    current is None
                    or current.revision != op.base_revision
                    or current.updated_at != record.base_updated_at
                ):
                    self._finish(record, "failed", model_call=model_call, error=_stale())
                    return
                changed = (
                    apply_user_text(
                        current,
                        at=at,
                        kind="reply",
                        text=op.text or "",
                        question_id=op.question_id,
                        proposal=valid.proposal,
                        interpreted_by=reply.interpreted_by,
                    )
                    if op.kind == "reply"
                    else apply_reassessment(current, at=at, proposal=valid.proposal, proposed_by=reply.interpreted_by)
                )
            marker = CommitMarker(
                at=changed.updated_at,
                project_id=project_id,
                revision=changed.revision,
                notes=valid.notes,
                model_call=model_call,
            )
            marked = record.model_copy(update={"commit": marker})
            self._operations.save(marked)
            self._projects.save(changed)
            self._finish(marked, "succeeded", model_call=model_call, result=_committed(marker))

    def _reconcile(self, record: OperationRecord, status: OperationStatus, error: OperationError) -> None:
        """Finish an operation whose run ended without reporting its outcome. A commit marker whose write reached
        the project means it succeeded. A commit that cannot be confirmed either way is never reported as having
        changed nothing. Otherwise nothing was written, and it ends with `status` and `error`."""
        marker = record.commit
        state = self._commit_state(marker) if marker else "absent"
        call = marker.model_call if marker else None
        if marker is not None and state == "committed":
            self._finish(record, "succeeded", result=_committed(marker), model_call=call)
        elif state == "unconfirmed":
            self._finish(record, "interrupted", error=_unconfirmed(), model_call=call)
        else:
            self._finish(record, status, error=error, model_call=call)

    def _commit_state(self, marker: CommitMarker) -> Literal["committed", "absent", "unconfirmed"]:
        """Whether the saved project is the one the marker announced. Writes replace the file atomically, so a
        readable project either is that revision or was never replaced."""
        try:
            loaded = self._projects.load(marker.project_id)
        except Exception:
            log.exception("could not read project %s to confirm a commit", marker.project_id)
            return "unconfirmed"
        if isinstance(loaded, Found):
            same = loaded.project.updated_at == marker.at and loaded.project.revision == marker.revision
            return "committed" if same else "absent"
        return "absent" if isinstance(loaded, Missing) else "unconfirmed"

    def _stop(self, record: OperationRecord, call: ModelCall | None = None) -> None:
        """Finish an operation the user cancelled or a shutdown interrupted."""
        if record.operation.id in self._cancel_requested:
            self._finish(record, "cancelled", error=_cancelled(_maybe_charged(call)), model_call=call)
        else:
            self._finish(record, "interrupted", error=_interrupted(_maybe_charged(call)), model_call=call)

    def _model_call(self, attempts: Sequence[CallAttempt], reply: ModelReply | None, started: float) -> ModelCall:
        cost = known_cost(attempts)
        reported = any(a.cost_status == "reported" for a in attempts)
        if cost is None:
            cost_status = "unknown"
        elif reported:
            cost_status = "reported"
        else:
            cost, cost_status = None, "not-charged"
        return ModelCall(
            requested_model=reply.requested_model if reply else self._assessor.label,
            served_model=reply.served_model if reply else None,
            provider=reply.provider if reply else None,
            prompt_version=reply.prompt_version if reply else None,
            attempts=len(attempts),
            ambiguous_attempts=sum(a.outcome == "ambiguous" for a in attempts),
            latency_ms=round((self._monotonic() - started) * 1000),
            prompt_tokens=reply.usage.prompt_tokens if reply else None,
            completion_tokens=reply.usage.completion_tokens if reply else None,
            cost=cost,
            cost_status=cost_status,
        )

    def _log_call(
        self,
        op: Operation,
        attempts: Sequence[CallAttempt],
        call: ModelCall | None,
        *,
        outcome: str,
        reply: ModelReply | None = None,
        error: str | None = None,
        validation: Valid | Invalid | None = None,
    ) -> None:
        """One line per submitted attempt, or one line when nothing was submitted. An attempt without an answer
        keeps its own outcome; the last line also carries the call's error, summary, and raw answer. Raw exchanges
        stay local (data/ is git-ignored) so live behavior can be inspected later."""
        lines: Sequence[CallAttempt | None] = attempts or [None]
        for index, attempt in enumerate(lines):
            last = index == len(lines) - 1
            self._call_log.append(
                {
                    "at": self._clock(),
                    "operationId": op.id,
                    "mode": op.kind,
                    "projectId": op.project_id,
                    "revision": op.base_revision,
                    "requestedModel": self._assessor.label,
                    "attempt": attempt.number if attempt else None,
                    "outcome": attempt.outcome if attempt and attempt.outcome != "answered" else outcome,
                    "httpStatus": attempt.http_status if attempt else None,
                    "failure": attempt.failure if attempt else None,
                    "cost": attempt.cost if attempt else None,
                    "costStatus": attempt.cost_status if attempt else None,
                    "model": call.model_dump(mode="json") if call and last else None,
                    "userText": op.text,
                    "raw": reply.raw if reply and last else None,
                    "error": error if last else None,
                    "issues": list(validation.issues) if last and isinstance(validation, Invalid) else [],
                    "notes": list(validation.notes) if last and isinstance(validation, Valid) else [],
                }
            )


_MAY_HAVE_RUN = (
    "Nothing in the brief changed, but the provider may still have processed the request and charged for it."
)


def _maybe_charged(call: ModelCall | None) -> bool:
    return call is not None and call.ambiguous_attempts > 0


def _unchanged(maybe_charged: bool) -> str:
    return _MAY_HAVE_RUN if maybe_charged else "Nothing was changed."


def _deadline_exceeded(maybe_charged: bool) -> OperationError:
    message = (
        f"The model did not finish within the time limit. {_MAY_HAVE_RUN}"
        if maybe_charged
        else "The model did not finish within the time limit, including retries. Nothing was changed."
    )
    return OperationError(kind="deadline-exceeded", message=message, retryable=True)


def _cancelled(maybe_charged: bool) -> OperationError:
    return OperationError(kind="cancelled", message=f"Cancelled. {_unchanged(maybe_charged)}", retryable=True)


def _interrupted(maybe_charged: bool = False) -> OperationError:
    return OperationError(
        kind="interrupted",
        message=f"The server stopped before this finished. {_unchanged(maybe_charged)} Retry when ready.",
        retryable=True,
    )


def _committed(marker: CommitMarker) -> OperationResult:
    return OperationResult(project_id=marker.project_id, revision=marker.revision, notes=marker.notes)


def _unconfirmed() -> OperationError:
    # Not retryable from the interface: if the change did land, a retry would apply it twice.
    return OperationError(
        kind="internal",
        message="The server failed while saving this and could not confirm whether the change was applied. "
        "Reload to see the current brief before trying again.",
        retryable=False,
    )


def _stale() -> OperationError:
    return OperationError(
        kind="conflict",
        message="The brief changed while the model was working. Nothing was applied. Reload and retry.",
        retryable=False,
    )
