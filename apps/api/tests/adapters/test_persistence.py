"""File persistence: atomic replacement, refusal of inconsistent records, and compatibility with records
written by the legacy implementation."""

import json
import os
from pathlib import Path

import pytest

from intent_harness.adapters.persistence.files import FileOperationStore, FileProjectStore, InconsistentRecordError
from intent_harness.application.ports import Corrupt, Found, Missing
from intent_harness.domain.handoff import current_exports
from tests.support import CLEAR, GOLDEN, failing_fsync, project_from


def test_save_replaces_atomically_and_leaves_no_temporary_files(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project = project_from(CLEAR, "clear brief", project_id="p1")
    store.save(project)
    store.save(project.model_copy(update={"title": "Renamed"}))
    assert [p.name for p in (tmp_path / "projects").iterdir()] == ["p1.json"]
    loaded = store.load("p1")
    assert isinstance(loaded, Found)
    assert loaded.project.title == "Renamed"


def title_of(store: FileProjectStore, project_id: str) -> str:
    loaded = store.load(project_id)
    assert isinstance(loaded, Found)
    return loaded.project.title


@pytest.mark.parametrize("step", ["temporary file sync", "directory open"])
def test_a_write_that_fails_before_the_rename_keeps_the_old_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    store = FileProjectStore(tmp_path)
    project = project_from(CLEAR, "clear brief", project_id="p1")
    store.save(project)
    if step == "temporary file sync":
        failing_fsync(monkeypatch, directories=False)
    else:
        real_open = os.open

        def open_(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
            if Path(path) == tmp_path / "projects":
                raise OSError(24, "Too many open files")
            return real_open(path, flags, mode)

        monkeypatch.setattr(os, "open", open_)
    with pytest.raises(OSError, match=r"Input/output error|Too many open files"):
        store.save(project.model_copy(update={"title": "Renamed"}))
    monkeypatch.undo()
    assert title_of(store, "p1") == project.title  # a raised save left the record as it was
    assert [p.name for p in (tmp_path / "projects").iterdir()] == ["p1.json"]  # and no temporary file


def test_a_write_already_visible_is_not_reported_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = FileProjectStore(tmp_path)
    project = project_from(CLEAR, "clear brief", project_id="p1")
    store.save(project)
    failing_fsync(monkeypatch, directories=True)  # the sync that follows the rename
    store.save(project.model_copy(update={"title": "Renamed"}))
    assert title_of(store, "p1") == "Renamed"
    assert "may not survive a crash" in caplog.text


def test_inconsistent_records_are_never_written(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project = project_from(CLEAR, "clear brief", project_id="p1")
    tampered = project.model_copy(update={"intent": (project.intent[0].model_copy(update={"text": "Silently."}),)})
    with pytest.raises(InconsistentRecordError):
        store.save(tampered)
    assert store.load("p1") == Missing("p1")


def test_unknown_ids_and_unsafe_names_are_missing(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    assert store.load("nope") == Missing("nope")
    assert store.load("../etc/passwd") == Missing("../etc/passwd")
    assert store.most_recent() is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"\xff\xfe", "Invalid JSON"),
        (b"{}", "schemaVersion"),
    ],
)
def test_unreadable_files_are_reported(tmp_path: Path, content: bytes, reason: str) -> None:
    store = FileProjectStore(tmp_path)
    (tmp_path / "projects" / "bad.json").write_bytes(content)
    loaded = store.load("bad")
    assert isinstance(loaded, Corrupt)
    assert reason in loaded.reason
    assert (tmp_path / "projects" / "bad.json").read_bytes() == content


def test_a_file_holding_another_project_is_reported(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    store.save(project_from(CLEAR, "clear brief", project_id="p1"))
    (tmp_path / "projects" / "p2.json").write_bytes((tmp_path / "projects" / "p1.json").read_bytes())
    loaded = store.load("p2")
    assert isinstance(loaded, Corrupt)
    assert "holds project p1" in loaded.reason


@pytest.mark.parametrize(
    "path", sorted(p for p in GOLDEN.glob("*.json") if p.name != "validation.json"), ids=lambda p: p.stem
)
def test_records_written_by_the_legacy_implementation_load_and_export_unchanged(tmp_path: Path, path: Path) -> None:
    scenario = json.loads(path.read_text())
    store = FileProjectStore(tmp_path)
    final = scenario["snapshots"][-1]
    project_id = json.loads(final["storedFile"])["id"]
    (tmp_path / "projects" / f"{project_id}.json").write_text(final["storedFile"])
    loaded = store.load(project_id)
    assert isinstance(loaded, Found), loaded
    if final["exports"]["status"] == "reviewed" or scenario["name"] != "ambiguous-deferred-by-reply-then-selected":
        exports = current_exports(loaded.project)
        assert (exports.markdown, exports.json) == (final["exports"]["markdown"], final["exports"]["json"])


def test_unreadable_operation_files_are_reported_not_deleted(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path)
    (tmp_path / "operations" / "broken.json").write_text("{")
    assert store.all() == []
    [damaged] = store.damaged()
    assert damaged.file == str(tmp_path / "operations" / "broken.json")
    assert "JSON" in damaged.reason
    assert store.load("missing") is None
    assert (tmp_path / "operations" / "broken.json").read_text() == "{"
