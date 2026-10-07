"""Runs the real app (file stores on a temporary directory) in-process, with a scripted or fixture model, or
with the real OpenRouter client over a scripted transport."""

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from intent_harness.adapters.model.openrouter import OpenRouterClient
from intent_harness.application.assessment import LiveAssessor
from intent_harness.application.ports import Assessor, AssessRequest, CallAttempt, ModelCallError, ModelReply
from intent_harness.config import Config
from intent_harness.main import build
from tests.support import FIXTURES

type Step = str | Exception | Callable[[AssessRequest], Awaitable[str]]


@dataclass
class ScriptedAssessor:
    """A stand-in model returning scripted raw responses in order and recording each request."""

    script: list[Step]
    calls: list[AssessRequest] = field(default_factory=list[AssessRequest])

    @property
    def label(self) -> str:
        return "stub-model"

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply:
        """A scripted exception fails before anything is sent; a scripted answer is one answered attempt."""
        self.calls.append(request)
        if not self.script:
            raise AssertionError("Scripted assessor ran out of responses.")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        raw = step if isinstance(step, str) else await step(request)
        attempts.append(CallAttempt(1, "answered"))
        return ModelReply(raw=raw, interpreted_by="stub-model", requested_model="stub-model", prompt_version="test")


type Handler = (
    Callable[[httpx.Request], httpx.Response] | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
)


def completion(content: str, *, cost: float | None = None) -> httpx.Response:
    """A successful OpenRouter chat completion."""
    usage: dict[str, object] = {"prompt_tokens": 900, "completion_tokens": 120}
    if cost is not None:
        usage["cost"] = cost
    return httpx.Response(
        200,
        json={
            "model": "test/model-1",
            "provider": "TestCloud",
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": usage,
        },
    )


def scripted(steps: Sequence[httpx.Response | Exception]) -> Handler:
    """A transport handler that receives each request, then answers or raises with the next step."""
    queue = list(steps)

    def handle(_: httpx.Request) -> httpx.Response:
        step = queue.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    return handle


def gateway(handler: Handler, *, max_attempts: int = 2) -> LiveAssessor:
    """The live assessor and OpenRouter client, with the network replaced by `handler` and no real backoff."""

    async def no_wait(_: float) -> None:
        return None

    client = OpenRouterClient(
        api_key="sk-or-test",
        model="test/model",
        transport=httpx.MockTransport(handler),
        sleep=no_wait,
        max_attempts=max_attempts,
    )
    return LiveAssessor(client, max_output_tokens=4000)


class Ticker:
    """A deterministic clock: each reading is one second after the previous one."""

    def __init__(self) -> None:
        self._now = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)

    def __call__(self) -> str:
        self._now += timedelta(seconds=1)
        return self._now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Counter:
    def __init__(self, prefix: str = "id") -> None:
        self._n = 0
        self._prefix = prefix

    def __call__(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n}"


def config(data_dir: Path, **overrides: Any) -> Config:
    return Config(
        model_mode="fixture",
        data_dir=data_dir,
        fixtures_path=FIXTURES / "journeys.json",
        allowed_hosts=("testserver",),
        **overrides,
    )


@dataclass
class Api:
    client: httpx.AsyncClient
    app: FastAPI
    data_dir: Path

    async def get(self, path: str) -> httpx.Response:
        return await self.client.get(path)

    async def post(self, path: str, body: object = None) -> httpx.Response:
        return await self.client.post(path, json=body)

    async def events(self, operation_id: str) -> list[dict[str, Any]]:
        """Reads the SSE stream to its end (the operation's terminal state) and parses each event."""
        response = await self.client.get(f"/api/operations/{operation_id}/events")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        return [json.loads(line[len("data: ") :]) for line in response.text.splitlines() if line.startswith("data: ")]

    async def finish(self, started: httpx.Response) -> dict[str, Any]:
        assert started.status_code == 202, started.text
        operation = started.json()
        assert started.headers["location"] == f"/api/operations/{operation['id']}"
        return (await self.events(operation["id"]))[-1]

    async def create(self, brief: str) -> dict[str, Any]:
        done = await self.finish(await self.post("/api/projects", {"brief": brief}))
        assert done["status"] == "succeeded", done
        return (await self.get(f"/api/projects/{done['result']['projectId']}")).json()

    async def decide(self, project: dict[str, Any], **command: Any) -> httpx.Response:
        return await self.post(
            f"/api/projects/{project['id']}/decisions", {**command, "baseRevision": project["revision"]}
        )

    def project_file(self, project_id: str) -> bytes:
        return (self.data_dir / "projects" / f"{project_id}.json").read_bytes()


@asynccontextmanager
async def running(data_dir: Path, assessor: Assessor | None = None, **overrides: Any) -> AsyncGenerator[Api]:
    app = build(config(data_dir, **overrides), clock=Ticker(), new_id=Counter(), assessor=assessor)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield Api(client, app, data_dir)


def call_log(data_dir: Path) -> list[dict[str, Any]]:
    """The local model-call log, one entry per line."""
    return [json.loads(line) for line in (data_dir / "model-calls.jsonl").read_text().splitlines()]


def unavailable() -> ModelCallError:
    return ModelCallError("model-unavailable", "Could not reach the model gateway.", retryable=True)


async def wait_until(condition: Callable[[], bool], seconds: float = 2.0) -> None:
    """Polls state owned by another task, such as an operation moving to running."""
    async with asyncio.timeout(seconds):
        while not condition():  # noqa: ASYNC110 - there is no event to wait on from outside the runner
            await asyncio.sleep(0.005)
