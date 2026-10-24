"""Fixture mode: canned responses read from a JSON file of rules, for repeatable UI work and browser tests.
No network access. Every response is labeled as a fixture wherever it appears and passes the same
validation as live output. The canned texts live in the data file, not in application code."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from zigzag.application.ports import AssessRequest, CallAttempt, ModelCallError, ModelReply
from zigzag.domain.model import Project
from zigzag.domain.text import normalize_for_match

FIXTURE_LABEL = "fixture (canned, not a live model)"
type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, frozen=True, extra="forbid")


class FixtureText(_Model):
    label: str
    text: str


class FixtureTexts(_Model):
    briefs: tuple[FixtureText, ...]
    replies: tuple[FixtureText, ...]
    paraphrased_brief: str | None = None


class When(_Model):
    mode: Literal["brief", "reply", "reassess"]
    text: str | None = None
    brief: str | None = None
    last_selected_option_label: str | None = None
    absent_question: str | None = None


class Rule(_Model):
    name: str
    when: When
    # Successive calls matching this rule get successive responses; the last one repeats.
    # A string is returned as raw text, so a rule can also exercise invalid output.
    respond: tuple[Json, ...] = Field(min_length=1)


class FixtureFile(_Model):
    note: str
    texts: FixtureTexts
    rules: tuple[Rule, ...]


def load_fixtures(path: Path) -> FixtureFile:
    return FixtureFile.model_validate_json(path.read_bytes())


def _same(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and normalize_for_match(a) == normalize_for_match(b)


def _last_selected_label(project: Project) -> str | None:
    last = project.decisions[-1] if project.decisions else None
    if last is None or last.action != "select" or last.question_id is None:
        return None
    q = project.question(last.question_id)
    return next((o.label for o in q.options if o.id == last.option_id), None) if q else None


def _matches(when: When, request: AssessRequest) -> bool:
    project = request.project
    if when.mode != request.mode:
        return False
    if when.text is not None and not _same(when.text, request.text):
        return False
    if when.brief is not None and not (project and project.inputs and _same(when.brief, project.inputs[0].text)):
        return False
    if when.last_selected_option_label is not None and (
        project is None or _last_selected_label(project) != when.last_selected_option_label
    ):
        return False
    return when.absent_question is None or not (
        project and any(o.text == when.absent_question for o in project.open_items)
    )


def _resolve_question_refs(node: Json, project: Project | None) -> Json:
    """Canned replies name questions by text; ids are assigned at run time."""
    if isinstance(node, list):
        return [_resolve_question_refs(x, project) for x in node]
    if not isinstance(node, dict):
        return node
    text = node.get("questionText")
    if isinstance(text, str) and len(node) == 1:
        found = next((o.id for o in project.open_items if o.text == text), None) if project else None
        return found or f"unknown question: {text}"
    return {k: _resolve_question_refs(v, project) for k, v in node.items()}


class FixtureAssessor:
    def __init__(self, fixtures: FixtureFile) -> None:
        self._fixtures = fixtures
        self._calls: dict[str, int] = {}

    @property
    def label(self) -> str:
        return "fixture"

    @property
    def texts(self) -> FixtureTexts:
        return self._fixtures.texts

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply:
        rule = next((r for r in self._fixtures.rules if _matches(r.when, request)), None)
        if rule is None:
            raise ModelCallError(
                "fixture-miss",
                "Fixture mode only knows the journey fixtures (fixtures/journeys.json). "
                "Use one of those texts, or run with a live model.",
                retryable=False,
            )
        count = self._calls.get(rule.name, 0)
        self._calls[rule.name] = count + 1
        response = rule.respond[min(count, len(rule.respond) - 1)]
        raw = response if isinstance(response, str) else json.dumps(_resolve_question_refs(response, request.project))
        attempts.append(CallAttempt(1, "answered"))  # no network call and no reported cost
        return ModelReply(raw=raw, interpreted_by=FIXTURE_LABEL, requested_model="fixture", prompt_version=None)
