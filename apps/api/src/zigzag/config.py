"""Runtime configuration, read once from an explicit mapping (the process environment in production).

Only `ZIGZAG_*` variables are read, so unrelated shell credentials or base URLs (`OPENAI_*`, `ANTHROPIC_*`,
`OPENROUTER_*`) can never redirect requests or be sent anywhere. Unknown `ZIGZAG_*` names, leftover `INTENT_*`
names, invalid values, and incompatible combinations stop startup with every problem listed."""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

PREFIX = "ZIGZAG_"
# The prefix before the project was renamed. A leftover name stops startup rather than being ignored, so an old
# .env cannot silently fall back to the defaults.
_OLD_PREFIX = "INTENT_"
_RETIRED = {
    "INTENT_EFFORT": "use ZIGZAG_REASONING_EFFORT (low, medium, high, or empty)",
    "INTENT_MAX_TOKENS": "use ZIGZAG_MAX_OUTPUT_TOKENS",
}


class ConfigError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("Invalid configuration:\n" + "\n".join(f"- {p}" for p in problems))
        self.problems = problems


class Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_mode: Literal["fixture", "live"] = "fixture"
    data_dir: Path = Path("data")
    fixtures_path: Path = Path("../../fixtures/journeys.json")
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: Annotated[str, Field(pattern=r"^https://[^\s/]+(/[^\s]*)?$")] = "https://openrouter.ai/api/v1"
    model: Annotated[str, Field(min_length=3, pattern=r"^[\w.:-]+/[\w.:-]+$")] | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    max_output_tokens: Annotated[int, Field(ge=512, le=64_000)] = 16_000
    attempt_timeout_seconds: Annotated[float, Field(ge=5, le=600)] = 90.0
    deadline_seconds: Annotated[float, Field(ge=10, le=1_800)] = 180.0
    # Attempts for failures known not to have reached the model. A request that may have been processed is never
    # repeated automatically, whatever this is (see the OpenRouter adapter).
    max_attempts: Annotated[int, Field(ge=1, le=4)] = 2
    max_concurrent_operations: Annotated[int, Field(ge=1, le=8)] = 2
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]", "api")

    @model_validator(mode="after")
    def _compatible(self) -> Self:
        problems: list[str] = []
        if self.model_mode == "live":
            if self.openrouter_api_key is None or not self.openrouter_api_key.get_secret_value().strip():
                problems.append("ZIGZAG_MODEL_MODE=live needs ZIGZAG_OPENROUTER_API_KEY.")
            if self.model is None:
                problems.append("ZIGZAG_MODEL_MODE=live needs ZIGZAG_MODEL, an explicit OpenRouter model slug.")
        elif not self.fixtures_path.is_file():
            problems.append(f"ZIGZAG_FIXTURES_PATH points to {self.fixtures_path}, which does not exist.")
        if self.deadline_seconds < self.attempt_timeout_seconds:
            problems.append("ZIGZAG_DEADLINE_SECONDS must be at least ZIGZAG_ATTEMPT_TIMEOUT_SECONDS.")
        if problems:
            raise ValueError(" ".join(problems))
        return self


def load_config(env: Mapping[str, str]) -> Config:
    problems: list[str] = []
    values: dict[str, object] = {}
    fields = Config.model_fields
    for name, raw in env.items():
        if name.startswith(_OLD_PREFIX):
            problems.append(_old_name(name))
            continue
        if not name.startswith(PREFIX):
            continue
        key = name.removeprefix(PREFIX).lower()
        if key not in fields:
            problems.append(f"{name} is not a known setting.")
        elif raw.strip() == "":
            continue  # empty means "use the default", as in .env.example
        elif key == "allowed_hosts":
            values[key] = tuple(h.strip() for h in raw.split(",") if h.strip())
        else:
            values[key] = raw.strip()
    if problems:
        raise ConfigError(problems)
    try:
        return Config.model_validate(values)
    except ValidationError as error:
        raise ConfigError([_describe(e["loc"], e["msg"]) for e in error.errors()]) from error


def _old_name(name: str) -> str:
    if name in _RETIRED:
        return f"{name} is no longer read; {_RETIRED[name]}."
    key = name.removeprefix(_OLD_PREFIX)
    if key.lower() in Config.model_fields:
        return f"{name} was renamed; use {PREFIX}{key}."
    return f"{name} is not read; settings use the {PREFIX} prefix."


def _describe(loc: tuple[int | str, ...], message: str) -> str:
    name = ".".join(str(part) for part in loc).upper() or "SETTINGS"
    return f"{PREFIX}{name}: {message.removeprefix('Value error, ')}"
