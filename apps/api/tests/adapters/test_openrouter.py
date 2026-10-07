"""The OpenRouter adapter against a stubbed transport: request shape, response reading, error mapping,
bounded retries, and the record of every attempt. No network."""

import asyncio
import json
from collections.abc import Callable, Sequence
from typing import Literal

import httpx
import pytest

from intent_harness.adapters.model.openrouter import DEFAULT_BASE_URL, OpenRouterClient
from intent_harness.application.assessment import PROMPT_VERSION, Json, LiveAssessor, provider_schema
from intent_harness.application.ports import AssessRequest, CallAttempt, CompletionRequest, ModelCallError
from tests.support import CLEAR, text

pytestmark = pytest.mark.anyio
REQUEST = CompletionRequest(
    system="sys", user="usr", schema_name="intent_proposal", schema={"type": "object"}, max_output_tokens=4000
)
MAY_HAVE_RUN = "may still have processed the request and charged for it"


def ok(content: str = '{"a": 1}', *, finish: str = "stop", cost: float | None = 0.0123) -> httpx.Response:
    usage: dict[str, object] = {"prompt_tokens": 900, "completion_tokens": 120}
    if cost is not None:
        usage["cost"] = cost
    return httpx.Response(
        200,
        json={
            "id": "gen-1",
            "model": "anthropic/claude-opus-5.5",
            "provider": "Anthropic",
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": usage,
        },
    )


def client(
    responses: Sequence[httpx.Response | Exception],
    seen: list[httpx.Request],
    *,
    reasoning_effort: Literal["low", "medium", "high"] | None = None,
    base_url: str = DEFAULT_BASE_URL,
    max_attempts: int = 2,
    sleeps: list[float] | None = None,
) -> OpenRouterClient:
    """The transport records each request it receives, then raises or answers with the next scripted step."""
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        nxt = queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    waited = [] if sleeps is None else sleeps

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    return OpenRouterClient(
        api_key="sk-or-test",
        model="anthropic/claude-opus-5.5",
        transport=httpx.MockTransport(handle),
        sleep=sleep,
        reasoning_effort=reasoning_effort,
        base_url=base_url,
        max_attempts=max_attempts,
    )


def answered(number: int, cost: float | None = 0.0123) -> CallAttempt:
    return CallAttempt(number, "answered", http_status=200, cost=cost)


async def test_request_shape_and_successful_reading() -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    c = client([ok()], seen, reasoning_effort="high")
    completion = await c.complete(REQUEST, attempts)
    request = seen[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-or-test"
    assert request.headers["x-openrouter-title"] == "Intent Harness"
    body = json.loads(request.content)
    assert body == {
        "model": "anthropic/claude-opus-5.5",
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "intent_proposal", "strict": True, "schema": {"type": "object"}},
        },
        "provider": {"require_parameters": True},
        "max_tokens": 4000,
        "stream": False,
        "reasoning": {"effort": "high"},
    }
    assert completion.content == '{"a": 1}'
    assert (completion.served_model, completion.provider) == ("anthropic/claude-opus-5.5", "Anthropic")
    assert attempts == [answered(1)]
    assert attempts[0].cost_status == "reported"
    assert (completion.usage.prompt_tokens, completion.usage.completion_tokens, completion.usage.cost) == (
        900,
        120,
        0.0123,
    )
    await c.aclose()


async def test_effort_is_omitted_and_missing_cost_stays_unknown() -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    c = client([ok(cost=None)], seen, base_url="https://gateway.example/api/v1/")
    completion = await c.complete(REQUEST, attempts)
    assert "reasoning" not in json.loads(seen[0].content)
    assert str(seen[0].url) == "https://gateway.example/api/v1/chat/completions"
    assert completion.usage.cost is None
    assert attempts == [answered(1, cost=None)]
    assert attempts[0].cost_status == "unknown"


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (400, "model-rejected", False),
        (401, "model-credentials", False),
        (402, "model-insufficient-credits", False),
        (403, "model-credentials", False),
        (404, "model-rejected", False),
    ],
)
async def test_non_retryable_statuses_fail_at_once(status: int, kind: str, retryable: bool) -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    c = client([httpx.Response(status, json={"error": {"code": status, "message": "upstream said no"}})], seen)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, attempts)
    assert (error.value.kind, error.value.retryable) == (kind, retryable)
    assert "upstream said no" in error.value.message
    assert len(seen) == 1
    assert attempts == [CallAttempt(1, "not-processed", http_status=status)]
    assert attempts[0].cost_status == "not-charged"


