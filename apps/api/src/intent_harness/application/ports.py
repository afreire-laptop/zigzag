"""What the application needs from the outside world. Adapters implement these; tests use the real
file adapters on temporary directories and stubbed model transports."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from intent_harness.domain.model import Project

# --- Project persistence ------------------------------------------------------------------------


@dataclass(frozen=True)
class Found:
    project: Project


@dataclass(frozen=True)
class Missing:
    project_id: str


@dataclass(frozen=True)
class Corrupt:
    """A record file that cannot be read or fails its invariants. It is never modified or skipped."""

    project_id: str
    file: str
    reason: str
    modified_at: str


type Loaded = Found | Missing | Corrupt


class ProjectStore(Protocol):
    def load(self, project_id: str) -> Loaded: ...

    def most_recent(self) -> Found | Corrupt | None:
        """The most recently updated record, or the damaged file if that is the most recent one."""
        ...

    def save(self, project: Project) -> None:
        """Atomically replace the record. Refuses records that fail their invariants. Raises only if the stored
        record is unchanged."""
        ...


class CallLog(Protocol):
    def append(self, entry: Mapping[str, object]) -> None: ...


# --- Model assessment ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssessRequest:
    mode: Literal["brief", "reply", "reassess"]
    project: Project | None
    text: str | None = None
    question_id: str | None = None
    event: str | None = None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Credits reported by the gateway. None means the cost is unknown, never zero.
    cost: float | None = None


AttemptOutcome = Literal["answered", "not-processed", "ambiguous"]
AttemptCostStatus = Literal["reported", "unknown", "not-charged", "unknown-may-have-been-charged"]


@dataclass(frozen=True)
class CallAttempt:
    """One request to the model and what is known about it.

    - answered: a response was read. `cost` is what the gateway reported; None means it reported none.
    - not-processed: the request was never sent, or was rejected before any model processed it. Nothing was charged.
    - ambiguous: the request may have reached the model, but no usable answer came back (a timeout, a dropped
      connection, an unreadable answer, a cancellation). It may still have been processed and charged."""

    number: int
    outcome: AttemptOutcome
    http_status: int | None = None
    # Why no answer was read: the exception type, "cancelled", or what was wrong with a 200.
    failure: str | None = None
    cost: float | None = None

    @property
    def cost_status(self) -> AttemptCostStatus:
        if self.outcome == "not-processed":
            return "not-charged"
        if self.outcome == "ambiguous":
            return "unknown-may-have-been-charged"
        return "reported" if self.cost is not None else "unknown"


def known_cost(attempts: Sequence[CallAttempt]) -> float | None:
    """The credits these attempts cost, or None when any attempt's cost is unknown. Unknown is never zero."""
    if any(a.cost_status not in ("reported", "not-charged") for a in attempts):
        return None
    return sum(a.cost or 0.0 for a in attempts)


@dataclass(frozen=True)
class ModelReply:
    raw: str
    # Who read the text, as recorded on the project: the served model id, or a fixture label.
    interpreted_by: str
    requested_model: str
    served_model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    # Tokens and cost of the answered attempt. Every attempt, including failed ones, is in the attempts record.
    usage: Usage = field(default_factory=Usage)


ModelErrorKind = Literal[
    "model-credentials",
    "model-insufficient-credits",
    "model-rate-limited",
    "model-unavailable",
    "model-rejected",
    "model-declined",
    "model-incomplete",
    "model-timeout",
    "fixture-miss",
]


class ModelCallError(Exception):
    def __init__(
        self,
        kind: ModelErrorKind,
        message: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind: ModelErrorKind = kind
        self.message = message
        # Whether the user may retry. Never a reason to repeat a request automatically; see CallAttempt.
        self.retryable = retryable
        # Seconds the provider asked us to wait before retrying, when it said.
        self.retry_after = retry_after


class Assessor(Protocol):
    """Reads user text against the current state and returns a raw, unvalidated proposal.

    Each request it submits is appended to `attempts` as it settles, including one cut off by cancellation, so
    the caller can account for every attempt even when this call never returns."""

    @property
    def label(self) -> str: ...

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply: ...


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    schema_name: str
    schema: Mapping[str, object]
    max_output_tokens: int


@dataclass(frozen=True)
class Completion:
    content: str
    served_model: str | None
    provider: str | None
    finish_reason: str | None
    usage: Usage


class CompletionClient(Protocol):
    """A domain-independent structured-output completion: system and user text in, JSON text out."""

    @property
    def requested_model(self) -> str: ...

    async def complete(self, request: CompletionRequest, attempts: list[CallAttempt]) -> Completion:
        """Appends each request it submits to `attempts`, as `Assessor.assess` does."""
        ...


# --- Effects ------------------------------------------------------------------------------------

Clock = Callable[[], str]
"""The current time as an ISO 8601 UTC string with milliseconds."""

NewId = Callable[[], str]
"""A fresh short identifier."""
