"""The scope guard hook, run as Claude Code runs it: JSON on stdin, exit 2 to block."""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import HOOKS, SCRIPTS

HOOK = HOOKS / "scope_guard.py"


def old_system_python() -> str | None:
    """/usr/bin/python3 when it is older than 3.10, as on macOS; the hook must still work there."""
    python = Path("/usr/bin/python3")
    if not python.exists():
        return None
    check = "import sys; raise SystemExit(0 if sys.version_info < (3, 10) else 1)"
    return str(python) if subprocess.run([str(python), "-c", check], check=False).returncode == 0 else None


OLD_PYTHON = old_system_python()
API = ["--allow", "apps/api/", "--deny", "apps/api/openapi.json"]


class ScopeGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_hook(self, tool_input: object, args: list[str] = API) -> subprocess.CompletedProcess[str]:
        event = {"tool_name": "Write", "tool_input": tool_input, "cwd": str(self.root)}
        return subprocess.run(
            [sys.executable, str(HOOK), *args],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
        )

    def test_a_file_inside_the_agents_paths_is_allowed(self) -> None:
        run = self.run_hook({"file_path": str(self.root / "apps/api/src/intent_harness/domain/model.py")})
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_a_relative_path_inside_the_agents_paths_is_allowed(self) -> None:
        self.assertEqual(self.run_hook({"file_path": "apps/api/tests/test_x.py"}).returncode, 0)

    def test_another_apps_file_is_blocked(self) -> None:
        run = self.run_hook({"file_path": str(self.root / "apps/web/src/app/App.tsx")})
        self.assertEqual(run.returncode, 2)
        self.assertIn("outside this agent's paths", run.stderr)

    def test_a_denied_file_inside_the_paths_is_blocked(self) -> None:
        run = self.run_hook({"file_path": str(self.root / "apps/api/openapi.json")})
        self.assertEqual(run.returncode, 2)
        self.assertIn("owned by the coordinator", run.stderr)

    def test_a_prefix_lookalike_is_blocked(self) -> None:
        self.assertEqual(self.run_hook({"file_path": str(self.root / "apps/api-old/x.py")}).returncode, 2)

    def test_escaping_with_dot_dot_is_blocked(self) -> None:
        self.assertEqual(self.run_hook({"file_path": str(self.root / "apps/api/../../outside.py")}).returncode, 2)

    def test_a_symlink_out_of_the_paths_is_blocked(self) -> None:
        (self.root / "apps/api").mkdir(parents=True)
        (self.root / "apps/web").mkdir(parents=True)
        os.symlink(self.root / "apps/web", self.root / "apps/api/web-link")
        self.assertEqual(self.run_hook({"file_path": str(self.root / "apps/api/web-link/x.tsx")}).returncode, 2)

    def test_a_notebook_path_is_checked_too(self) -> None:
        self.assertEqual(self.run_hook({"notebook_path": str(self.root / "docs/x.ipynb")}).returncode, 2)

    def test_a_call_without_a_path_fails_closed(self) -> None:
        self.assertEqual(self.run_hook({"content": "x"}).returncode, 2)

    def test_input_that_is_not_json_fails_closed(self) -> None:
        run = subprocess.run(
            [sys.executable, str(HOOK), *API], input="nope", capture_output=True, text=True, check=False
        )
        self.assertEqual(run.returncode, 2)

    def test_an_unexpected_error_blocks(self) -> None:
        run = self.run_hook({"file_path": "apps/api/a\x00b"})
        self.assertEqual(run.returncode, 2, run.stderr)

    def test_the_agents_hook_commands_block_whenever_the_guard_cannot_run(self) -> None:
        """Claude Code blocks only on exit 2, so the configured command must turn every failure into 2."""
        agents = SCRIPTS.parent / ".claude" / "agents"
        commands = {
            path.name: re.search(r"command: '(.*)'$", path.read_text(encoding="utf-8"), re.M)
            for path in (agents / "python-api-engineer.md", agents / "react-ui-engineer.md")
        }
        for name, match in commands.items():
            assert match is not None, name
            for case, python in {"crashes": "exit 1", "is missing": None}.items():
                with self.subTest(agent=name, python=case), tempfile.TemporaryDirectory() as bin_dir:
                    if python:
                        fake = Path(bin_dir) / "python3"
                        fake.write_text(f"#!/bin/sh\n{python}\n")
                        fake.chmod(0o755)
                    run = subprocess.run(
                        ["/bin/sh", "-c", match.group(1)],
                        input=json.dumps({"tool_input": {"file_path": str(self.root / "docs/x.md")}}),
                        capture_output=True,
                        text=True,
                        check=False,
                        env={"PATH": f"{bin_dir}:/usr/bin/false-only", "CLAUDE_PROJECT_DIR": str(SCRIPTS.parent)},
                    )
                    self.assertEqual(run.returncode, 2, run.stderr)

    def test_the_agents_hook_commands_still_allow_in_scope_writes(self) -> None:
        agents = SCRIPTS.parent / ".claude" / "agents"
        for name, inside in (("python-api-engineer.md", "apps/api/x.py"), ("react-ui-engineer.md", "apps/web/x.tsx")):
            match = re.search(r"command: '(.*)'$", (agents / name).read_text(encoding="utf-8"), re.M)
            assert match is not None, name
            with self.subTest(name):
                run = subprocess.run(
                    ["/bin/sh", "-c", match.group(1)],
                    input=json.dumps({"tool_input": {"file_path": str(SCRIPTS.parent / inside)}}),
                    capture_output=True,
                    text=True,
                    check=False,
                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(SCRIPTS.parent)},
                )
                self.assertEqual(run.returncode, 0, run.stderr)

    @unittest.skipUnless(OLD_PYTHON, "no python3 older than 3.10 at /usr/bin/python3")
    def test_the_guard_works_under_an_old_system_python(self) -> None:
        assert OLD_PYTHON is not None
        for target, expected in (("docs/x.md", 2), ("apps/api/x.py", 0)):
            with self.subTest(target):
                run = subprocess.run(
                    [OLD_PYTHON, str(HOOK), *API],
                    input=json.dumps({"tool_input": {"file_path": target}}),
                    capture_output=True,
                    text=True,
                    check=False,
                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
                )
                self.assertEqual(run.returncode, expected, run.stderr)

    def test_the_guard_runs_on_the_oldest_supported_python_syntax(self) -> None:
        """The hook runs with whatever python3 is on PATH, which may not be the pinned 3.14."""
        source = HOOK.read_text(encoding="utf-8")
        ast.parse(source, filename=str(HOOK), feature_version=(3, 9))
        self.assertIn("from __future__ import annotations", source)

    def test_the_design_system_stays_unmodified_for_the_ui_agent(self) -> None:
        ui = ["--allow", "apps/web/", "--deny", "apps/web/src/design-system/ui/"]
        blocked = self.run_hook({"file_path": str(self.root / "apps/web/src/design-system/ui/button.tsx")}, ui)
        allowed = self.run_hook({"file_path": str(self.root / "apps/web/src/design-system/status-pill.tsx")}, ui)
        self.assertEqual((blocked.returncode, allowed.returncode), (2, 0))


if __name__ == "__main__":
    unittest.main()
