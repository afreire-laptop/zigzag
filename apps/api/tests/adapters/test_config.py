"""Configuration fails fast and reads only INTENT_* settings."""

from pathlib import Path

import pytest

from intent_harness.config import ConfigError, load_config
from tests.support import FIXTURES

FIXTURE_ENV = {"INTENT_FIXTURES_PATH": str(FIXTURES / "journeys.json")}


def problems(env: dict[str, str]) -> str:
    with pytest.raises(ConfigError) as error:
        load_config(env)
    return str(error.value)


def test_defaults_are_fixture_mode_without_secrets() -> None:
    config = load_config(FIXTURE_ENV)
    assert config.model_mode == "fixture"
    assert config.openrouter_api_key is None
    assert config.data_dir == Path("data")


def test_unrelated_shell_credentials_and_base_urls_are_ignored() -> None:
    config = load_config(
        FIXTURE_ENV
        | {
            "OPENROUTER_API_KEY": "sk-unrelated",
            "OPENAI_BASE_URL": "https://elsewhere.example",
            "ANTHROPIC_BASE_URL": "https://elsewhere.example",
            "ANTHROPIC_API_KEY": "sk-ant",
        }
    )
    assert config.openrouter_api_key is None
    assert config.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_live_mode_is_explicit_and_needs_its_credentials_and_model() -> None:
    text = problems({"INTENT_MODEL_MODE": "live"})
    assert "needs INTENT_OPENROUTER_API_KEY" in text
    assert "needs INTENT_MODEL" in text
    live = load_config(
        {
            "INTENT_MODEL_MODE": "live",
            "INTENT_OPENROUTER_API_KEY": "sk-or-1",
            "INTENT_MODEL": "anthropic/claude-opus-5.5",
            "INTENT_REASONING_EFFORT": "high",
            "INTENT_ALLOWED_HOSTS": "localhost, api",
        }
    )
    assert live.model == "anthropic/claude-opus-5.5"
    assert live.reasoning_effort == "high"
    assert live.allowed_hosts == ("localhost", "api")
    assert "sk-or-1" not in repr(live)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"INTENT_MODEL_MODE": "fixtur"}, "INTENT_MODEL_MODE"),
        ({"INTENT_MODLE": "x"}, "INTENT_MODLE is not a known setting."),
        ({"INTENT_EFFORT": "high"}, "use INTENT_REASONING_EFFORT"),
        ({"INTENT_MAX_TOKENS": "100"}, "use INTENT_MAX_OUTPUT_TOKENS"),
        ({"INTENT_MAX_OUTPUT_TOKENS": "10"}, "INTENT_MAX_OUTPUT_TOKENS"),
        ({"INTENT_OPENROUTER_BASE_URL": "http://plain.example/v1"}, "INTENT_OPENROUTER_BASE_URL"),
        (
            {"INTENT_DEADLINE_SECONDS": "20", "INTENT_ATTEMPT_TIMEOUT_SECONDS": "60"},
            "at least INTENT_ATTEMPT_TIMEOUT_SECONDS",
        ),
        ({"INTENT_FIXTURES_PATH": "/nonexistent/journeys.json"}, "does not exist"),
    ],
)
def test_invalid_or_incompatible_settings_stop_startup(env: dict[str, str], expected: str) -> None:
    assert expected in problems(FIXTURE_ENV | env)


def test_empty_values_mean_defaults() -> None:
    assert load_config(FIXTURE_ENV | {"INTENT_REASONING_EFFORT": "", "INTENT_MODEL": ""}).reasoning_effort is None
