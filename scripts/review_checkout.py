"""A private, temporary checkout of one commit, for one reviewer.

Each reviewer runs in its own detached git worktree, for two reasons. First, the Codex plugin's SessionEnd hook
stops the Codex runtime of the workspace whenever any Claude Code session there ends, so a review sharing the
main checkout can be cut off by an unrelated session. Second, the checkout omits docs/records/, so
other reviewers' conclusions are not in it. That is not isolation: a reviewer can still reach the main
repository by absolute path, or git history, so the prompt must still forbid reading them. The checkout is removed
afterwards.
"""

import shutil
import subprocess
import tempfile
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

HIDDEN = ("docs/records",)


@contextmanager
def isolated_checkout(root: Path, commit: str, hidden: Sequence[str] = HIDDEN) -> Generator[Path]:
    parent = Path(tempfile.mkdtemp(prefix="review-checkout-"))
    tree = parent / "tree"
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", "--quiet", str(tree), commit],
            cwd=root,
            check=True,
            capture_output=True,
        )
        for path in hidden:
            shutil.rmtree(tree / path, ignore_errors=True)
        yield tree
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=root, check=False, capture_output=True)
        shutil.rmtree(parent, ignore_errors=True)
