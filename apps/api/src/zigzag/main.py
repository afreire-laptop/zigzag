"""Composition root: reads configuration, builds the adapters, and returns the ASGI app.

Run one process with one worker: project locks and operation tracking live in this process."""

import logging
import os
import secrets
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

from fastapi import FastAPI

from zigzag.adapters.http.app import ApiContainer, build_api
from zigzag.adapters.http.schemas import FixtureTextsView, FixtureTextView, StatusView
from zigzag.adapters.model.fixture import FixtureAssessor, load_fixtures
from zigzag.adapters.model.openrouter import OpenRouterClient
from zigzag.adapters.persistence.files import FileOperationStore, FileProjectStore, JsonlCallLog
from zigzag.application.assessment import PROMPT_VERSION, LiveAssessor
from zigzag.application.operations import OperationRunner
from zigzag.application.ports import Assessor
from zigzag.application.projects import ProjectLocks, ProjectService
from zigzag.config import Config, ConfigError, load_config

log = logging.getLogger("zigzag")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def short_id() -> str:
    return secrets.token_hex(6)


def build(
    config: Config,
    *,
    clock: Callable[[], str] = utc_now,
    new_id: Callable[[], str] = short_id,
    assessor: Assessor | None = None,
) -> FastAPI:
    """Build the app. `assessor` replaces the configured one; tests use it to script model replies."""
    projects = FileProjectStore(config.data_dir)
    locks = ProjectLocks()
    closers: list[Callable[[], Awaitable[None]]] = []
    fixtures: FixtureTextsView | None = None
    if assessor is None and config.model_mode == "fixture":
        fixture = FixtureAssessor(load_fixtures(config.fixtures_path))
        fixtures = FixtureTextsView(
            briefs=tuple(FixtureTextView(label=t.label, text=t.text) for t in fixture.texts.briefs),
            replies=tuple(FixtureTextView(label=t.label, text=t.text) for t in fixture.texts.replies),
        )
        assessor = fixture
    elif assessor is None:
        assert config.openrouter_api_key is not None  # checked by Config
        assert config.model is not None
        client = OpenRouterClient(
            api_key=config.openrouter_api_key.get_secret_value(),
            model=config.model,
            base_url=config.openrouter_base_url,
            reasoning_effort=config.reasoning_effort,
            attempt_timeout_seconds=config.attempt_timeout_seconds,
            max_attempts=config.max_attempts,
        )
        closers.append(client.aclose)
        assessor = LiveAssessor(client, max_output_tokens=config.max_output_tokens)
    runner = OperationRunner(
        projects=projects,
        operations=FileOperationStore(config.data_dir),
        locks=locks,
        assessor=assessor,
        call_log=JsonlCallLog(config.data_dir),
        clock=clock,
        new_id=new_id,
        deadline_seconds=config.deadline_seconds,
        max_concurrent=config.max_concurrent_operations,
    )
    status = StatusView(
        mode=config.model_mode,
        model=assessor.label,
        reasoning_effort=config.reasoning_effort if config.model_mode == "live" else None,
        prompt_version=PROMPT_VERSION if config.model_mode == "live" else None,
        fixtures=fixtures,
        damaged_operations=(),
    )
    return build_api(
        ApiContainer(
            projects=ProjectService(projects, locks, clock),
            operations=runner,
            status=status,
            allowed_hosts=config.allowed_hosts,
            on_shutdown=tuple(closers),
        )
    )


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Entry point for `uvicorn --factory zigzag.main:create_app`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        config = load_config(os.environ if env is None else env)
    except ConfigError as error:
        log.error("%s", error)
        sys.exit(2)
    if config.model_mode == "fixture":
        log.info("FIXTURE MODE: canned journey responses from %s, not a live model.", config.fixtures_path)
    else:
        log.info(
            "Live model %s via OpenRouter (reasoning effort: %s).", config.model, config.reasoning_effort or "default"
        )
    return build(config)
