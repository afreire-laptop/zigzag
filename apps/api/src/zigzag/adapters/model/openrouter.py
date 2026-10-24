"""OpenRouter structured-output completions over its OpenAI-compatible Chat Completions endpoint.

Everything is passed in explicitly. The client never reads environment variables, proxy settings, or
netrc credentials, so unrelated shell configuration cannot redirect requests or leak another key."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from zigzag.application.ports import (
    AttemptOutcome,
    CallAttempt,
    Completion,
    CompletionRequest,
    ModelCallError,
    ModelErrorKind,
    Usage,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_BACKOFF_SECONDS = 8.0


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str | None = None


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None


class _ChatResponse(BaseModel):
    """The fields this adapter relies on. The response is untrusted input and is validated."""

    model_config = ConfigDict(extra="ignore")
    model: str | None = None
    provider: str | None = None
    choices: list[_Choice]
    usage: _Usage | None = None


class _ErrorBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = ""


class _ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    error: _ErrorBody


# Retry policy. OpenRouter commits `200 OK` "as soon as the provider accepts the request", and reports every
# failure after that point inside the response body, so an error status means no provider accepted the request
# (https://openrouter.ai/docs/api_reference/errors-and-debugging, "Mid-stream errors"). A request is repeated
# automatically only when it was certainly not processed:
# - it was never sent: no connection could be opened, or none was free in the pool;
# - 429: rate limited by OpenRouter or refused by the provider; "honor the Retry-After header"
#   (https://openrouter.ai/docs/api_reference/limits, "Handling 429 errors");
# - 503: "There is no available model provider that meets your routing requirements" (errors-and-debugging).
# Everything else that follows a sent request may have reached the model and may still be processed and charged:
# read timeouts, dropped connections, 408 ("Your request timed out"), 502 ("we received an invalid response from"
# the model), 504 (the provider "did not respond within the allowed time"), other 5xx, an unreadable 200, and a
# 200 whose finish_reason is "error". These are never repeated automatically; the user decides whether to retry.
# OpenRouter documents no idempotency key for chat completions, so a repeated request cannot be deduplicated.
_MAY_HAVE_RUN = (
    "Nothing in the brief changed, but the provider may still have processed the request and charged for it."
)
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

# status: (kind, whether the request may have been processed, whether the user may retry, text).
_STATUS: dict[int, tuple[ModelErrorKind, bool, bool, str]] = {
    400: ("model-rejected", False, False, "The model gateway rejected the request"),
    401: (
        "model-credentials",
        False,
        False,
        "The model gateway rejected the credentials. Check ZIGZAG_OPENROUTER_API_KEY",
    ),
    402: ("model-insufficient-credits", False, False, "The model gateway account has insufficient credits"),
    403: ("model-credentials", False, False, "The model gateway refused this request for these credentials"),
    404: ("model-rejected", False, False, "No route serves this model with the required parameters"),
    408: ("model-timeout", True, True, "The model gateway timed out"),
    429: ("model-rate-limited", False, True, "The model gateway is rate limiting requests"),
    503: ("model-unavailable", False, True, "No model provider is available for this request"),
}


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after", "")
    return float(value) if value.replace(".", "", 1).isdigit() else None


class _AttemptFailedError(Exception):
    """One attempt failed: what the user is told, and what is known about the request."""

    def __init__(self, error: ModelCallError, attempt: CallAttempt) -> None:
        super().__init__(error.message)
        self.error = error
        self.attempt = attempt


def _failed(
    number: int,
    outcome: AttemptOutcome,
    kind: ModelErrorKind,
    message: str,
    *,
    http_status: int | None = None,
    failure: str | None = None,
    retryable: bool = True,
    retry_after: float | None = None,
) -> _AttemptFailedError:
    return _AttemptFailedError(
        ModelCallError(kind, message, retryable=retryable, retry_after=retry_after),
        CallAttempt(number, outcome, http_status=http_status, failure=failure),
    )


def _unusable(number: int, text: str, failure: str) -> _AttemptFailedError:
    """A 200 without a usable answer: the provider accepted the request and may have charged for it."""
    return _failed(
        number, "ambiguous", "model-unavailable", f"{text} {_MAY_HAVE_RUN}", http_status=200, failure=failure
    )


def _status_failure(response: httpx.Response, number: int) -> _AttemptFailedError:
    server_error = response.status_code >= 500
    kind, maybe_processed, retryable, text = _STATUS.get(
        response.status_code, ("model-unavailable", server_error, server_error, "The model gateway returned an error")
    )
    try:
        detail = _ErrorResponse.model_validate_json(response.content).error.message
    except ValidationError:
        detail = ""
    retry_after = _retry_after(response)
    suffix = f": {detail}" if detail else ""
    outcome = _MAY_HAVE_RUN if maybe_processed else "Nothing was changed."
    wait = f" Retry after {retry_after:g} seconds." if retry_after is not None else ""
    return _failed(
        number,
        "ambiguous" if maybe_processed else "not-processed",
        kind,
        f"{text} ({response.status_code}){suffix}. {outcome}{wait}",
        http_status=response.status_code,
        retryable=retryable,
        retry_after=retry_after,
    )


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        reasoning_effort: Literal["low", "medium", "high"] | None = None,
        attempt_timeout_seconds: float = 90.0,
        max_attempts: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "X-OpenRouter-Title": "zigzag"},
            timeout=httpx.Timeout(attempt_timeout_seconds, connect=10.0),
            transport=transport,
            trust_env=False,
        )

    @property
    def requested_model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._http.aclose()

    def body(self, request: CompletionRequest) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": request.schema_name, "strict": True, "schema": request.schema},
            },
            # Route only to endpoints that honour response_format; otherwise the schema is a hint.
            "provider": {"require_parameters": True},
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        if self._reasoning_effort is not None:
            body["reasoning"] = {"effort": self._reasoning_effort}
        return body

    async def complete(self, request: CompletionRequest, attempts: list[CallAttempt]) -> Completion:
        body = self.body(request)
        number = 0
        while True:
            number += 1
            try:
                completion = await self._attempt(body, number)
            except _AttemptFailedError as failed:
                attempts.append(failed.attempt)
                wait = self._retry_wait(failed, number)
                if wait is None:
                    raise failed.error from failed.__cause__
                await self._sleep(wait)
            except asyncio.CancelledError:
                # Cut off while the request was out (a deadline, a cancel, a shutdown): it may still be charged.
                attempts.append(CallAttempt(number, "ambiguous", failure="cancelled"))
                raise
            else:
                attempts.append(CallAttempt(number, "answered", http_status=200, cost=completion.usage.cost))
                return completion

    def _retry_wait(self, failed: _AttemptFailedError, number: int) -> float | None:
        """Seconds to wait before repeating a request no model processed; None when it must not be repeated."""
        if failed.attempt.outcome != "not-processed" or not failed.error.retryable or number >= self._max_attempts:
            return None
        retry_after = failed.error.retry_after
        if retry_after is not None:
            # Honour the provider's wait; when it is longer than this client holds a request, the user retries.
            return retry_after if retry_after <= _MAX_BACKOFF_SECONDS else None
        return min(0.5 * 2 ** (number - 1), _MAX_BACKOFF_SECONDS)

    async def _attempt(self, body: dict[str, object], number: int) -> Completion:
        try:
            response = await self._http.post("/chat/completions", json=body)
        except _NOT_SENT as e:
            raise _failed(
                number,
                "not-processed",
                "model-unavailable",
                "Could not reach the model gateway. Check the connection and retry. Nothing was changed.",
                failure=type(e).__name__,
            ) from e
        except httpx.TimeoutException as e:
            raise _failed(
                number,
                "ambiguous",
                "model-timeout",
                f"The model gateway did not answer in time. {_MAY_HAVE_RUN}",
                failure=type(e).__name__,
            ) from e
        except httpx.TransportError as e:
            raise _failed(
                number,
                "ambiguous",
                "model-unavailable",
                f"The connection to the model gateway failed before its answer arrived. {_MAY_HAVE_RUN}",
                failure=type(e).__name__,
            ) from e
        if response.status_code != 200:
            raise _status_failure(response, number)
        return self._read(response, number)

    def _read(self, response: httpx.Response, number: int) -> Completion:
        try:
            data = _ChatResponse.model_validate_json(response.content)
        except ValidationError as e:
            raise _unusable(
                number, "The model gateway returned a response this app could not read.", "unreadable"
            ) from e
        if not data.choices:
            raise _unusable(number, "The model gateway returned no answer.", "no choices")
        choice = data.choices[0]
        if choice.finish_reason == "error":
            raise _unusable(number, "The model failed while answering.", "finish_reason error")
        usage = data.usage or _Usage()
        return Completion(
            content=choice.message.content or "",
            served_model=data.model,
            provider=data.provider,
            finish_reason=choice.finish_reason,
            usage=Usage(prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens, cost=usage.cost),
        )