async def test_rejections_before_processing_are_retried_within_the_attempt_budget() -> None:
    seen: list[httpx.Request] = []
    sleeps: list[float] = []
    attempts: list[CallAttempt] = []
    c = client([httpx.Response(429, headers={"retry-after": "2"}, text="slow down"), ok()], seen, sleeps=sleeps)
    await c.complete(REQUEST, attempts)
    assert attempts == [CallAttempt(1, "not-processed", http_status=429), answered(2)]
    assert len(seen) == 2
    assert sleeps == [2.0]  # the provider's Retry-After, honoured

    seen.clear()
    attempts.clear()
    c = client([httpx.Response(503), httpx.Response(502)], seen)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, attempts)
    assert (error.value.kind, error.value.retryable) == ("model-unavailable", True)
    assert MAY_HAVE_RUN in error.value.message  # the 502 came from a provider that received the request
    assert attempts == [
        CallAttempt(1, "not-processed", http_status=503),
        CallAttempt(2, "ambiguous", http_status=502),
    ]

    seen.clear()
    attempts.clear()
    c = client([httpx.Response(503), httpx.Response(503)], seen)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, attempts)
    assert [a.outcome for a in attempts] == ["not-processed", "not-processed"]  # the budget is spent
    assert "Nothing was changed." in error.value.message

    seen.clear()
    c = client([httpx.ReadTimeout("slow")], seen, max_attempts=1)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, [])
    assert error.value.kind == "model-timeout"

    seen.clear()
    c = client([httpx.Response(408)], seen, max_attempts=1)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, [])
    assert (error.value.kind, error.value.retryable) == ("model-timeout", True)


async def test_a_read_timeout_after_the_request_arrived_is_not_retried() -> None:
    seen: list[httpx.Request] = []
    sleeps: list[float] = []
    attempts: list[CallAttempt] = []
    c = client([httpx.ReadTimeout("no answer yet"), ok()], seen, sleeps=sleeps)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, attempts)
    assert len(seen) == 1
    assert (error.value.kind, error.value.retryable) == ("model-timeout", True)  # the user may retry explicitly
    assert MAY_HAVE_RUN in error.value.message
    assert sleeps == []
    assert attempts == [CallAttempt(1, "ambiguous", failure="ReadTimeout")]
    assert (attempts[0].cost, attempts[0].cost_status) == (None, "unknown-may-have-been-charged")


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ConnectTimeout("no connection"), httpx.PoolTimeout("no free connection")],
)
async def test_a_request_that_was_never_sent_is_retried(failure: Exception) -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    completion = await client([failure, ok()], seen).complete(REQUEST, attempts)
    assert len(seen) == 2
    assert completion.content == '{"a": 1}'
    assert attempts == [CallAttempt(1, "not-processed", failure=type(failure).__name__), answered(2)]


@pytest.mark.parametrize(
    "failure",
    [httpx.ReadError("reset"), httpx.RemoteProtocolError("closed mid-answer"), httpx.WriteError("broken pipe")],
)
async def test_a_connection_lost_after_sending_is_not_retried(failure: Exception) -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    with pytest.raises(ModelCallError) as error:
        await client([failure, ok()], seen).complete(REQUEST, attempts)
    assert len(seen) == 1
    assert (error.value.kind, error.value.retryable) == ("model-unavailable", True)
    assert MAY_HAVE_RUN in error.value.message
    assert attempts == [CallAttempt(1, "ambiguous", failure=type(failure).__name__)]


@pytest.mark.parametrize(
    ("status", "kind"),
    [(408, "model-timeout"), (500, "model-unavailable"), (502, "model-unavailable"), (504, "model-unavailable")],
)
async def test_failures_after_a_provider_may_have_started_are_not_retried(status: int, kind: str) -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    with pytest.raises(ModelCallError) as error:
        await client([httpx.Response(status), ok()], seen).complete(REQUEST, attempts)
    assert len(seen) == 1
    assert (error.value.kind, error.value.retryable) == (kind, True)
    assert MAY_HAVE_RUN in error.value.message
    assert attempts == [CallAttempt(1, "ambiguous", http_status=status)]


