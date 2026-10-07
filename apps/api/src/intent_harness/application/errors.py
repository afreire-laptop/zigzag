"""Typed application errors. The HTTP adapter maps each kind to a status and a problem response."""

from typing import Literal

ErrorKind = Literal[
    "not-found",
    "invalid-request",
    "conflict",
    "busy",
    "corrupt-record",
    "model-credentials",
    "model-insufficient-credits",
    "model-rate-limited",
    "model-unavailable",
    "model-rejected",
    "model-declined",
    "model-incomplete",
    "model-timeout",
    "invalid-output",
    "deadline-exceeded",
    "fixture-miss",
    "cancelled",
    "interrupted",
    "internal",
]


class ApplicationError(Exception):
    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        retryable: bool = False,
        issues: tuple[str, ...] = (),
        active_operation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.message = message
        self.retryable = retryable
        self.issues = issues
        self.active_operation_id = active_operation_id
