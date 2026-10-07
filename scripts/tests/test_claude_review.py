"""The Claude reviewer launcher records what ran, and never reports a review that produced nothing."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import claude_review

SESSION = "00000000-0000-4000-8000-00000000c1a0"


def events(result: str | None) -> str:
    lines: list[dict[str, object]] = [
        {
            "type": "system",
            "subtype": "init",
            "session_id": SESSION,
            "model": "claude-sonnet-5-5",
            "claude_code_version": "2.1.292",
            "tools": ["Read", "Grep", "Glob"],
        },
        {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": []}},
    ]
    if result is not None:
        lines.append(
            {
                "type": "result",
                "subtype": "success",
                "result": result,
                "num_turns": 3,
                "total_cost_usd": 0.1,
                "modelUsage": {"claude-sonnet-5-5": {}},
            }
        )
    return "\n".join(json.dumps(line) for line in lines) + "\n"


class ClaudeReviewTest(unittest.TestCase):
    def run_review(
        self, stream: str, stale: str | None = None, script: str | None = None, out_name: str = "out.md"
    ) -> tuple[int, str, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "stream.jsonl").write_text(stream)
            claude = home / "claude"
            claude.write_text(script or f"#!/bin/sh\ncat '{home}/stream.jsonl'\n")
            claude.chmod(0o755)
            prompt = home / "prompt.md"
            prompt.write_text("review this")
            out_file = home / out_name
            if stale is not None:
                out_file.write_text(stale)
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch.dict(os.environ, {"PATH": f"{home}:{os.environ['PATH']}"}),
                redirect_stdout(out),
                redirect_stderr(err),
            ):
                inputs = home / "inputs"
                inputs.mkdir()
                code = claude_review.main(
                    ["--base", "HEAD", "--prompt-file", str(prompt), "--inputs", str(inputs), "--out", str(out_file)]
                )
            written = out_file.read_text() if out_file.exists() else ""
            return code, out.getvalue(), err.getvalue(), written

    def test_a_completed_review_writes_the_report_and_its_evidence(self) -> None:
        code, out, _, report = self.run_review(events("# Review\n\nNo findings."))
        self.assertEqual(code, 0)
        self.assertEqual(report, "# Review\n\nNo findings.")
        self.assertIn("reviewer: claude-code-reviewer", out)
        self.assertIn(f"invocation: session {SESSION}", out)
        self.assertIn("model: claude-sonnet-5-5", out)
        self.assertIn("tool: Claude Code 2.1.292, claude -p --agent code-reviewer", out)
        self.assertIn("status: complete", out)
        self.assertRegex(out, r"reviewed_commit: [0-9a-f]{40}")

    def test_a_session_without_a_result_is_incomplete(self) -> None:
        code, out, err, report = self.run_review(events(None), stale="# An earlier report")
        self.assertEqual(code, 4)
        self.assertIn("produced no review", err)
        self.assertIn("status: incomplete", out)
        self.assertEqual(report, "", "a stale report must not survive an incomplete run")

    def test_the_report_directory_is_created_before_the_review_runs(self) -> None:
        """A missing --out directory must not lose a finished, paid review."""
        code, _, err, report = self.run_review(events("# Review"), out_name="new/dir/claude.md")
        self.assertEqual(code, 0, err)
        self.assertEqual(report, "# Review")

    def test_the_report_may_not_be_written_where_the_reviewer_can_read(self) -> None:
        """Reviews written into --inputs would be readable by a later or concurrent reviewer."""
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "prompt.md"
            prompt.write_text("review this")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                claude_review.main(
                    ["--base", "HEAD", "--prompt-file", str(prompt), "--inputs", tmp, "--out", f"{tmp}/r.md"]
                )

    def test_a_checkout_that_cannot_be_made_is_an_incomplete_review(self) -> None:
        with (
            mock.patch.object(
                claude_review, "isolated_checkout", side_effect=subprocess.CalledProcessError(128, "git")
            ),
            tempfile.TemporaryDirectory() as tmp,
            tempfile.TemporaryDirectory() as inputs,
        ):
            prompt = Path(tmp) / "prompt.md"
            prompt.write_text("review this")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = claude_review.main(
                    ["--base", "HEAD", "--prompt-file", str(prompt), "--inputs", inputs, "--out", f"{tmp}/r.md"]
                )
        self.assertEqual(code, 4)
        self.assertIn("status: incomplete", out.getvalue())
        self.assertIn("could not make a private checkout", err.getvalue())

    def test_the_reviewer_runs_in_its_own_checkout_without_review_records(self) -> None:
        """Another session ending in the main workspace cannot stop it, and other reviews are not there to read."""
        emit = (
            "import json, sys; "
            'print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "claude_code_version": "x"})); '
            'print(json.dumps({"type": "result", "subtype": "success", "result": " ".join(sys.argv[1:]), '
            '"modelUsage": {"m": {}}}))'
        )
        script = (
            "#!/bin/sh\n"
            "reviews=$(test -e docs/records && echo present || echo absent)\n"
            f'python3 -c \'{emit}\' "$(pwd)" "reviews=$reviews" "head=$(git rev-parse HEAD)"\n'
        )
        code, _, err, report = self.run_review("", script=script)
        self.assertEqual(code, 0, err)
        place, reviews, head = report.split(" ")
        root = Path(claude_review.__file__).resolve().parent.parent
        self.assertNotEqual(Path(place).resolve(), root)
        self.assertEqual(reviews, "reviews=absent")
        self.assertEqual(head.removeprefix("head="), claude_review.resolve(root, "HEAD"))
        self.assertFalse(Path(place).exists(), "the checkout is removed afterwards")


if __name__ == "__main__":
    unittest.main()
