"""The private checkout leaves nothing behind, even when it cannot be made."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from review_checkout import isolated_checkout

from tests.support import Repo


class ReviewCheckoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.commit = self.repo.commit({"src/a.py": "1\n", "docs/records/r.md": "a review\n"})

    def tearDown(self) -> None:
        self.repo.close()

    def leftovers(self) -> set[Path]:
        return set(Path(tempfile.gettempdir()).glob("review-checkout-*"))

    def test_the_checkout_has_the_commit_without_review_records_and_is_removed(self) -> None:
        with isolated_checkout(self.repo.root, self.commit) as tree:
            self.assertTrue((tree / "src/a.py").is_file())
            self.assertFalse((tree / "docs/records").exists())
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True, check=True)
            self.assertEqual(head.stdout.strip(), self.commit)
        self.assertFalse(tree.exists())

    def test_a_checkout_that_cannot_be_made_leaves_no_directory(self) -> None:
        before = self.leftovers()
        with self.assertRaises(subprocess.CalledProcessError), isolated_checkout(self.repo.root, "0" * 40):
            pass
        self.assertEqual(self.leftovers() - before, set())


if __name__ == "__main__":
    unittest.main()
