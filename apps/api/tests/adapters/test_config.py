"""Configuration fails fast and reads only ZIGZAG_* settings."""

from pathlib import Path

import pytest

from tests.support import FIXTURES
from zigzag.config import ConfigError, load_config

FIXTURE_ENV = {"ZIGZAG_FIXTURES_PATH": str(FIXTURES / "journeys.json")}


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


@pytest.mark.parametrize("name", ["MODEL_MODE", "OPENAI_API_KEY", "ANTHROPIC_MODEL", "APP_MAX_ATTEMPTS"])
def test_a_variable_without_the_zigzag_prefix_never_stops_startup(name: str) -> None:
    assert load_config(FIXTURE_ENV | {name: "anything"}) == load_config(FIXTURE_ENV)


def test_live_mode_is_explicit_and_needs_its_credentials_and_model() -> None:
    text = problems({"ZIGZAG_MODEL_MODE": "live"})
    assert "needs ZIGZAG_OPENROUTER_API_KEY" in text
    assert "needs ZIGZAG_MODEL" in text
    live = load_config(
        {
            "ZIGZAG_MODEL_MODE": "live",
            "ZIGZAG_OPENROUTER_API_KEY": "sk-or-1",
            "ZIGZAG_MODEL": "anthropic/claude-opus-5.5",
            "ZIGZAG_REASONING_EFFORT": "high",
            "ZIGZAG_ALLOWED_HOSTS": "localhost, api",
        }
    )
    assert live.model == "anthropic/claude-opus-5.5"
    assert live.reasoning_effort == "high"
    assert live.allowed_hosts == ("localhost", "api")
    assert "sk-or-1" not in repr(live)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"ZIGZAG_MODEL_MODE": "fixtur"}, "ZIGZAG_MODEL_MODE"),
        ({"ZIGZAG_MODLE": "x"}, "ZIGZAG_MODLE is not a known setting."),
        ({"ZIGZAG_MAX_OUTPUT_TOKENS": "10"}, "ZIGZAG_MAX_OUTPUT_TOKENS"),
        ({"ZIGZAG_OPENROUTER_BASE_URL": "http://plain.example/v1"}, "ZIGZAG_OPENROUTER_BASE_URL"),
        (
            {"ZIGZAG_DEADLINE_SECONDS": "20", "ZIGZAG_ATTEMPT_TIMEOUT_SECONDS": "60"},
            "at least ZIGZAG_ATTEMPT_TIMEOUT_SECONDS",
        ),
        ({"ZIGZAG_FIXTURES_PATH": "/nonexistent/journeys.json"}, "does not exist"),
    ],
)
def test_invalid_or_incompatible_settings_stop_startup(env: dict[str, str], expected: str) -> None:
    assert expected in problems(FIXTURE_ENV | env)


def test_the_names_stage_lists_every_unknown_name_before_any_value_is_checked() -> None:
    text = problems(
        FIXTURE_ENV | {"ZIGZAG_MODLE": "secret-model", "ZIGZAG_MDOEL_MODE": "live", "ZIGZAG_MAX_OUTPUT_TOKENS": "10"}
    )
    assert "ZIGZAG_MODLE is not a known setting." in text
    assert "ZIGZAG_MDOEL_MODE is not a known setting." in text
    assert "ZIGZAG_MAX_OUTPUT_TOKENS" not in text
    assert "secret-model" not in text


def test_empty_values_mean_defaults() -> None:
    assert load_config(FIXTURE_ENV | {"ZIGZAG_REASONING_EFFORT": "", "ZIGZAG_MODEL": ""}).reasoning_effort is None
