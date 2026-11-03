"""Local file persistence: one JSON file per project and per operation, replaced atomically, plus an
append-only log of raw model exchanges. Damaged files are reported and never modified or skipped."""

import json
import logging
import os
import re
import secrets
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from zigzag.application.operations import DamagedOperation, OperationRecord
from zigzag.application.ports import Corrupt, Found, Loaded, Missing
from zigzag.domain.invariants import check_invariants
from zigzag.domain.model import Project

_ID = re.compile(r"^[a-z0-9-]{1,64}$")
log = logging.getLogger("zigzag.persistence")


class InconsistentRecordError(Exception):
    """A transition produced a record that fails its invariants. A bug: nothing is written."""


def _write_atomically(target: Path, text: str) -> None:
    """Write beside the target, flush to disk, then rename over it, so readers see old or new, never half.

    It raises only while the old content is still in place, so callers can treat a raised save as nothing
    written. Everything that can fail is done before the rename. The directory sync that makes the rename
    durable can only follow it. If that sync fails, every reader already sees the new content, so the write is
    not reported as failed; the failure is logged, because the rename may not survive a crash."""
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        temp = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            temp.replace(target)
        except BaseException:
            with suppress(OSError):
                temp.unlink(missing_ok=True)
            raise
        try:
            os.fsync(directory)
        except OSError:
            log.exception("Replaced %s, but syncing its directory failed: the change may not survive a crash", target)
    finally:
        with suppress(OSError):
            os.close(directory)


def project_text(project: Project) -> str:
    """The exact text of a project's file."""
    return json.dumps(project.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def _reason(error: ValidationError) -> str:
    first = error.errors()[0]
    return f"{'.'.join(str(p) for p in first['loc']) or 'file'}: {first['msg']}"


def _modified_at(path: Path) -> str:
    moment = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FileProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "projects"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, project_id: str) -> Path:
        return self._dir / f"{project_id}.json"

    def _read(self, path: Path) -> Found | Corrupt:
        project_id = path.stem
        try:
            project = Project.model_validate_json(path.read_bytes())
        except ValidationError as error:
            return Corrupt(project_id, str(path), _reason(error), _modified_at(path))
        problems = check_invariants(project)
        if problems:
            return Corrupt(project_id, str(path), f"inconsistent record: {problems[0]}", _modified_at(path))
        if project.id != project_id:
            return Corrupt(project_id, str(path), f"file holds project {project.id}", _modified_at(path))
        return Found(project)

    def load(self, project_id: str) -> Loaded:
        path = self._path(project_id)
        if not _ID.match(project_id) or not path.is_file():
            return Missing(project_id)
        return self._read(path)

    def most_recent(self) -> Found | Corrupt | None:
        candidates: list[tuple[str, Found | Corrupt]] = []
        for path in self._dir.glob("*.json"):
            read = self._read(path)
            when = read.project.updated_at if isinstance(read, Found) else read.modified_at
            candidates.append((when, read))
        return max(candidates, key=lambda c: c[0])[1] if candidates else None

    def save(self, project: Project) -> None:
        problems = check_invariants(project)
        if problems:
            raise InconsistentRecordError(f"Refusing to save an inconsistent project: {' '.join(problems)}")
        _write_atomically(self._path(project.id), project_text(project))


class FileOperationStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "operations"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: OperationRecord) -> None:
        _write_atomically(self._dir / f"{record.operation.id}.json", record.model_dump_json(indent=2) + "\n")

    def load(self, operation_id: str) -> OperationRecord | None:
        path = self._dir / f"{operation_id}.json"
        if not _ID.match(operation_id) or not path.is_file():
            return None
        return OperationRecord.model_validate_json(path.read_bytes())

    def all(self) -> list[OperationRecord]:
        return [r for r in self._read_all() if isinstance(r, OperationRecord)]

    def damaged(self) -> list[DamagedOperation]:
        return [r for r in self._read_all() if isinstance(r, DamagedOperation)]

    def _read_all(self) -> list[OperationRecord | DamagedOperation]:
        found: list[OperationRecord | DamagedOperation] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                found.append(OperationRecord.model_validate_json(path.read_bytes()))
            except ValidationError as error:
                found.append(DamagedOperation(file=str(path), reason=_reason(error), modified_at=_modified_at(path)))
        return found


class JsonlCallLog:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "model-calls.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)

    def append(self, entry: Mapping[str, object]) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
