"""Runs a Codex adversarial review of `<base>..HEAD` with read-only access, and records what ran.

    python3 scripts/codex_review.py --base <sha> --focus-file <file> --out <file>

Codex reviews a private checkout of HEAD without docs/records/ (see review_checkout.py), so a Claude Code session
ending in the main workspace cannot stop it, and other reviewers' reports are not there to read.

1. If the Codex plugin for Claude Code (codex@openai-codex) is installed, it runs the plugin's own
   `adversarial-review --wait --base <sha>`, in a read-only sandbox, with the focus file as focus text.
2. Otherwise, if the Codex CLI is installed, it runs `codex exec --sandbox read-only` with the adversarial
   instructions below and the focus file.
3. Otherwise, it prints the setup steps and exits 3. Record that review as blocked.

The report goes to --out, and Codex's progress to the same path with .log. The script then prints the evidence
block for the review report, filled from what actually ran: the tool, Codex's version, the thread id, the model
Codex's client log records for that thread (the requested model; the served one is not exposed), the reviewed
commit, and the base. It exits 0 only when Codex produced a report with a verdict; otherwise it prints `status:
incomplete`, leaves no report file, and exits 4. Fill in `findings` with register IDs.
"""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from readiness import format_evidence, resolve
from review_checkout import isolated_checkout

PLUGIN = "codex@openai-codex"
REPORT_MARK = "# Codex Adversarial Review"
NO_REPORT = "Codex did not return valid structured JSON"
SETUP = """Codex is not available, so this review is blocked. To enable it:
  1. Install the Codex CLI: npm install -g @openai/codex   (or see https://developers.openai.com/codex/cli)
  2. Sign in: codex login
  3. Optional, for the plugin path: in Claude Code, /plugin install codex@openai-codex, then /codex:setup
Then rerun: python3 scripts/codex_review.py --base <sha> --focus-file <file> --out <file>"""
INSTRUCTIONS = """You are performing an adversarial review. Your job is to find the strongest concrete reasons the
change between {base} and HEAD should not ship. Inspect it yourself with `git diff {base}...HEAD` and by reading
files. You have read-only access; do not modify anything.

Report only material findings you can defend from the code. For each: severity (critical, high, medium, low),
path:line, a concrete trigger or reproduction, the impact, and a minimal remedy. Label inferences as hypotheses.
List the areas you did not examine. If you find nothing material, say so; do not manufacture findings.
End with one line: `Verdict: approve` or `Verdict: needs-attention`.

Focus and requirements:
{focus}"""


def companion_script(home: Path) -> Path | None:
    """The plugin's companion script, found through Claude Code's plugin registry."""
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
        install = Path(data["plugins"][PLUGIN][0]["installPath"])
    except OSError, ValueError, KeyError, IndexError, TypeError:
        return None
    script = install / "scripts" / "codex-companion.mjs"
    return script if script.is_file() else None


def logged_model(home: Path, thread: str) -> str | None:
    """The model Codex's local client log records for a thread; this is the requested model."""
    database = home / ".codex" / "logs_2.sqlite"
    if not thread or not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
            rows = connection.execute("select feedback_log_body from logs where thread_id = ?", (thread,)).fetchall()
    except sqlite3.Error:
        return None
    models = {m for (body,) in rows if isinstance(body, str) for m in re.findall(r"\bmodel=([\w.:-]+)", body)}
    efforts = {e for (body,) in rows if isinstance(body, str) for e in re.findall(r"reasoning_effort=(\w+)", body)}
    if len(models) != 1:
        return None
    effort = f", reasoning effort {efforts.pop()}" if len(efforts) == 1 else ""
    return f"{models.pop()}{effort}"


def version() -> str:
    try:
        return subprocess.run(["codex", "--version"], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return "unknown"


def review(
    tree: Path, out: Path, log: Path, script: Path | None, base: str, focus: str
) -> tuple[str, subprocess.CompletedProcess[str], bool]:
    """Runs one review in `tree` through the plugin, or else the CLI; returns the tool, the run, and whether a
    report was produced."""
    if script is not None:
        tool = f"Codex plugin {PLUGIN} {script.parent.parent.name}, adversarial-review --wait --base; read-only sandbox"
        command = ["node", str(script), "adversarial-review", "--wait", "--base", base, focus]
        run = subprocess.run(command, cwd=tree, capture_output=True, text=True, check=False)
        out.write_text(run.stdout, encoding="utf-8")
        log.write_text(run.stderr, encoding="utf-8")
        produced = REPORT_MARK in run.stdout and "Verdict:" in run.stdout and NO_REPORT not in run.stdout
        return tool, run, produced
    prompt = INSTRUCTIONS.format(base=base, focus=focus)
    command = ["codex", "exec", "--sandbox", "read-only", "--json", "-C", str(tree), "-o", str(out), "-"]
    run = subprocess.run(command, input=prompt, capture_output=True, text=True, check=False)
    log.write_text(run.stdout + run.stderr, encoding="utf-8")
    return "codex exec --sandbox read-only", run, out.is_file() and "Verdict:" in out.read_text(encoding="utf-8")


def main(argv: Sequence[str] | None = None, home: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--focus-file", required=True)
    parser.add_argument("--out", required=True, help="the review report; progress goes to the same path with .log")
    args = parser.parse_args(argv)
    home = home or Path.home()
    root = Path(__file__).resolve().parent.parent
    script = companion_script(home)
    plugin = script is not None and shutil.which("node") is not None
    if not plugin and not shutil.which("codex"):
        print(SETUP, file=sys.stderr)
        return 3
    base, head = resolve(root, args.base), resolve(root, "HEAD")
    if base is None or head is None:
        print(f"cannot resolve the base {args.base!r} or HEAD", file=sys.stderr)
        return 2
    focus = Path(args.focus_file).read_text(encoding="utf-8")
    out = Path(args.out)
    log = out.with_suffix(".log")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    log.unlink(missing_ok=True)
    tool = "Codex plugin" if script and plugin else "codex exec --sandbox read-only"
    run = subprocess.CompletedProcess[str]([], 1, "", "")
    produced = False
    try:
        with isolated_checkout(root, head) as tree:
            tool, run, produced = review(tree, out, log, script if plugin else None, base, focus)
    except subprocess.CalledProcessError as error:
        print(f"The launcher could not make a private checkout of {head}: {error}.", file=sys.stderr)

    ids = re.findall(r"Thread ready \(([0-9a-f-]{36})\)|\"thread_id\":\s*\"([0-9a-f-]{36})\"", run.stdout + run.stderr)
    thread = next((t for pair in ids for t in pair if t), "")
    model = logged_model(home, thread)
    complete = produced and run.returncode == 0
    if not complete:
        out.unlink(missing_ok=True)
        print(
            f"Codex produced no review that counts (exit {run.returncode}). "
            f"Record this attempt as incomplete; see {log}.",
            file=sys.stderr,
        )
    evidence = {
        "reviewer": "codex-adversarial",
        "tool": f"{tool}; {version()}",
        "model": f"{model} (requested, per the Codex client log; served model not exposed)" if model else "not exposed",
        "invocation": f"thread {thread}" if thread else "not exposed",
        "reviewed_commit": head,
        "baseline": base,
        "status": "complete" if complete else "incomplete",
        "findings": "<register IDs, or none>",
    }
    print(format_evidence(evidence))
    print(f"report: {out}; progress: {log}")
    return 0 if complete else 4


if __name__ == "__main__":
    sys.exit(main())
