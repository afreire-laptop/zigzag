"""Project reads and deterministic user commands. Every read-modify-save runs under the project's lock,
so overlapping requests apply one after another against the revision they were based on."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from intent_harness.application.errors import ApplicationError, ErrorKind
from intent_harness.application.ports import Clock, Corrupt, Found, Missing, ProjectStore
from intent_harness.domain.handoff import current_exports
from intent_harness.domain.model import Project
from intent_harness.domain.transitions import (
    Outcome,
    Rejected,
    defer_question,
    edit_statement,
    mark_reviewed,
    rely_on_assumption,
    remove_statement,
    select_option,
)
from intent_harness.domain.view import HandoffView, ProjectView, handoff_view, project_view


class ProjectLocks:
    """One lock per project id for the single API process. Not shared across processes or workers."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def __call__(self, project_id: str) -> asyncio.Lock:
        return self._locks.setdefault(project_id, asyncio.Lock())


@dataclass(frozen=True)
class Select:
    question_id: str
    option_id: str
    reason: str | None


@dataclass(frozen=True)
class Defer:
    question_id: str
    reason: str | None


@dataclass(frozen=True)
class Edit:
    item_id: str
    text: str


@dataclass(frozen=True)
class Remove:
    item_id: str


@dataclass(frozen=True)
class Rely:
    item_id: str


type Command = Select | Defer | Edit | Remove | Rely


@dataclass(frozen=True)
class Recovery:
    project_id: str
    file: str
    reason: str
    modified_at: str


@dataclass(frozen=True)
class Current:
    state: Literal["empty", "ready", "corrupt"]
    project: ProjectView | None = None
    recovery: Recovery | None = None


@dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    body: str


def _corrupt_error(c: Corrupt) -> ApplicationError:
    return ApplicationError(
        "corrupt-record",
        f"The saved record {c.file} cannot be read ({c.reason}). It was left untouched. "
        "Restore it from a backup or move it out of the data directory, then reload.",
    )


def require(loaded: Found | Missing | Corrupt) -> Project:
    match loaded:
        case Found(project):
            return project
        case Missing(project_id):
            raise ApplicationError("not-found", f"Project {project_id} does not exist.")
        case Corrupt():
            raise _corrupt_error(loaded)


def check_base(project: Project, base_revision: int) -> None:
    if base_revision != project.revision:
        raise ApplicationError(
            "conflict",
            f"This page shows revision {base_revision}, but revision {project.revision} is saved. Reload to continue.",
        )


_REJECTION_KINDS: Mapping[str, ErrorKind] = {
    "not_found": "not-found",
    "invalid": "invalid-request",
    "conflict": "conflict",
}


def _apply(outcome: Outcome) -> Project:
    if isinstance(outcome, Rejected):
        raise ApplicationError(_REJECTION_KINDS[outcome.reason], outcome.message)
    return outcome


class ProjectService:
    def __init__(self, store: ProjectStore, locks: ProjectLocks, clock: Clock) -> None:
        self._store = store
        self._locks = locks
        self._clock = clock

    def current(self) -> Current:
        match self._store.most_recent():
            case None:
                return Current("empty")
            case Found(project):
                return Current("ready", project=project_view(project))
            case Corrupt(project_id, file, reason, modified_at):
                return Current("corrupt", recovery=Recovery(project_id, file, reason, modified_at))

    def view(self, project_id: str) -> ProjectView:
        return project_view(require(self._store.load(project_id)))

    def handoff(self, project_id: str) -> HandoffView:
        return handoff_view(require(self._store.load(project_id)))

    async def decide(self, project_id: str, base_revision: int, command: Command) -> ProjectView:
        def transition(p: Project, at: str) -> Outcome:
            match command:
                case Select(question_id, option_id, reason):
                    return select_option(p, at=at, question_id=question_id, option_id=option_id, reason=reason)
                case Defer(question_id, reason):
                    return defer_question(p, at=at, question_id=question_id, reason=reason)
                case Edit(item_id, text):
                    return edit_statement(p, at=at, item_id=item_id, text=text)
                case Remove(item_id):
                    return remove_statement(p, at=at, item_id=item_id)
                case Rely(item_id):
                    return rely_on_assumption(p, at=at, item_id=item_id)

        return await self._change(project_id, base_revision, transition)

    async def review(self, project_id: str, revision: int) -> ProjectView:
        return await self._change(project_id, revision, lambda p, at: mark_reviewed(p, at=at, revision=revision))

    async def _change(
        self, project_id: str, base_revision: int, transition: Callable[[Project, str], Outcome]
    ) -> ProjectView:
        async with self._locks(project_id):
            project = require(self._store.load(project_id))
            check_base(project, base_revision)
            changed = _apply(transition(project, self._clock()))
            self._store.save(changed)
            return project_view(changed)

    def export(self, project_id: str, fmt: Literal["markdown", "json"], revision: int | None) -> ExportFile:
        project = require(self._store.load(project_id))
        wanted = project.revision if revision is None else revision
        if wanted == project.revision:
            exports = current_exports(project)
            status, markdown, json_text = exports.status, exports.markdown, exports.json
        else:
            review = next((r for r in project.reviews if r.revision == wanted), None)
            if review is None:
                raise ApplicationError("not-found", "Only the current revision and reviewed revisions can be exported.")
            status, markdown, json_text = "reviewed", review.markdown, review.json_copy
        extension, media_type, body = (
            ("md", "text/markdown; charset=utf-8", markdown)
            if fmt == "markdown"
            else ("json", "application/json; charset=utf-8", json_text)
        )
        return ExportFile(f"intent-handoff-{project.id}-r{wanted}-{status}.{extension}", media_type, body)
