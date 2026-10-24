"""The single project record. Immutable values; transitions return new records.

Field names, order, and the camelCase wire form match the record files the POC already wrote
(`schemaVersion: 1`), so existing projects load unchanged.
"""

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_serializer, field_validator
from pydantic.alias_generators import to_camel

IntentKind = Literal["outcome", "audience", "direction", "scope", "exclusion", "constraint", "nextStep"]
INTENT_KINDS: tuple[IntentKind, ...] = (
    "outcome",
    "audience",
    "direction",
    "scope",
    "exclusion",
    "constraint",
    "nextStep",
)
INTENT_LABELS: Mapping[IntentKind, str] = {
    "outcome": "Desired outcome",
    "audience": "Audience and circumstances",
    "direction": "Direction to pursue",
    "scope": "In scope",
    "exclusion": "Excluded",
    "constraint": "Constraints",
    "nextStep": "Next step",
}

OpenItemKind = Literal["question", "assumption", "needed"]
OpenItemStatus = Literal["open", "deferred", "answered", "relied"]
DecisionAction = Literal["brief", "reply", "select", "defer", "edit", "remove", "rely"]
InputKind = Literal["brief", "reply"]
NonEmpty = Annotated[str, Field(min_length=1)]
_SEQ_OBJECT = TypeAdapter(dict[str, int])


class Value(BaseModel):
    """Frozen, camelCase on the wire, and strict about unknown fields."""

    model_config = ConfigDict(
        frozen=True,
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Input(Value):
    id: str
    kind: InputKind
    text: NonEmpty
    at: str
    question_id: str | None
    interpreted_by: str


class QuoteSource(Value):
    """The user's own words: an explicit instruction counts as a choice."""

    type: Literal["quote"] = "quote"
    input_id: str
    quote: str


class OptionSource(Value):
    """A proposed option the user selected."""

    type: Literal["option"] = "option"
    question_id: str
    option_id: str


Source = Annotated[QuoteSource | OptionSource, Field(discriminator="type")]


class IntentItem(Value):
    id: str
    kind: IntentKind
    text: NonEmpty
    source: Source
    decision_id: str


class Statement(Value):
    kind: IntentKind
    text: NonEmpty


class Option(Value):
    id: str
    label: str
    description: str
    tradeoff: str
    establishes: tuple[Statement, ...]


class ItemSource(Value):
    input_id: str
    quote: str


class OpenItem(Value):
    id: str
    kind: OpenItemKind
    text: NonEmpty
    basis: str
    effect: str
    source: ItemSource | None
    options: tuple[Option, ...]
    defer_effect: str | None
    status: OpenItemStatus
    decision_id: str | None
    proposed_by: str


class Change(Value):
    item_id: str
    kind: IntentKind
    before: str | None
    after: str | None


class StatusChange(Value):
    item_id: str
    to: Literal["answered", "deferred", "relied"]


class Decision(Value):
    id: str
    at: str
    revision: int
    action: DecisionAction
    summary: str
    input_id: str | None
    question_id: str | None
    option_id: str | None
    reason: str | None
    changes: tuple[Change, ...]
    status_changes: tuple[StatusChange, ...]
    supersedes: tuple[str, ...]


class Review(Value):
    revision: int
    reviewed_at: str
    reviewer: Literal["local user"]
    markdown: str
    json_copy: str = Field(alias="json")


class Project(Value):
    schema_version: Literal[1]
    id: str
    title: str
    created_at: str
    updated_at: str
    revision: Annotated[int, Field(ge=0)]
    # Next number per id prefix, so ids read as s1, i1, q1, d1. Stored as an object; held as pairs.
    seq: tuple[tuple[str, int], ...]
    inputs: tuple[Input, ...]
    intent: tuple[IntentItem, ...]
    open_items: tuple[OpenItem, ...]
    focus_id: str | None
    decisions: tuple[Decision, ...]
    reviews: tuple[Review, ...]

    @field_validator("seq", mode="before")
    @classmethod
    def _seq_from_object(cls, value: object) -> object:
        return tuple(_SEQ_OBJECT.validate_python(value).items()) if isinstance(value, Mapping) else value

    @field_serializer("seq")
    def _seq_to_object(self, seq: tuple[tuple[str, int], ...]) -> dict[str, int]:
        return dict(seq)

    def question(self, question_id: str) -> OpenItem | None:
        return next((o for o in self.open_items if o.id == question_id and o.kind == "question"), None)

    def item(self, item_id: str) -> OpenItem | None:
        return next((o for o in self.open_items if o.id == item_id), None)

    def decision(self, decision_id: str | None) -> Decision | None:
        return next((d for d in self.decisions if d.id == decision_id), None)

    def input(self, input_id: str | None) -> Input | None:
        return next((i for i in self.inputs if i.id == input_id), None)


def is_reviewed(p: Project) -> bool:
    return any(r.revision == p.revision for r in p.reviews)


def last_review(p: Project) -> Review | None:
    return p.reviews[-1] if p.reviews else None


def superseded_by(p: Project, decision_id: str) -> str | None:
    return next((d.id for d in p.decisions if decision_id in d.supersedes), None)


def answering_decision(p: Project, question: OpenItem) -> Decision | None:
    """The decision that set this question's current status, if any."""
    return p.decision(question.decision_id) if question.status != "open" else None
