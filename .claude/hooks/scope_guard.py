"""PreToolUse hook that keeps an implementation agent's Edit and Write calls inside its own paths.

    python3 scope_guard.py --allow apps/api/ [--allow ...] [--deny apps/api/openapi.json ...]

Claude Code passes the tool call as JSON on stdin. Exit 0 allows the call; exit 2 blocks it and shows the
reason (stderr) to the agent. Claude Code treats any other exit code as a non-blocking error, so every failure
here returns 2: an unreadable input, a target that cannot be determined or resolves outside the repository, and
any unexpected error. The agents' hook command adds `|| exit 2`, so a missing or failing interpreter blocks
too. It runs on Python 3.9 and later, because it uses whatever python3 is on PATH. Shell commands are not
covered.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast


def field(value: object, key: str) -> object:
    """`value[key]` when value is a JSON object; otherwise None."""
    return cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None


def target_of(event: object) -> str | None:
    tool_input = field(event, "tool_input")
    for key in ("file_path", "notebook_path"):
        value = field(tool_input, key)
        if isinstance(value, str) and value:
            return value
    return None


def within(relative: str, prefix: str) -> bool:
    return relative == prefix.rstrip("/") or relative.startswith(prefix if prefix.endswith("/") else prefix + "/")


def decide(event: object, root: Path, allow: Sequence[str], deny: Sequence[str]) -> str | None:
    """None when the call may proceed; otherwise the reason it is blocked."""
    target = target_of(event)
    if target is None:
        return "scope guard: the tool call names no file, so its scope cannot be checked"
    path = Path(target)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        return f"scope guard: {target} is outside the repository"
    relative = resolved.relative_to(root).as_posix()
    if any(within(relative, d) for d in deny):
        return f"scope guard: {relative} is owned by the coordinator or must stay unmodified; ask for the change"
    if not any(within(relative, a) for a in allow):
        return f"scope guard: {relative} is outside this agent's paths ({', '.join(allow)}); ask the coordinator"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return guard(argv)
    except Exception as error:
        print(f"scope guard: blocked because the check failed: {error!r}", file=sys.stderr)
        return 2


def guard(argv: Sequence[str] | None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow", action="append", default=[], required=True)
    parser.add_argument("--deny", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        event: object = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("scope guard: the hook input is not JSON", file=sys.stderr)
        return 2
    cwd = field(event, "cwd")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or (cwd if isinstance(cwd, str) else None)
    if not project:
        print("scope guard: CLAUDE_PROJECT_DIR is not set", file=sys.stderr)
        return 2
    reason = decide(event, Path(project).resolve(), args.allow, args.deny)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
