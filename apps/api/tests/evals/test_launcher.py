"""`pnpm eval` reads the repository's .env when there is one, as `pnpm dev` does, and variables already set in the
shell take precedence, so one command can evaluate another model without editing .env."""

import os
import shutil
import subprocess
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "eval.sh"
RUNNER = ("python", "-m", "evals.run")
ARGS = ("--budget-usd", "1", "--cases", "clear-brief")


def launch(root: Path, *args: str) -> list[str]:
    """Runs a copy of the launcher in the repository's layout under `root`, with a `uv` that records its arguments."""
    scripts = root / "apps" / "api" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(LAUNCHER, scripts)
    tools = root / "bin"
    tools.mkdir()
    (tools / "uv").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$UV_ARGS"\n')
    (tools / "uv").chmod(0o755)
    recorded = root / "uv-args"
    env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "UV_ARGS": str(recorded)}
    subprocess.run(["sh", str(scripts / "eval.sh"), *args], env=env, check=True, timeout=30)
    return recorded.read_text().splitlines()


def test_the_launcher_reads_the_repository_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ZIGZAG_MODEL_MODE=live\n")
    assert launch(tmp_path, *ARGS) == ["run", "--frozen", "--env-file", "../../.env", *RUNNER, *ARGS]


def test_without_an_env_file_the_launcher_uses_the_shell_environment(tmp_path: Path) -> None:
    assert launch(tmp_path, *ARGS) == ["run", "--frozen", *RUNNER, *ARGS]


def test_a_variable_set_in_the_shell_overrides_the_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ZIGZAG_MODEL=from/env-file\nZIGZAG_REASONING_EFFORT=medium\n")
    uv = shutil.which("uv")
    assert uv is not None, "uv runs the evaluation, so it must be on PATH"
    for name, expected in (("ZIGZAG_MODEL", "from/shell"), ("ZIGZAG_REASONING_EFFORT", "medium")):
        shown = subprocess.run(
            [uv, "run", "--no-project", "--env-file", str(tmp_path / ".env"), "printenv", name],
            env={**os.environ, "ZIGZAG_MODEL": "from/shell"},
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        assert shown.stdout.strip() == expected
