"""The docs check finds broken references, missing status lines, unlisted templates, and unportable skills."""

import os
import unittest

import check_docs

from tests.support import Repo

SKILL = "---\nname: {name}\ndescription: Does a thing. Use when testing.\n---\n\nBody.\n"
README = "# Docs\n\n- [adr](templates/adr.md)\n"
TEMPLATE = "# ADR\n\n**Status:** Proposed\n"


class CheckDocsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.repo.write(
            {
                "docs/README.md": README,
                "docs/templates/adr.md": TEMPLATE,
                "docs/product/tenet.md": "# Tenet\n\n**Status:** Current\n\nSee [the template](../templates/adr.md).\n",
                ".agents/skills/zz-demo/SKILL.md": SKILL.format(name="zz-demo"),
                ".claude/agents/code-reviewer.md": (
                    "---\nname: code-reviewer\ndescription: Reviews.\ntools: Read, Grep, Glob\nmodel: sonnet\n---\n"
                ),
            }
        )
        (self.repo.root / ".claude" / "skills").mkdir(parents=True)
        os.symlink("../../.agents/skills/zz-demo", self.repo.root / ".claude" / "skills" / "zz-demo")

    def tearDown(self) -> None:
        self.repo.close()

    def problems(self) -> list[str]:
        return check_docs.check(self.repo.root)

    def test_a_consistent_tree_passes(self) -> None:
        self.assertEqual(self.problems(), [])

    def test_a_broken_relative_link_is_reported(self) -> None:
        self.repo.write({"docs/product/journeys.md": "**Status:** Current\n\n[gone](tenet-old.md)\n"})
        self.assertIn("docs/product/journeys.md:3: broken link to tenet-old.md", self.problems())

    def test_links_inside_code_are_ignored(self) -> None:
        self.repo.write(
            {"docs/product/journeys.md": "**Status:** Current\n\n```\n[x](nowhere.md)\n```\n`[y](no.md)`\n"}
        )
        self.assertEqual(self.problems(), [])

    def test_a_stale_path_mention_in_code_is_reported(self) -> None:
        self.repo.write({"apps/api/evals/run.py": '"""Record results in docs/observations.md."""\n'})
        self.assertIn("apps/api/evals/run.py:1: mentions missing docs/observations.md", self.problems())

    def test_a_run_record_has_no_exemption_for_quoted_paths(self) -> None:
        self.repo.write(
            {"docs/records/r.md": "**Status:** Complete\n\n## Report (verbatim)\n\nQuoted: docs/observations.md\n"}
        )
        self.assertIn("docs/records/r.md:5: mentions missing docs/observations.md", self.problems())

    def test_a_run_record_may_not_name_local_paths_ids_or_costs(self) -> None:
        record = (
            "**Status:** Complete\n\n"
            "Ran in /Users/someone/repo.\n"
            "Thread 0f0f0f0f-1234 and session 0123abcd-4567-89ab-cdef-0123456789ab.\n"
            "It cost $0.42.\n"
            "Raw report SHA-256 `65035fa20a373f719cc6d756d82051388c5d36bdae8b3049649f2b038b007c50`, on 2026-10-07.\n"
        )
        self.repo.write({"docs/records/r.md": record})
        problems = self.problems()
        self.assertIn("docs/records/r.md:3: names a local path", problems)
        self.assertIn("docs/records/r.md:4: names a session or thread id", problems)
        self.assertIn("docs/records/r.md:5: names a cost", problems)
        self.assertFalse([p for p in problems if p.startswith("docs/records/r.md:6")], problems)

    def test_raw_review_output_must_stay_git_ignored(self) -> None:
        self.repo.write({".reviews/run/codex.md": "raw report\n"})
        self.assertIn(".reviews/run/codex.md: raw review output must stay git-ignored", self.problems())
        self.repo.write({".gitignore": ".reviews/\n"})
        self.assertEqual(self.problems(), [])
        self.repo.git("add", "-f", ".reviews/run/codex.md")
        self.assertIn(".reviews/run/codex.md: raw review output must stay git-ignored", self.problems())

    def test_a_document_without_a_status_line_is_reported(self) -> None:
        self.repo.write({"docs/plans/plan.md": "# Plan\n\nNo status.\n"})
        self.assertIn("docs/plans/plan.md: no **Status:** line in its first 12 lines", self.problems())

    def test_an_unlisted_template_is_reported(self) -> None:
        self.repo.write({"docs/templates/spec.md": "# Spec\n\n**Status:** Draft\n"})
        self.assertIn("docs/templates/spec.md: not listed in docs/README.md", self.problems())

    def test_a_skill_without_a_claude_link_is_reported(self) -> None:
        self.repo.write({".agents/skills/zz-other/SKILL.md": SKILL.format(name="zz-other")})
        self.assertIn(
            ".claude/skills/zz-other: missing; it must be a symlink to ../../.agents/skills/zz-other", self.problems()
        )

    def test_an_absolute_skill_link_is_reported(self) -> None:
        link = self.repo.root / ".claude" / "skills" / "zz-demo"
        link.unlink()
        os.symlink(self.repo.root / ".agents" / "skills" / "zz-demo", link)
        self.assertTrue(any("is absolute" in p for p in self.problems()))

    def test_a_skill_name_must_match_its_directory(self) -> None:
        self.repo.write({".agents/skills/zz-demo/SKILL.md": SKILL.format(name="demo")})
        self.assertIn(".agents/skills/zz-demo/SKILL.md: frontmatter name must be 'zz-demo'", self.problems())

    def test_a_machine_path_in_a_skill_is_reported(self) -> None:
        self.repo.write({".agents/skills/zz-demo/notes.md": "Run /Users/someone/bin/tool\n"})
        self.assertIn(".agents/skills/zz-demo/notes.md:1: absolute machine path", self.problems())

    def test_a_reviewer_with_write_tools_is_reported(self) -> None:
        self.repo.write(
            {
                ".claude/agents/code-reviewer.md": (
                    "---\nname: code-reviewer\ndescription: Reviews.\ntools: Read, Edit\nmodel: sonnet\n---\n"
                )
            }
        )
        self.assertTrue(any("read-only reviewer" in p for p in self.problems()))

    def test_an_agent_without_an_explicit_model_is_reported(self) -> None:
        self.repo.write({".claude/agents/helper.md": "---\nname: helper\ndescription: Helps.\nmodel: inherit\n---\n"})
        self.assertIn(".claude/agents/helper.md: must name an explicit model", self.problems())


if __name__ == "__main__":
    unittest.main()
