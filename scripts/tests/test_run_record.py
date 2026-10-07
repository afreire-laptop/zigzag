"""A run record summarizes the private evidence of a run, binds to it by hash, and never leaks or overwrites."""

import hashlib
import re
import subprocess
import sys
import unittest

import check_docs
import readiness
import run_record
from readiness import Finding, Gate, GateResult

from tests.support import SCRIPTS, Repo

CHECK = Gate("pnpm check", ("pnpm", "check"), (), "always")
OUT = "docs/records/2026-10-07-demo.md"
SESSION = "0123abcd-4567-89ab-cdef-0123456789ab"


def report(reviewer: str, baseline: str, reviewed: str, findings: str) -> str:
    return (
        f"# Review\n\n**Status:** Complete\n\n```\nreviewer: {reviewer}\ntool: Tool 1.0\nmodel: model-1\n"
        f"invocation: session {SESSION}\nreviewed_commit: {reviewed}\nbaseline: {baseline}\nstatus: complete\n"
        f"findings: {findings}\n```\n\n## Report (verbatim)\n\nVERBATIM-BODY\n"
    )


class RunRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.base = self.repo.commit(
            {"src/app.py": "v1\n", "docs/specs/s.md": "**Status:** Draft\n\nTracks X2.\n"}, "base"
        )
        self.candidate = self.repo.commit({"src/app.py": "v2\n", ".gitignore": ".reviews/\n"}, "feature")

    def tearDown(self) -> None:
        self.repo.close()

    def write_run(self, finding_text: str = "A bug in the parser", tracking: str = "../../docs/specs/s.md") -> None:
        self.repo.write(
            {
                ".reviews/run/claude.md": report("claude-code-reviewer", self.base, self.candidate, "C1"),
                ".reviews/run/codex.md": report("codex-adversarial", self.base, self.candidate, "X2"),
                ".reviews/run/findings.md": (
                    "# Findings\n\n**Status:** Complete\n\n- [claude](claude.md)\n- [codex](codex.md)\n\n"
                    "| ID | Severity | Source | Finding | Disposition | Fix | Evidence | Tracking |\n"
                    "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
                    f"| C1 | high | Claude, round 1 | {finding_text} | rejected | | Refuted by test_parser | |\n"
                    "| X2 | high | Codex, round 1 | A gap | deferred | | "
                    f"EVIDENCE-NOTE {SESSION} | [spec]({tracking}) |\n"
                ),
            }
        )
        register = self.repo.root / ".reviews" / "run" / "findings.md"
        results = (GateResult(CHECK, True, "\x1b[32mexit 0\x1b[0m | Tests 3 passed"),)
        verdict = readiness.evaluate(self.repo.root, self.base, self.candidate, register, (), (CHECK,), results)
        text = readiness.render(verdict, self.base, self.candidate, (CHECK,), results)
        self.repo.write({".reviews/run/readiness.md": text})

    def generate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_record.py"),
                *("--run", ".reviews/run", "--title", "Demo", "--summary", "Did a thing."),
                *("--decision", "2026-10-07: the owner accepted X2.", "--out", OUT),
                *extra,
            ],
            cwd=self.repo.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def sha256(self, name: str) -> str:
        return hashlib.sha256((self.repo.root / name).read_bytes()).hexdigest()

    def test_a_record_summarizes_the_run_and_binds_to_its_raw_files(self) -> None:
        self.write_run()
        run = self.generate()
        self.assertEqual(run.returncode, 0, run.stderr)
        text = (self.repo.root / OUT).read_text(encoding="utf-8")
        self.assertIn("**Readiness:** READY, with 1 deferred finding not fixed", text)
        self.assertIn("**Status:** Complete", text)
        self.assertIn("Did a thing.", text)
        for name in ("claude.md", "codex.md", "findings.md", "readiness.md"):
            self.assertIn(self.sha256(f".reviews/run/{name}"), text)
        self.assertIn("| 1 | claude-code-reviewer | Tool 1.0 | model-1 |", text)
        self.assertIn("| C1 | high | Claude, round 1 | A bug in the parser | rejected | Refuted by test_parser |", text)
        self.assertIn("[spec](../specs/s.md)", text)
        self.assertIn("- 2026-10-07: the owner accepted X2.", text)
        self.assertEqual(check_docs.record_leaks(OUT, text), [])

    def test_a_record_of_an_unready_run_says_so(self) -> None:
        self.write_run(tracking="../../src/app.py")
        self.assertEqual(self.generate().returncode, 0)
        text = (self.repo.root / OUT).read_text(encoding="utf-8")
        self.assertIn("**Status:** Incomplete", text)
        self.assertIn("**Readiness:** NOT READY", text)
        self.assertIn("- NOT READY: finding X2 is deferred, but its tracking document does not mention X2", text)

    def test_a_fixed_finding_shows_its_fix_commit(self) -> None:
        fixed = Finding("C1", "high", "fixed", "abc1234", "a note", "", "Claude", "A bug")
        self.assertEqual(run_record.outcome(fixed), "abc1234")

    def test_a_record_leaves_out_raw_content(self) -> None:
        self.write_run()
        self.assertEqual(self.generate().returncode, 0)
        text = (self.repo.root / OUT).read_text(encoding="utf-8")
        for raw in ("VERBATIM-BODY", "EVIDENCE-NOTE", SESSION[:8], "\x1b["):
            self.assertNotIn(raw, text)
        gate = next(line for line in text.splitlines() if line.startswith("| `pnpm check`"))
        self.assertEqual(len(re.split(r"(?<!\\)\|", gate)), 5, gate)

    def test_a_record_is_never_overwritten(self) -> None:
        self.write_run()
        self.assertEqual(self.generate().returncode, 0)
        before = (self.repo.root / OUT).read_text(encoding="utf-8")
        again = self.generate()
        self.assertEqual(again.returncode, 1)
        self.assertIn("already exists", again.stderr)
        self.assertEqual((self.repo.root / OUT).read_text(encoding="utf-8"), before)

    def test_a_record_that_would_leak_is_not_written(self) -> None:
        self.write_run(finding_text="Fails under /Users/someone/project")
        run = self.generate()
        self.assertEqual(run.returncode, 1)
        self.assertIn("names a local path", run.stderr)
        self.assertFalse((self.repo.root / OUT).exists())

    def test_a_run_without_readiness_output_is_refused(self) -> None:
        self.write_run()
        (self.repo.root / ".reviews" / "run" / "readiness.md").unlink()
        run = self.generate()
        self.assertEqual(run.returncode, 2)
        self.assertIn("readiness.md", run.stderr)
        self.assertFalse((self.repo.root / OUT).exists())


if __name__ == "__main__":
    unittest.main()
