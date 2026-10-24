"""Readiness must fail closed: absent reviewers, stale evidence, failed gates, and hidden findings never pass."""

import re
import subprocess
import sys
import unittest

import readiness
from readiness import Gate, GateResult

from tests.support import SCRIPTS, Repo

CHECK = Gate("pnpm check", ("pnpm", "check"), (), "always")
REGISTER = "docs/records/r-findings.md"


def report(reviewer: str, baseline: str, reviewed: str, status: str = "complete", findings: str = "none") -> str:
    return (
        f"# Review\n\n**Status:** Complete\n\n```\nreviewer: {reviewer}\ntool: test\nmodel: not exposed\n"
        f"invocation: run-1\nreviewed_commit: {reviewed}\nbaseline: {baseline}\nstatus: {status}\n"
        f"findings: {findings}\n```\n"
    )


def register(rows: str = "", reports: tuple[str, ...] = ("claude.md", "codex.md")) -> str:
    links = "\n".join(f"- [{name}]({name})" for name in reports)
    return (
        "# Findings\n\n**Status:** Complete\n\n"
        f"{links}\n\n"
        "| ID | Severity | Source | Finding | Disposition | Fix | Evidence | Tracking |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"{rows}"
    )


class ReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.base = self.repo.commit({"src/app.py": "v1\n"}, "base")
        self.candidate = self.repo.commit({"src/app.py": "v2\n"}, "feature")

    def tearDown(self) -> None:
        self.repo.close()

    def record(self, files: dict[str, str]) -> str:
        """A report-only commit."""
        return self.repo.commit({f"docs/records/{k}": v for k, v in files.items()}, "reviews")

    def both_reviewed(self, rows: str = "", head: str | None = None) -> str:
        head = head or self.candidate
        return self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, head),
                "codex.md": report("codex-adversarial", self.base, head),
                "r-findings.md": register(rows),
            }
        )

    def verdict(self, results: tuple[GateResult, ...] | None = (GateResult(CHECK, True, "exit 0"),)):
        head = self.repo.git("rev-parse", "HEAD")
        return readiness.evaluate(
            self.repo.root,
            self.base,
            head,
            self.repo.root / REGISTER,
            readiness.DEFAULT_REVIEWERS,
            (CHECK,),
            results,
        )

    def test_ready_when_both_reviewers_cover_the_candidate_and_gates_pass(self) -> None:
        self.both_reviewed()
        verdict = self.verdict()
        self.assertEqual(verdict.status, "READY", verdict)

    def test_a_missing_reviewer_is_incomplete(self) -> None:
        self.record(
            {"claude.md": report("claude-code-reviewer", self.base, self.candidate), "r-findings.md": register()}
        )
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertIn("no report from required reviewer codex-adversarial", verdict.gaps)

    def test_a_blocked_reviewer_is_incomplete(self) -> None:
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, self.candidate),
                "codex.md": report("codex-adversarial", self.base, self.candidate, status="blocked"),
                "r-findings.md": register(),
            }
        )
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertTrue(any("codex-adversarial has no complete report (blocked)" in g for g in verdict.gaps))

    def test_a_source_change_after_the_review_makes_the_evidence_stale(self) -> None:
        self.both_reviewed()
        self.repo.commit({"src/app.py": "v3\n"}, "unreviewed change")
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertEqual(dict(verdict.coverage), {"claude-code-reviewer": False, "codex-adversarial": False})

    def test_report_only_commits_keep_the_evidence_valid(self) -> None:
        self.both_reviewed()
        self.record({"readiness.md": "# Readiness\n\n**Status:** Complete\n"})
        self.assertEqual(self.verdict().status, "READY")

    def test_a_gate_detail_with_pipes_stays_one_table_cell(self) -> None:
        self.both_reviewed()
        text = readiness.render(
            self.verdict(), self.base, self.candidate, (CHECK,), (GateResult(CHECK, True, "a | b"),)
        )
        row = next(line for line in text.splitlines() if line.startswith("| `pnpm check`"))
        self.assertEqual(len(re.split(r"(?<!\\)\|", row)), 5, row)

    def test_evidence_kept_uncommitted_in_the_ignored_reviews_folder_counts(self) -> None:
        candidate = self.repo.commit({".gitignore": ".reviews/\n"}, "ignore raw review output")
        self.repo.write(
            {
                ".reviews/run/claude.md": report("claude-code-reviewer", self.base, candidate),
                ".reviews/run/codex.md": report("codex-adversarial", self.base, candidate),
                ".reviews/run/findings.md": register(),
            }
        )
        head = self.record({"run.md": "# Run record\n\n**Status:** Complete\n"})
        verdict = readiness.evaluate(
            self.repo.root,
            self.base,
            head,
            self.repo.root / ".reviews" / "run" / "findings.md",
            readiness.DEFAULT_REVIEWERS,
            (CHECK,),
            (GateResult(CHECK, True, "exit 0"),),
        )
        self.assertEqual(verdict.status, "READY", verdict)
        self.assertEqual(self.repo.git("ls-files", ".reviews"), "")

    def test_a_fix_round_chains_from_the_previous_candidate(self) -> None:
        self.both_reviewed(rows="| C1 | high | claude.md | bug | open | | | |\n")
        fix = self.repo.commit({"src/app.py": "v3\n"}, "fix")
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, self.candidate, findings="C1"),
                "claude-2.md": report("claude-code-reviewer", self.candidate, fix),
                "codex.md": report("codex-adversarial", self.base, self.candidate),
                "codex-2.md": report("codex-adversarial", self.candidate, fix),
                "r-findings.md": register(
                    f"| C1 | high | claude.md | bug | fixed | {fix} | regression test; claude-2.md | |\n",
                    ("claude.md", "claude-2.md", "codex.md", "codex-2.md"),
                ),
            }
        )
        self.assertEqual(self.verdict().status, "READY")

    def test_the_fix_round_is_required_for_each_reviewer(self) -> None:
        fix = self.repo.commit({"src/app.py": "v3\n"}, "fix")
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, self.candidate),
                "claude-2.md": report("claude-code-reviewer", self.candidate, fix),
                "codex.md": report("codex-adversarial", self.base, self.candidate),
                "r-findings.md": register("", ("claude.md", "claude-2.md", "codex.md")),
            }
        )
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertEqual(dict(verdict.coverage), {"claude-code-reviewer": True, "codex-adversarial": False})

    def test_a_failed_gate_is_not_ready(self) -> None:
        self.both_reviewed()
        verdict = self.verdict((GateResult(CHECK, False, "exit 1"),))
        self.assertEqual(verdict.status, "NOT READY")

    def test_gates_not_run_are_incomplete(self) -> None:
        self.both_reviewed()
        self.assertEqual(self.verdict(None).status, "INCOMPLETE")

    def test_an_open_finding_is_not_ready(self) -> None:
        self.both_reviewed("| C1 | low | claude.md | nit | open | | | |\n")
        verdict = self.verdict()
        self.assertEqual(verdict.status, "NOT READY")
        self.assertIn("finding C1 is open", verdict.blocking)

    def test_a_deferral_must_be_recorded_where_it_points(self) -> None:
        self.repo.commit({"docs/adr.md": "# ADR\n\nNothing about the finding.\n"})
        self.both_reviewed("| C1 | high | codex.md | gap | deferred | | local only | [adr](../adr.md) |\n")
        verdict = self.verdict()
        self.assertEqual(verdict.status, "NOT READY")
        self.assertIn("finding C1 is deferred, but its tracking document does not mention C1", verdict.blocking)

    def test_a_recorded_deferral_passes_but_stays_listed(self) -> None:
        tracked = self.repo.commit({"docs/adr.md": "# ADR\n\nKnown gap C1, accepted for now.\n"})
        self.both_reviewed("| C1 | high | codex.md | gap | deferred | | local only | [adr](../adr.md) |\n", tracked)
        verdict = self.verdict()
        self.assertEqual(verdict.status, "READY")
        text = readiness.render(verdict, self.base, self.candidate, (CHECK,), None)
        self.assertIn("Deferred, not fixed:", text)

    def test_a_fix_must_name_a_commit_in_the_candidate(self) -> None:
        self.both_reviewed("| C1 | high | claude.md | bug | fixed | 0123456789abcdef | said so | |\n")
        self.assertEqual(self.verdict().status, "NOT READY")

    def test_a_rejection_needs_evidence(self) -> None:
        self.both_reviewed("| C1 | low | claude.md | claim | rejected | | | |\n")
        self.assertIn("finding C1 is rejected without evidence", self.verdict().blocking)

    def test_report_findings_must_be_registered(self) -> None:
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, self.candidate, findings="C9"),
                "codex.md": report("codex-adversarial", self.base, self.candidate),
                "r-findings.md": register(),
            }
        )
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertTrue(any("lists finding C9, which is not in the register" in g for g in verdict.gaps))

    def test_an_uncommitted_change_is_incomplete(self) -> None:
        self.both_reviewed()
        self.repo.write({"src/app.py": "edited\n"})
        self.assertIn(
            "the working tree has uncommitted changes, so HEAD is not the whole candidate", self.verdict().gaps
        )

    def test_a_report_for_another_branch_does_not_count(self) -> None:
        self.repo.git("checkout", "-q", "-b", "other", self.base)
        elsewhere = self.repo.commit({"src/app.py": "other\n"}, "elsewhere")
        self.repo.git("checkout", "-q", "main")
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, elsewhere),
                "codex.md": report("codex-adversarial", self.base, self.candidate),
                "r-findings.md": register(),
            }
        )
        self.assertEqual(dict(self.verdict().coverage)["claude-code-reviewer"], False)

    def test_the_mandatory_reviewers_cannot_be_dropped(self) -> None:
        self.record({"r-findings.md": register("", ())})
        head = self.repo.git("rev-parse", "HEAD")
        ok = (GateResult(CHECK, True, "exit 0"),)
        verdict = readiness.evaluate(self.repo.root, self.base, head, self.repo.root / REGISTER, (), (CHECK,), ok)
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertEqual([r for r, _ in verdict.coverage], list(readiness.DEFAULT_REVIEWERS))

    def test_the_cli_cannot_replace_the_required_reviewers(self) -> None:
        self.both_reviewed()
        for flag in (["--require", ""], ["--require", "codex-adversarial"]):
            with self.subTest(flag), self.assertRaises(SystemExit):
                readiness.main(["--base", self.base, "--register", REGISTER, "--skip-gates", *flag])

    def test_an_extra_reviewer_is_added_to_the_mandatory_ones(self) -> None:
        self.both_reviewed()
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "readiness.py"),
                *("--base", self.base, "--register", REGISTER, "--skip-gates", "--also-require", "human"),
            ],
            cwd=self.repo.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertIn("no report from required reviewer human", run.stdout)
        self.assertIn("| claude-code-reviewer |", run.stdout)

    def test_a_report_without_provenance_does_not_count(self) -> None:
        bare = report("codex-adversarial", self.base, self.candidate).replace("tool: test\n", "tool:\n")
        bare = bare.replace("invocation: run-1\n", "")
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, self.candidate),
                "codex.md": bare,
                "r-findings.md": register(),
            }
        )
        verdict = self.verdict()
        self.assertEqual(verdict.status, "INCOMPLETE")
        self.assertEqual(dict(verdict.coverage)["codex-adversarial"], False)
        self.assertTrue(any("tool, model, and invocation" in g for g in verdict.gaps), verdict.gaps)

    def test_a_report_made_from_the_template_is_valid(self) -> None:
        template = (SCRIPTS.parent / "docs" / "templates" / "review-report.md").read_text(encoding="utf-8")
        values = {
            "reviewer": "claude-code-reviewer",
            "tool": "Claude Code",
            "model": "not exposed",
            "invocation": "session 1",
            "reviewed_commit": self.candidate,
            "baseline": self.base,
            "status": "complete",
            "findings": "none",
        }
        filled = re.sub(r"^(\w+): <[^>]*>$", lambda m: f"{m.group(1)}: {values[m.group(1)]}", template, flags=re.M)
        path = self.repo.root / "report.md"
        path.write_text(filled, encoding="utf-8")
        parsed, problems = readiness.parse_report(self.repo.root, path)
        self.assertIsNotNone(parsed)
        self.assertEqual(problems, ())

    def test_a_fix_must_be_a_commit_after_the_base(self) -> None:
        self.both_reviewed(f"| C1 | high | claude.md | bug | fixed | {self.base} | said so | |\n")
        self.assertIn(
            "finding C1 is fixed, but its fix column names no commit between the base and the candidate",
            self.verdict().blocking,
        )

    def test_a_fix_must_come_after_the_review_that_raised_the_finding(self) -> None:
        earlier = self.repo.commit({"src/app.py": "v3\n"}, "change before the review")
        reviewed = self.repo.commit({"src/other.py": "x\n"}, "reviewed")
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, reviewed, findings="C1"),
                "codex.md": report("codex-adversarial", self.base, reviewed),
                "r-findings.md": register(f"| C1 | high | claude.md | bug | fixed | {earlier} | said so | |\n"),
            }
        )
        self.assertIn(
            "finding C1 is fixed, but no commit in its fix column comes after the review that raised it",
            self.verdict().blocking,
        )

    def test_a_report_only_commit_is_not_a_fix(self) -> None:
        reviewed = self.candidate
        notes = self.record({"notes.md": "# Notes\n\n**Status:** Complete\n"})
        self.record(
            {
                "claude.md": report("claude-code-reviewer", self.base, reviewed, findings="C1"),
                "codex.md": report("codex-adversarial", self.base, reviewed),
                "r-findings.md": register(f"| C1 | high | claude.md | bug | fixed | {notes} | said so | |\n"),
            }
        )
        self.assertIn("finding C1 is fixed, but its fix commit changes only review records", self.verdict().blocking)

    def test_a_high_deferral_is_flagged_for_owner_acceptance(self) -> None:
        tracked = self.repo.commit({"docs/adr.md": "# ADR\n\nKnown gap C1, accepted for now.\n"})
        self.both_reviewed("| C1 | high | codex.md | gap | deferred | | local only | [adr](../adr.md) |\n", tracked)
        verdict = self.verdict()
        text = readiness.render(verdict, self.base, tracked, (CHECK,), None)
        self.assertIn("# Readiness: READY, with 1 deferred finding not fixed", text)
        self.assertIn("C1 (high) needs the owner's acceptance", text)
        self.assertIn("taken as declared", text)

    def test_the_cli_exits_nonzero_unless_ready(self) -> None:
        self.both_reviewed()
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "readiness.py"),
                "--base",
                self.base,
                "--register",
                REGISTER,
                "--skip-gates",
            ],
            cwd=self.repo.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn("# Readiness: INCOMPLETE", run.stdout)


