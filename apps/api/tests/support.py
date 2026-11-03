"""Shared test helpers: fixture paths, validated proposals, and small project builders."""

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from zigzag.domain.model import OpenItem, Option, Project
from zigzag.domain.proposal import ProposalContext, Valid, ValidProposal, validate_proposal
from zigzag.domain.transitions import create_project

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "fixtures"


def journeys() -> dict[str, Any]:
    return json.loads((FIXTURES / "journeys.json").read_text())


def at(minute: int) -> str:
    return f"2026-10-05T10:{minute:02d}:00.000Z"


def validated(raw: object, ctx: ProposalContext) -> ValidProposal:
    result = validate_proposal(json.dumps(raw), ctx)
    assert isinstance(result, Valid), f"fixture failed validation: {result}"
    return result.proposal


def rule(name: str) -> dict[str, Any]:
    return next(r for r in journeys()["rules"] if r["name"] == name)


def canned(name: str, project: Project | None = None) -> dict[str, Any]:
    """A canned proposal with any {"questionText": ...} reference resolved against the project."""
    raw = json.loads(json.dumps(rule(name)["respond"][0]))
    for r in raw.get("resolutions", []):
        if isinstance(r["questionId"], dict):
            assert project is not None
            r["questionId"] = question(project, r["questionId"]["questionText"]).id
    return raw


def text(label_or_key: str) -> str:
    texts = journeys()["texts"]
    for entry in [*texts["briefs"], *texts["replies"]]:
        if entry["label"] == label_or_key:
            return entry["text"]
    return texts[label_or_key]


CLEAR = "Clear brief (journey 1)"
AMBIGUOUS = "Ambiguous brief (journey 2)"
FOCUS_QUESTION = "Which improvement should we investigate first?"
SOFTWARE_QUESTION = "Does this need new software, a better process, or both?"


def project_from(brief_label: str, rule_name: str, project_id: str = "test1") -> Project:
    brief = text(brief_label)
    proposal = validated(canned(rule_name), ProposalContext("brief", brief, None))
    return create_project(project_id=project_id, at=at(0), brief=brief, proposal=proposal, interpreted_by="stub")


def question(p: Project, question_text: str) -> OpenItem:
    return next(o for o in p.open_items if o.kind == "question" and o.text == question_text)


def option(p: Project, question_text: str, label: str) -> Option:
    return next(o for o in question(p, question_text).options if o.label == label)


def failing_fsync(monkeypatch: pytest.MonkeyPatch, *, directories: bool) -> None:
    """Makes fsync fail with an I/O error for directories, or for regular files, as a failing disk would."""
    real = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode) == directories:
            raise OSError(5, "Input/output error")
        real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
