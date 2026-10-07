"""Transport-only models: request bodies, status, and problem responses. Response bodies for projects,
handoffs, and operations are the application's own read models. All of these feed the OpenAPI contract."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StringConstraints

from intent_harness.application.operations import DamagedOperation
from intent_harness.domain.model import Value
from intent_harness.domain.view import ProjectView


def _blank_to_none(value: object) -> object:
    return value.strip() or None if isinstance(value, str) else value


Reason = Annotated[Annotated[str, Field(max_length=1000)] | None, BeforeValidator(_blank_to_none)]
UserText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]


class CreateProjectRequest(Value):
    brief: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


class ReplyRequest(Value):
    text: UserText
    question_id: str | None = Field(
        description="The question the user chose to answer. Only that question may be re-answered."
    )
    base_revision: int


class AssessmentRequest(Value):
    base_revision: int


class SelectCommand(Value):
    type: Literal["select"]
    question_id: str
    option_id: str
    reason: Reason = None
    base_revision: int


class DeferCommand(Value):
    type: Literal["defer"]
    question_id: str
    reason: Reason = None
    base_revision: int


class EditCommand(Value):
    type: Literal["edit"]
    item_id: str
    text: Annotated[str, Field(max_length=2_000)]
    base_revision: int


class RemoveCommand(Value):
    type: Literal["remove"]
    item_id: str
    base_revision: int


class RelyCommand(Value):
    type: Literal["rely"]
    item_id: str
    base_revision: int


DecisionCommand = Annotated[
    SelectCommand | DeferCommand | EditCommand | RemoveCommand | RelyCommand, Field(discriminator="type")
]


class ReviewRequest(Value):
    revision: int


class FixtureTextView(Value):
    label: str
    text: str


class FixtureTextsView(Value):
    briefs: tuple[FixtureTextView, ...]
    replies: tuple[FixtureTextView, ...]


class StatusView(Value):
    mode: Literal["fixture", "live"]
    model: str
    reasoning_effort: Literal["low", "medium", "high"] | None
    prompt_version: str | None
    # Fixture mode only: the journey texts that have canned responses.
    fixtures: FixtureTextsView | None
    damaged_operations: tuple[DamagedOperation, ...] = Field(
        description="Operation records that cannot be read. Model work is refused until each is moved aside."
    )


class RecoveryView(Value):
    project_id: str
    file: str
    reason: str
    modified_at: str


class CurrentProjectView(Value):
    state: Literal["empty", "ready", "corrupt"]
    project: ProjectView | None
    recovery: RecoveryView | None


class Health(Value):
    status: Literal["ok"]


class Problem(Value):
    """An RFC 9457 problem with this API's extension members."""

    type: str
    title: str
    status: int
    detail: str
    kind: str
    retryable: bool
    issues: tuple[str, ...] = ()
    active_operation_id: str | None = None
