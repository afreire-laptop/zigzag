"""HTTP boundary. Handlers parse, delegate to an application service, and return its read model.
Model work is asynchronous: starting it returns 202 and an operation; progress arrives over SSE."""

from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from zigzag.adapters.http.schemas import (
    AssessmentRequest,
    CreateProjectRequest,
    CurrentProjectView,
    DecisionCommand,
    DeferCommand,
    EditCommand,
    Health,
    Problem,
    RecoveryView,
    RelyCommand,
    RemoveCommand,
    ReplyRequest,
    ReviewRequest,
    SelectCommand,
    StatusView,
)
from zigzag.application.errors import ApplicationError, ErrorKind
from zigzag.application.operations import Operation, OperationRunner
from zigzag.application.projects import Command, Defer, Edit, ProjectService, Rely, Remove, Select
from zigzag.domain.view import HandoffView, ProjectView

_STATUS: dict[ErrorKind, int] = {
    "not-found": 404,
    "invalid-request": 400,
    "conflict": 409,
    "busy": 409,
    "corrupt-record": 500,
    "internal": 500,
}
_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": Problem, "content": {"application/problem+json": {}}} for code in (400, 404, 409, 422, 500)
}


@dataclass(frozen=True)
class ApiContainer:
    projects: ProjectService
    operations: OperationRunner
    status: StatusView
    allowed_hosts: tuple[str, ...]
    on_shutdown: tuple[Callable[[], Awaitable[None]], ...] = field(default=())


def _problem(status: int, kind: str, detail: str, **extra: object) -> JSONResponse:
    title = {400: "Bad Request", 404: "Not Found", 409: "Conflict", 422: "Unprocessable Content"}.get(
        status, "Internal Server Error"
    )
    problem = Problem.model_validate(
        {"type": f"/problems/{kind}", "title": title, "status": status, "detail": detail, "kind": kind, **extra}
    )
    return JSONResponse(problem.model_dump(mode="json"), status_code=status, media_type="application/problem+json")


def _command(body: DecisionCommand) -> Command:
    match body:
        case SelectCommand():
            return Select(body.question_id, body.option_id, body.reason)
        case DeferCommand():
            return Defer(body.question_id, body.reason)
        case EditCommand():
            return Edit(body.item_id, body.text)
        case RemoveCommand():
            return Remove(body.item_id)
        case RelyCommand():
            return Rely(body.item_id)


def _accepted(response: Response, operation: Operation) -> Operation:
    response.headers["Location"] = f"/api/operations/{operation.id}"
    return operation


def build_api(c: ApiContainer) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        c.operations.recover()
        yield
        await c.operations.shutdown()
        for close in c.on_shutdown:
            await close()

    app = FastAPI(
        title="zigzag API",
        version="0.2.0",
        lifespan=lifespan,
        generate_unique_id_function=lambda route: route.name,
        responses=_ERRORS,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(c.allowed_hosts))

    @app.exception_handler(ApplicationError)
    async def application_error(_: Request, error: ApplicationError) -> JSONResponse:
        return _problem(
            _STATUS.get(error.kind, 500),
            error.kind,
            error.message,
            retryable=error.retryable,
            issues=list(error.issues),
            activeOperationId=error.active_operation_id,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        issues = [f"{'.'.join(str(p) for p in e['loc'][1:]) or 'body'}: {e['msg']}" for e in error.errors()]
        return _problem(422, "invalid-request", "The request was not valid.", retryable=False, issues=issues[:10])

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        return _problem(
            error.status_code,
            "not-found" if error.status_code == 404 else "request",
            str(error.detail),
            retryable=False,
        )

    app.include_router(_system_routes(c))
    app.include_router(_project_routes(c))
    app.include_router(_operation_routes(c))
    return app


def _system_routes(c: ApiContainer) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health")
    async def get_health() -> Health:
        return Health(status="ok")

    @router.get("/status")
    async def get_status() -> StatusView:
        return c.status.model_copy(update={"damaged_operations": tuple(c.operations.damaged())})

    return router


def _project_routes(c: ApiContainer) -> APIRouter:
    router = APIRouter(prefix="/api/projects", tags=["projects"])

    @router.get("/current")
    async def get_current_project() -> CurrentProjectView:
        current = c.projects.current()
        recovery = (
            RecoveryView(
                project_id=current.recovery.project_id,
                file=current.recovery.file,
                reason=current.recovery.reason,
                modified_at=current.recovery.modified_at,
            )
            if current.recovery
            else None
        )
        return CurrentProjectView(state=current.state, project=current.project, recovery=recovery)

    @router.post("", status_code=202)
    async def create_project(body: CreateProjectRequest, response: Response) -> Operation:
        return _accepted(response, await c.operations.start_create(body.brief))

    @router.get("/{project_id}")
    async def get_project(project_id: str) -> ProjectView:
        return c.projects.view(project_id)

    @router.post("/{project_id}/replies", status_code=202)
    async def create_reply(project_id: str, body: ReplyRequest, response: Response) -> Operation:
        operation = await c.operations.start_reply(project_id, body.base_revision, body.text, body.question_id)
        return _accepted(response, operation)

    @router.post("/{project_id}/assessments", status_code=202)
    async def create_assessment(project_id: str, body: AssessmentRequest, response: Response) -> Operation:
        return _accepted(response, await c.operations.start_reassess(project_id, body.base_revision))

    @router.post("/{project_id}/decisions")
    async def create_decision(project_id: str, body: DecisionCommand) -> ProjectView:
        return await c.projects.decide(project_id, body.base_revision, _command(body))

    @router.post("/{project_id}/reviews")
    async def create_review(project_id: str, body: ReviewRequest) -> ProjectView:
        return await c.projects.review(project_id, body.revision)

    @router.get("/{project_id}/handoff")
    async def get_handoff(project_id: str) -> HandoffView:
        return c.projects.handoff(project_id)

    @router.get(
        "/{project_id}/exports/{export_format}",
        response_class=Response,
        responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}, "application/json": {}}}},
    )
    async def get_export(
        project_id: str, export_format: Literal["markdown", "json"], revision: int | None = None
    ) -> Response:
        file = c.projects.export(project_id, export_format, revision)
        return Response(
            file.body,
            media_type=file.media_type,
            headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
        )

    return router


def _operation_routes(c: ApiContainer) -> APIRouter:
    router = APIRouter(prefix="/api/operations", tags=["operations"])

    def existing(operation_id: str) -> Operation:
        return c.operations.get(operation_id)

    @router.get("")
    async def list_active_operations() -> list[Operation]:
        return c.operations.active()

    @router.get("/{operation_id}")
    async def get_operation(operation: Annotated[Operation, Depends(existing)]) -> Operation:
        return operation

    @router.post("/{operation_id}/cancel")
    async def cancel_operation(operation: Annotated[Operation, Depends(existing)]) -> Operation:
        return await c.operations.cancel(operation.id)

    @router.get("/{operation_id}/events", response_class=EventSourceResponse)
    async def watch_operation(operation: Annotated[Operation, Depends(existing)]) -> AsyncIterable[Operation]:
        """Each persisted state of the operation, starting with the current one, until it finishes.
        Notifications only: the REST resource stays authoritative, and reconnecting never repeats work."""
        async for state in c.operations.watch(operation.id):
            yield state

    return router
