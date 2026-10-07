"""Runs the Claude Code `code-reviewer` agent in a fresh headless session, and records what ran.

    python3 scripts/claude_review.py --base <sha> --prompt-file <file> --inputs <dir> --out <file>

It starts `claude -p --agent code-reviewer` in a private checkout of HEAD without docs/records/ (see
review_checkout.py), with read access to --inputs (the requirements, the diff, and the gate results). The agent's
own tools are Read, Grep, and Glob. Nothing from the coordinator's session or from another reviewer reaches it
except what the prompt and inputs contain.

The final report goes to --out, and the raw event stream to the same path with .jsonl. The script prints the
evidence block for the review report, filled from the session itself: Claude Code's version, the session id, the
models in the session's usage, the reviewed commit, and the base. It exits 0 only when the session ended with a
successful result; otherwise it prints `status: incomplete`, leaves no report file, and exits 4. Fill in `findings`
with register IDs.
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from readiness import format_evidence, resolve
from review_checkout import isolated_checkout

AGENT = "code-reviewer"


@dataclass(frozen=True)
class Session:
    id: str
    version: str
    models: tuple[str, ...]
    report: str | None
    turns: int
    cost: float


def field(value: object, key: str) -> object:
    """`value[key]` when value is a JSON object; otherwise None."""
    return cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None


def summarize(stream: str) -> Session:
    """Session id, version, models, and the final report, read from `--output-format stream-json`."""
    session, version, models, report, turns, cost = "", "", (), None, 0, 0.0
    for line in stream.splitlines():
        try:
            event: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = field(event, "type")
        if kind == "system" and field(event, "subtype") == "init":
            session = str(field(event, "session_id") or "")
            version = str(field(event, "claude_code_version") or "")
        elif kind == "result":
            usage = field(event, "modelUsage")
            models = tuple(str(m) for m in cast("dict[str, object]", usage)) if isinstance(usage, dict) else ()
            text = field(event, "result")
            ok = field(event, "subtype") == "success" and isinstance(text, str) and text.strip() != ""
            report = text if ok and isinstance(text, str) else None
            number = field(event, "num_turns")
            turns = number if isinstance(number, int) else 0
            spent = field(event, "total_cost_usd")
            cost = float(spent) if isinstance(spent, int | float) else 0.0
    return Session(session, version, models, report, turns, cost)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--inputs", required=True, help="a directory the reviewer may read, outside the repository")
    parser.add_argument("--out", required=True, help="the review report; it must lie outside --inputs")
    parser.add_argument("--max-turns", default="150")
    args = parser.parse_args(argv)
    if Path(args.out).resolve().is_relative_to(Path(args.inputs).resolve()):
        parser.error("--out must be outside --inputs: the reviewer can read everything in --inputs")
    root = Path(__file__).resolve().parent.parent
    base, head = resolve(root, args.base), resolve(root, "HEAD")
    if base is None or head is None:
        print(f"cannot resolve the base {args.base!r} or HEAD", file=sys.stderr)
        return 2
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    command = ["claude", "-p", prompt, "--agent", AGENT, "--add-dir", args.inputs, "--max-turns", args.max_turns]
    command += ["--output-format", "stream-json", "--verbose"]
    stream = out.with_suffix(".jsonl")
    stream.unlink(missing_ok=True)
    try:
        with isolated_checkout(root, head) as tree:
            run = subprocess.run(
                command, cwd=tree, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
            )
    except subprocess.CalledProcessError as error:
        print(f"The launcher could not make a private checkout of {head}: {error}.", file=sys.stderr)
        run = subprocess.CompletedProcess(command, 1, "", "")
    stream.write_text(run.stdout, encoding="utf-8")
    found = summarize(run.stdout)
    if found.report is not None:
        out.write_text(found.report, encoding="utf-8")
    complete = found.report is not None
    if not complete:
        print(f"The session produced no review (exit {run.returncode}). Record it as incomplete.", file=sys.stderr)
    evidence = {
        "reviewer": "claude-code-reviewer",
        "tool": f"Claude Code {found.version or 'unknown'}, claude -p --agent {AGENT}",
        "model": ", ".join(found.models) or "not exposed",
        "invocation": f"session {found.id}" if found.id else "not exposed",
        "reviewed_commit": head,
        "baseline": base,
        "status": "complete" if complete else "incomplete",
        "findings": "<register IDs, or none>",
    }
    print(format_evidence(evidence))
    print(f"report: {out}; turns: {found.turns}; cost: {found.cost}")
    return 0 if complete else 4


if __name__ == "__main__":
    sys.exit(main())