class GateRoutingTest(unittest.TestCase):
    def names(self, *paths: str) -> list[str]:
        return [g.name for g in readiness.required_gates(paths)]

    def test_docs_only_changes_need_only_the_check(self) -> None:
        self.assertEqual(self.names("docs/README.md", ".agents/skills/zz-review/SKILL.md"), ["pnpm check"])

    def test_web_changes_need_the_browser_journeys(self) -> None:
        self.assertEqual(self.names("apps/web/src/app/App.tsx"), ["pnpm check", "pnpm e2e"])

    def test_container_inputs_need_the_smoke_test(self) -> None:
        self.assertEqual(self.names("scripts/docker-smoke.sh"), ["pnpm check", "pnpm docker:smoke"])

    def test_both_run_the_journeys_against_the_containers_too(self) -> None:
        gates = readiness.required_gates(("apps/web/nginx/default.conf",))
        self.assertEqual([g.name for g in gates], ["pnpm check", "pnpm e2e", "SMOKE_E2E=1 pnpm docker:smoke"])
        self.assertEqual(gates[-1].env, (("SMOKE_E2E", "1"),))

    def test_run_gates_stops_at_the_first_failure(self) -> None:
        failing = Gate("fails", (sys.executable, "-c", "raise SystemExit(3)"), (), "test")
        passing = Gate("passes", (sys.executable, "-c", "print('1 passed')"), (), "test")
        with self.subTest("stop"):
            repo = Repo()
            try:
                results = readiness.run_gates(repo.root, (failing, passing), repo.root)
            finally:
                repo.close()
            self.assertEqual([(r.gate.name, r.passed) for r in results], [("fails", False)])
            self.assertTrue(results[0].detail.startswith("exit 3"))


if __name__ == "__main__":
    unittest.main()