async def test_503_is_retried_and_a_long_retry_after_is_left_to_the_user() -> None:
    seen: list[httpx.Request] = []
    sleeps: list[float] = []
    attempts: list[CallAttempt] = []
    await client([httpx.Response(503), ok()], seen, sleeps=sleeps).complete(REQUEST, attempts)
    assert (len(seen), len(attempts), sleeps) == (2, 2, [0.5])

    seen.clear()
    sleeps.clear()
    attempts.clear()
    c = client([httpx.Response(429, headers={"retry-after": "60"}), ok()], seen, sleeps=sleeps)
    with pytest.raises(ModelCallError) as error:
        await c.complete(REQUEST, attempts)
    assert len(seen) == 1  # not retried early, and not held for a minute either
    assert sleeps == []
    assert (error.value.kind, error.value.retryable, error.value.retry_after) == ("model-rate-limited", True, 60.0)
    assert "Nothing was changed." in error.value.message
    assert "60 seconds" in error.value.message
    assert attempts == [CallAttempt(1, "not-processed", http_status=429)]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>gateway page</html>"),
        httpx.Response(200, json={"model": "m", "choices": []}),
        # OpenRouter's documented shape when the provider fails after the 200 status was sent.
        httpx.Response(200, json={"id": "gen-1", "error": {"code": 502, "message": "Provider disconnected"}}),
        ok(finish="error"),
    ],
)
async def test_unreadable_or_failed_answers_are_unavailable_and_not_retried(response: httpx.Response) -> None:
    seen: list[httpx.Request] = []
    attempts: list[CallAttempt] = []
    with pytest.raises(ModelCallError) as error:
        await client([response, ok()], seen).complete(REQUEST, attempts)
    assert len(seen) == 1
    assert (error.value.kind, error.value.retryable) == ("model-unavailable", True)
    assert MAY_HAVE_RUN in error.value.message
    assert [(a.number, a.outcome, a.http_status, a.cost) for a in attempts] == [(1, "ambiguous", 200, None)]


async def test_a_request_cancelled_in_flight_is_recorded_as_ambiguous() -> None:
    received = asyncio.Event()

    async def hang(_: httpx.Request) -> httpx.Response:
        received.set()
        await asyncio.sleep(10)
        return ok()

    c = OpenRouterClient(api_key="k", model="a/b", transport=httpx.MockTransport(hang))
    attempts: list[CallAttempt] = []
    task = asyncio.create_task(c.complete(REQUEST, attempts))
    await received.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert attempts == [CallAttempt(1, "ambiguous", failure="cancelled")]


def live(responses: list[httpx.Response]) -> LiveAssessor:
    return LiveAssessor(client(responses, []), max_output_tokens=8000)


async def test_live_assessor_records_provenance_and_maps_finish_reasons() -> None:
    attempts: list[CallAttempt] = []
    reply = await live([ok('{"x": 1}')]).assess(AssessRequest(mode="brief", project=None, text=text(CLEAR)), attempts)
    assert reply.raw == '{"x": 1}'
    assert (reply.interpreted_by, reply.requested_model, reply.prompt_version) == (
        "anthropic/claude-opus-5.5",
        "anthropic/claude-opus-5.5",
        PROMPT_VERSION,
    )
    assert attempts == [answered(1)]
    for finish, kind in [("length", "model-incomplete"), ("content_filter", "model-declined")]:
        attempts = []
        with pytest.raises(ModelCallError) as error:
            await live([ok(finish=finish)]).assess(AssessRequest(mode="brief", project=None, text="x"), attempts)
        assert error.value.kind == kind
        assert attempts == [answered(1)]  # the model ran and its reported cost is kept


def walk(node: Json, visit: Callable[[dict[str, Json]], None]) -> None:
    if isinstance(node, list):
        for x in node:
            walk(x, visit)
    elif isinstance(node, dict):
        visit(node)
        for v in node.values():
            walk(v, visit)


def test_provider_schema_is_strict_and_self_contained() -> None:
    schema = provider_schema()
    text_form = json.dumps(schema)
    assert "$ref" not in text_form
    assert "$defs" not in text_form
    for keyword in ("minLength", "maxLength", "maxItems", "minItems", '"title"'):
        assert keyword not in text_form

    def check(node: dict[str, Json]) -> None:
        if node.get("type") == "object":
            properties = node["properties"]
            assert isinstance(properties, dict)
            assert node["required"] == list(properties)
            assert node["additionalProperties"] is False

    walk(schema, check)
    assert schema["required"] == ["extracted", "resolutions", "newItems", "focus"]
