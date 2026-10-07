"""Locating Codex, reporting what ran, and reporting a blocked review when Codex is absent."""

import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import codex_review

from tests.support import Repo


class CodexReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def install_plugin(self) -> Path:
        script = self.home / "plugins" / "codex" / "1.0.0" / "scripts" / "codex-companion.mjs"
        script.parent.mkdir(parents=True)
        script.write_text("// companion\n")
        registry = self.home / ".claude" / "plugins" / "installed_plugins.json"
        registry.parent.mkdir(parents=True)
        install = str(script.parent.parent)
        registry.write_text(json.dumps({"plugins": {codex_review.PLUGIN: [{"installPath": install}]}}))
        return script

    def test_the_companion_is_found_through_the_plugin_registry(self) -> None:
        script = self.install_plugin()
        self.assertEqual(codex_review.companion_script(self.home), script)

    def test_no_registry_means_no_companion(self) -> None:
        self.assertIsNone(codex_review.companion_script(self.home))

    def test_the_requested_model_comes_from_the_codex_client_log(self) -> None:
        database = self.home / ".codex" / "logs_2.sqlite"
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as connection:
            connection.execute("create table logs (thread_id text, feedback_log_body text)")
            connection.executemany(
                "insert into logs values (?, ?)",
                [("t1", "turn{model=gpt-test reasoning_effort=low}"), ("t1", "model=gpt-test"), ("t2", "model=x")],
            )
        connection.close()
        self.assertEqual(codex_review.logged_model(self.home, "t1"), "gpt-test, reasoning effort low")
        self.assertIsNone(codex_review.logged_model(self.home, "missing"))

    def run_plugin(self, stdout: str, stderr: str) -> tuple[int, str, str]:
        """Runs the script with a fake `node` standing in for the plugin's companion."""
        self.install_plugin()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        (self.home / "stdout.txt").write_text(stdout)
        (self.home / "stderr.txt").write_text(stderr)
        node = bin_dir / "node"
        node.write_text(f"#!/bin/sh\ncat '{self.home}/stdout.txt'\ncat '{self.home}/stderr.txt' >&2\n")
        node.chmod(0o755)
        focus = self.home / "focus.md"
        focus.write_text("focus")
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = codex_review.main(
                ["--base", "HEAD", "--focus-file", str(focus), "--out", str(self.home / "out.md")], home=self.home
            )
        return code, out.getvalue(), err.getvalue()

    def test_the_report_directory_is_created_before_the_review_runs(self) -> None:
        self.install_plugin()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        node = bin_dir / "node"
        node.write_text("#!/bin/sh\necho '# Codex Adversarial Review'\necho 'Verdict: approve'\n")
        node.chmod(0o755)
        focus = self.home / "focus.md"
        focus.write_text("focus")
        out = self.home / "new" / "dir" / "codex.md"
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}), redirect_stdout(io.StringIO()):
            code = codex_review.main(["--base", "HEAD", "--focus-file", str(focus), "--out", str(out)], home=self.home)
        self.assertEqual(code, 0)
        self.assertIn("Verdict: approve", out.read_text())

    def test_a_completed_plugin_review_prints_an_evidence_block(self) -> None:
        thread = "00000000-0000-7000-8000-00000000c0de"
        code, out, _ = self.run_plugin(
            "# Codex Adversarial Review\n\nVerdict: approve\n", f"[codex] Thread ready ({thread}).\n"
        )
        self.assertEqual(code, 0)
        self.assertIn("reviewer: codex-adversarial", out)
        self.assertIn(f"invocation: thread {thread}", out)
        self.assertRegex(out, r"reviewed_commit: [0-9a-f]{40}")
        self.assertRegex(out, r"baseline: [0-9a-f]{40}")
        self.assertIn("status: complete", out)

    def test_a_report_from_a_failed_run_is_not_left_behind(self) -> None:
        self.install_plugin()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        node = bin_dir / "node"
        node.write_text("#!/bin/sh\necho '# Codex Adversarial Review'\necho 'Verdict: approve'\nexit 1\n")
        node.chmod(0o755)
        focus = self.home / "focus.md"
        focus.write_text("focus")
        out = self.home / "out.md"
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}),
            redirect_stdout(stdout),
            redirect_stderr(io.StringIO()),
        ):
            code = codex_review.main(["--base", "HEAD", "--focus-file", str(focus), "--out", str(out)], home=self.home)
        self.assertEqual(code, 4)
        self.assertIn("status: incomplete", stdout.getvalue())
        self.assertFalse(out.exists(), "an incomplete run must leave no report file")

    def test_a_run_that_ends_without_a_report_is_incomplete(self) -> None:
        code, out, err = self.run_plugin("", "[codex] Thread ready (00000000-0000-7000-8000-00000000c0de).\n")
        self.assertEqual(code, 4)
        self.assertIn("produced no review", err)
        self.assertIn("status: incomplete", out)

    def test_the_plugin_runs_in_its_own_checkout_without_review_records(self) -> None:
        self.install_plugin()
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        node = bin_dir / "node"
        node.write_text(
            "#!/bin/sh\necho '# Codex Adversarial Review'\necho 'Verdict: approve'\n"
            'echo "at $(pwd) reviews=$(test -e docs/records && echo present || echo absent)"\n'
        )
        node.chmod(0o755)
        focus = self.home / "focus.md"
        focus.write_text("focus")
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}), redirect_stdout(io.StringIO()):
            code = codex_review.main(
                ["--base", "HEAD", "--focus-file", str(focus), "--out", str(self.home / "out.md")], home=self.home
            )
        self.assertEqual(code, 0)
        place = (self.home / "out.md").read_text().splitlines()[-1]
        root = Path(codex_review.__file__).resolve().parent.parent
        self.assertIn("reviews=absent", place)
        self.assertNotIn(f"at {root} ", place + " ")

    def run_cli_fallback(self, writes: str | None, stale: bool) -> tuple[int, str]:
        """No plugin; a fake `codex exec` that writes `writes` to its -o file, or nothing."""
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        codex = bin_dir / "codex"
        body = (
            ""
            if writes is None
            else f'while [ $# -gt 0 ]; do [ "$1" = -o ] && printf %s "{writes}" > "$2"; shift; done\n'
        )
        version = '[ "$1" = --version ] && echo "codex-cli test" && exit 0\n'
        codex.write_text("#!/bin/sh\n" + version + body + "cat > /dev/null\nexit 0\n")
        codex.chmod(0o755)
        focus = self.home / "focus.md"
        focus.write_text("focus")
        out = self.home / "out.md"
        if stale:
            out.write_text("# Codex Adversarial Review\nVerdict: approve\n(an earlier run)\n")
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:/usr/bin:/bin"}),
            redirect_stdout(stdout),
            redirect_stderr(io.StringIO()),
        ):
            code = codex_review.main(["--base", "HEAD", "--focus-file", str(focus), "--out", str(out)], home=self.home)
        return code, stdout.getvalue()

    def test_the_cli_fallback_never_reports_a_stale_or_unfinished_output(self) -> None:
        for writes, stale in ((None, True), ("still thinking", False)):
            with self.subTest(writes=writes, stale=stale):
                code, out = self.run_cli_fallback(writes, stale)
                self.assertEqual(code, 4)
                self.assertIn("status: incomplete", out)
            shutil.rmtree(self.home / "bin")

    def test_the_cli_fallback_reports_a_review_with_a_verdict(self) -> None:
        code, out = self.run_cli_fallback("Findings: none. Verdict: approve", stale=False)
        self.assertEqual(code, 0)
        self.assertIn("tool: codex exec --sandbox read-only", out)

    def test_a_checkout_that_cannot_be_made_is_an_incomplete_review(self) -> None:
        self.install_plugin()
        focus = self.home / "focus.md"
        focus.write_text("focus")
        log = self.home / "out.log"
        log.write_text("an earlier run's progress")
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(codex_review, "isolated_checkout", side_effect=subprocess.CalledProcessError(128, "git")),
            mock.patch.object(codex_review.shutil, "which", return_value="/usr/bin/node"),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = codex_review.main(
                ["--base", "HEAD", "--focus-file", str(focus), "--out", str(self.home / "out.md")], home=self.home
            )
        self.assertEqual(code, 4)
        self.assertIn("status: incomplete", out.getvalue())
        self.assertFalse(log.exists(), "an earlier run's log must not be left beside this attempt")

    def test_without_codex_the_review_is_blocked_with_setup_steps(self) -> None:
        repo = Repo()
        try:
            focus = repo.root / "focus.md"
            focus.write_text("focus")
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, {"PATH": str(self.home)}), redirect_stderr(stderr):
                code = codex_review.main(
                    ["--base", "HEAD", "--focus-file", str(focus), "--out", str(repo.root / "out.md")], home=self.home
                )
        finally:
            repo.close()
        self.assertEqual(code, 3)
        self.assertIn("this review is blocked", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
