"""Decides whether a branch is ready for a pull request, from the gates and the recorded review evidence.

    python3 scripts/readiness.py --base <sha> --register .reviews/<run>/findings.md [--out FILE]
    python3 scripts/readiness.py --base <sha> --plan          # print the gates the changed paths require
    python3 scripts/readiness.py --base <sha> --register FILE --skip-gates   # evidence only; never READY

Prints READY, INCOMPLETE, or NOT READY with every reason, and exits 0 only for READY.

- The candidate is HEAD, and the working tree must be clean.
- Each required reviewer's complete reports must chain `baseline -> reviewed_commit` from the base to the
  candidate. Commits that touch only docs/records/ (report-only commits) do not break the chain.
- Every finding in the register needs a valid disposition, and every finding a report lists must be registered.
- Every gate the changed paths require must pass.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Status = Literal["READY", "INCOMPLETE", "NOT READY"]
DEFAULT_REVIEWERS = ("claude-code-reviewer", "codex-adversarial")
REPORT_ONLY = ("docs/records/",)
DISPOSITIONS = ("open", "fixed", "rejected", "deferred")
REPORT_STATUSES = ("complete", "incomplete", "blocked")
# Who reviewed, with what, and the run's own id (a session or thread), so a reader can trace the evidence.
PROVENANCE = ("tool", "model", "invocation")
SERIOUS = ("critical", "high")

# Paths whose change needs the browser journeys, and paths whose change needs the container smoke test.
E2E_PATHS = ("apps/api/src/", "apps/web/", "packages/api-client/", "fixtures/")
SMOKE_PATHS = (
    "apps/api/Dockerfile",
    "apps/web/Dockerfile",
    "apps/web/nginx/",
    "compose.yaml",
    ".dockerignore",
    ".env.example",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.base.json",
    "apps/web/package.json",
    "apps/api/package.json",
    "packages/api-client/package.json",
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "apps/api/src/intent_harness/config.py",
    "apps/api/src/intent_harness/main.py",
    "scripts/docker-smoke.sh",
    "scripts/smoke_check.py",
    "scripts/smoke_hardening.sh",
)
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    reason: str


@dataclass(frozen=True)
class GateResult:
    gate: Gate
    passed: bool
    detail: str


@dataclass(frozen=True)
class Report:
    path: str
    reviewer: str
    tool: str
    model: str
    invocation: str
    reviewed_commit: str
    baseline: str
    status: str
    findings: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    disposition: str
    fix: str
    evidence: str
    tracking: str
    source: str = ""
    summary: str = ""


@dataclass(frozen=True)
class Verdict:
    status: Status
    blocking: tuple[str, ...]
    gaps: tuple[str, ...]
    reports: tuple[Report, ...]
    findings: tuple[Finding, ...]
    coverage: tuple[tuple[str, bool], ...]


# --- git ---------------------------------------------------------------------------------------------------


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def resolve(root: Path, ref: str) -> str | None:
    out = git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.stdout.strip() if out.returncode == 0 else None


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return git(root, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def changed_paths(root: Path, start: str, end: str) -> tuple[str, ...]:
    out = git(root, "diff", "--name-only", "--no-renames", start, end).stdout
    return tuple(line for line in out.splitlines() if line)


def clean_tree(root: Path) -> bool:
    return git(root, "status", "--porcelain", "--untracked-files=normal").stdout.strip() == ""


def report_only(path: str) -> bool:
    return path.startswith(REPORT_ONLY)


def same_source(root: Path, start: str, end: str) -> bool:
    """`end` is `start`, or descends from it through report-only changes."""
    return start == end or (
        is_ancestor(root, start, end) and all(report_only(p) for p in changed_paths(root, start, end))
    )


# --- gates -------------------------------------------------------------------------------------------------


def matches(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def required_gates(paths: Sequence[str]) -> tuple[Gate, ...]:
    e2e = [p for p in paths if matches(p, E2E_PATHS)]
    smoke = [p for p in paths if matches(p, SMOKE_PATHS)]
    gates = [Gate("pnpm check", ("pnpm", "check"), (), "always")]
    if e2e:
        gates.append(Gate("pnpm e2e", ("pnpm", "e2e"), (), f"browser-facing paths changed, e.g. {e2e[0]}"))
    if smoke:
        env = (("SMOKE_E2E", "1"),) if e2e else ()
        name = "SMOKE_E2E=1 pnpm docker:smoke" if e2e else "pnpm docker:smoke"
        gates.append(Gate(name, ("pnpm", "docker:smoke"), env, f"container inputs changed, e.g. {smoke[0]}"))
    return tuple(gates)


SUMMARY = re.compile(
    r"\d+ passed|Tests\s+\d+|Tasks:\s+\d+|Contract and generated|docs check:|container smoke test passed|FAIL"
)


def run_gates(root: Path, gates: Sequence[Gate], log_dir: Path) -> tuple[GateResult, ...]:
    """Runs gates in order and stops at the first failure; later gates are reported as not run."""
    results: list[GateResult] = []
    for gate in gates:
        log = log_dir / (re.sub(r"\W+", "-", gate.name).strip("-") + ".log")
        print(f"== {gate.name} (log: {log})", flush=True)
        with log.open("w") as out:
            code = subprocess.run(
                gate.command, cwd=root, env={**os.environ, **dict(gate.env)}, stdout=out, stderr=subprocess.STDOUT
            ).returncode
        lines = [line.strip() for line in log.read_text(errors="replace").splitlines() if SUMMARY.search(line)]
        detail = f"exit {code}; " + " | ".join(dict.fromkeys(lines[-6:])) if lines else f"exit {code}"
        results.append(GateResult(gate, code == 0, detail))
        if code != 0:
            break
    return tuple(results)


# --- evidence ----------------------------------------------------------------------------------------------


EVIDENCE_FIELDS = ("reviewer", "tool", "model", "invocation", "reviewed_commit", "baseline", "status", "findings")


def format_evidence(fields: Mapping[str, str]) -> str:
    """The fenced evidence block a review report carries; `evidence_block` parses it back."""
    return "```\n" + "".join(f"{key}: {fields[key]}\n" for key in EVIDENCE_FIELDS) + "```"


def evidence_block(text: str) -> Mapping[str, str]:
    """The `key: value` lines of the first fenced block that has a `reviewer:` line."""
    for block in re.findall(r"^```[^\n]*\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL):
        matches = (re.match(r"^\s*([a-z_]+):\s*(.*)$", line) for line in str(block).splitlines())
        fields = {m.group(1): m.group(2).strip() for m in matches if m}
        if "reviewer" in fields:
            return fields
    return {}


def parse_report(root: Path, path: Path) -> tuple[Report | None, tuple[str, ...]]:
    fields = evidence_block(path.read_text(encoding="utf-8"))
    if not fields:
        return None, ()
    name = path.relative_to(root).as_posix()
    problems: list[str] = []
    status = fields.get("status", "")
    if not all(fields.get(key, "").strip() for key in PROVENANCE):
        problems.append(f"{name}: tool, model, and invocation are required; such a report does not count")
    if status not in REPORT_STATUSES:
        problems.append(f"{name}: status must be one of {', '.join(REPORT_STATUSES)}")
    commits: dict[str, str] = {}
    for key in ("reviewed_commit", "baseline"):
        sha = resolve(root, fields.get(key, "")) if SHA.fullmatch(fields.get(key, "")) else None
        if sha is None:
            problems.append(f"{name}: {key} must be a commit SHA in this repository")
        commits[key] = sha or ""
    raw = fields.get("findings", "").strip()
    if not raw:
        problems.append(f"{name}: findings must list register IDs, or say none")
    found = () if raw.lower() in {"", "none"} else tuple(f.strip() for f in raw.split(",") if f.strip())
    report = Report(
        path=name,
        reviewer=fields.get("reviewer", ""),
        tool=fields.get("tool", "").strip(),
        model=fields.get("model", "").strip(),
        invocation=fields.get("invocation", "").strip(),
        reviewed_commit=commits["reviewed_commit"],
        baseline=commits["baseline"],
        status=status,
        findings=found,
    )
    return report, tuple(problems)


def linked_reports(root: Path, register: Path, text: str) -> tuple[tuple[Report, tuple[str, ...]], ...]:
    """The review reports that a findings register links to, in link order, each with its problems."""
    found: list[tuple[Report, tuple[str, ...]]] = []
    for target in dict.fromkeys(LINK.findall(text)):
        path = (register.parent / target).resolve()
        if path.is_file() and path.suffix == ".md" and path.is_relative_to(root):
            report, problems = parse_report(root, path)
            if report:
                found.append((report, problems))
    return tuple(found)


def parse_findings(text: str) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
    """The rows of the first table whose header has ID and Disposition columns."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        header = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if "id" not in header or "disposition" not in header:
            continue
        rows: list[Finding] = []
        problems: list[str] = []
        for row in lines[index + 2 :]:
            if not row.strip().startswith("|"):
                break
            cells = [c.strip().replace("`", "") for c in row.strip().strip("|").split("|")]
            if len(cells) != len(header):
                problems.append(f"register row has {len(cells)} cells, header has {len(header)}: {row.strip()}")
                continue
            cell = dict(zip(header, cells, strict=True))
            rows.append(
                Finding(
                    id=cell.get("id", ""),
                    severity=cell.get("severity", ""),
                    disposition=cell.get("disposition", "").lower(),
                    fix=cell.get("fix", ""),
                    evidence=cell.get("evidence", ""),
                    tracking=cell.get("tracking", ""),
                    source=cell.get("source", ""),
                    summary=cell.get("finding", ""),
                )
            )
        return tuple(rows), tuple(problems)
    return (), ("the register has no findings table with ID and Disposition columns",)


def touches_source(root: Path, commit: str) -> bool:
    """The commit changes something other than review records."""
    out = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout
    return any(not report_only(path) for path in out.splitlines() if path)


def disposition_problems(
    root: Path, register: Path, base: str, candidate: str, finding: Finding, reports: Sequence[Report]
) -> tuple[str, ...]:
    label = f"finding {finding.id or '(no id)'}"
    if finding.disposition not in DISPOSITIONS:
        return (f"{label}: disposition {finding.disposition!r} is not one of {', '.join(DISPOSITIONS)}",)
    if finding.disposition == "open":
        return (f"{label} is open",)
    problems: list[str] = []
    if not finding.evidence:
        problems.append(f"{label} is {finding.disposition} without evidence")
    if finding.disposition == "fixed":
        shas = [resolve(root, s) for s in SHA.findall(finding.fix)]
        on_branch = [
            s for s in shas if s and s != base and is_ancestor(root, base, s) and is_ancestor(root, s, candidate)
        ]
        raisers = [r for r in reports if finding.id in r.findings and r.reviewed_commit]
        if not shas or len(on_branch) != len(shas):
            problems.append(f"{label} is fixed, but its fix column names no commit between the base and the candidate")
        elif not any(touches_source(root, s) for s in on_branch):
            problems.append(f"{label} is fixed, but its fix commit changes only review records")
        elif any(
            not any(s != r.reviewed_commit and is_ancestor(root, r.reviewed_commit, s) for s in on_branch)
            for r in raisers
        ):
            problems.append(f"{label} is fixed, but no commit in its fix column comes after the review that raised it")
    if finding.disposition == "deferred":
        targets = LINK.findall(finding.tracking) or re.findall(r"[\w./-]+\.md", finding.tracking)
        documents = [d for t in targets for d in (register.parent / t, root / t) if d.is_file()]
        if not documents:
            problems.append(f"{label} is deferred without an existing tracking document")
        elif not any(re.search(rf"\b{re.escape(finding.id)}\b", d.read_text(encoding="utf-8")) for d in documents):
            problems.append(f"{label} is deferred, but its tracking document does not mention {finding.id}")
    return tuple(problems)


def covers(root: Path, reports: Sequence[Report], base: str, candidate: str) -> bool:
    """A chain of complete reports leads from the base to a commit with the candidate's source."""
    complete = [
        r
        for r in reports
        if r.status == "complete" and r.reviewed_commit and r.baseline and r.tool and r.model and r.invocation
    ]
    reached: set[str] = set()
    frontier = [base]
    while frontier:
        current = frontier.pop()
        for report in complete:
            end = report.reviewed_commit
            if end in reached or end == current or not is_ancestor(root, end, candidate):
                continue
            # The report's diff includes current..end: it starts at current (or at a report-only descendant of
            # it), or it starts earlier and passes through current.
            starts_here = same_source(root, current, report.baseline) and is_ancestor(root, report.baseline, end)
            passes_through = is_ancestor(root, report.baseline, current) and is_ancestor(root, current, end)
            if starts_here or passes_through:
                if same_source(root, end, candidate):
                    return True
                reached.add(end)
                frontier.append(end)
    return False


def evaluate(
    root: Path,
    base: str,
    candidate: str,
    register: Path,
    extra_reviewers: Sequence[str],
    gates: Sequence[Gate],
    results: Sequence[GateResult] | None,
) -> Verdict:
    """`extra_reviewers` adds to DEFAULT_REVIEWERS, which are always required."""
    reviewers = tuple(dict.fromkeys((*DEFAULT_REVIEWERS, *(r for r in extra_reviewers if r))))
    blocking: list[str] = []
    gaps: list[str] = []
    if not clean_tree(root):
        gaps.append("the working tree has uncommitted changes, so HEAD is not the whole candidate")
    if not is_ancestor(root, base, candidate):
        gaps.append(f"the base {base[:12]} is not an ancestor of the candidate {candidate[:12]}")

    if results is None:
        gaps.append("gates were not run (skipped, or the tree is not clean)")
    else:
        ran = {r.gate.name for r in results}
        blocking.extend(f"gate failed: {r.gate.name} ({r.detail})" for r in results if not r.passed)
        if not blocking:
            gaps.extend(f"gate not run: {g.name}" for g in gates if g.name not in ran)

    findings: tuple[Finding, ...] = ()
    reports: list[Report] = []
    if not register.is_file():
        gaps.append(f"no findings register at {register}")
    else:
        text = register.read_text(encoding="utf-8")
        findings, table_problems = parse_findings(text)
        blocking.extend(table_problems)
        ids = [f.id for f in findings]
        blocking.extend(f"finding ID {i} appears more than once" for i in sorted({i for i in ids if ids.count(i) > 1}))
        for report, problems in linked_reports(root, register, text):
            reports.append(report)
            gaps.extend(problems)
        for report in reports:
            gaps.extend(
                f"{report.path} lists finding {i}, which is not in the register"
                for i in report.findings
                if i not in ids
            )
        for finding in findings:
            blocking.extend(disposition_problems(root, register, base, candidate, finding, reports))

    coverage: list[tuple[str, bool]] = []
    for reviewer in reviewers:
        own = [r for r in reports if r.reviewer == reviewer]
        ok = covers(root, own, base, candidate)
        coverage.append((reviewer, ok))
        if ok:
            continue
        if not own:
            gaps.append(f"no report from required reviewer {reviewer}")
        elif all(r.status != "complete" for r in own):
            states = ", ".join(sorted({r.status for r in own}))
            gaps.append(f"required reviewer {reviewer} has no complete report ({states})")
        else:
            gaps.append(f"{reviewer}'s complete reports do not cover {base[:12]}..{candidate[:12]}")

    status: Status = "NOT READY" if blocking else "INCOMPLETE" if gaps else "READY"
    return Verdict(status, tuple(blocking), tuple(gaps), tuple(reports), findings, tuple(coverage))


# --- output ------------------------------------------------------------------------------------------------


def render(
    verdict: Verdict, base: str, candidate: str, gates: Sequence[Gate], results: Sequence[GateResult] | None
) -> str:
    by_gate = {r.gate.name: r for r in results or ()}
    deferred = [f for f in verdict.findings if f.disposition == "deferred"]
    title = verdict.status
    if deferred:
        title += f", with {len(deferred)} deferred finding{'s' if len(deferred) != 1 else ''} not fixed"
    lines = [
        f"# Readiness: {title}",
        "",
        f"Candidate `{candidate}` · base `{base}` · checked {datetime.now(UTC):%Y-%m-%dT%H:%MZ}",
        "",
        "## Gates",
        "",
        "| Gate | Required because | Result |",
        "| --- | --- | --- |",
    ]
    for gate in gates:
        result = by_gate.get(gate.name)
        outcome = "not run" if result is None else ("pass" if result.passed else "FAIL") + f": {result.detail}"
        outcome = outcome.replace("|", "\\|")  # a gate's summary may contain pipes; keep it one table cell
        lines.append(f"| `{gate.name}` | {gate.reason} | {outcome} |")
    lines += ["", "## Reviews", "", "| Reviewer | Reports (baseline → reviewed, status) | Covers the candidate |"]
    lines.append("| --- | --- | --- |")
    for reviewer, ok in verdict.coverage:
        own = [r for r in verdict.reports if r.reviewer == reviewer]
        chain = "; ".join(f"{r.baseline[:7]}→{r.reviewed_commit[:7]} {r.status} ({r.path})" for r in own) or "none"
        lines.append(f"| {reviewer} | {chain} | {'yes' if ok else 'NO'} |")
    counts = {d: sum(1 for f in verdict.findings if f.disposition == d) for d in DISPOSITIONS}
    lines += ["", "## Findings", "", ", ".join(f"{n} {d}" for d, n in counts.items()) or "none"]
    if deferred:
        lines += ["", "Deferred, not fixed:"]
        for f in deferred:
            if f.severity.lower() in SERIOUS:
                lines.append(
                    f"- {f.id} ({f.severity}) needs the owner's acceptance; this check verifies only that the"
                    f" tracking document names it: {f.tracking}"
                )
            else:
                lines.append(f"- {f.id} ({f.severity}): {f.tracking}")
    if verdict.blocking or verdict.gaps:
        lines += ["", "## Reasons", ""] + [f"- NOT READY: {b}" for b in verdict.blocking]
        lines += [f"- INCOMPLETE: {g}" for g in verdict.gaps]
    lines += [
        "",
        "## Not established by this check",
        "",
        "- GitHub CI: this script runs the same gates locally; a hosted run is evidence only once observed.",
        "- Live-model behavior: the gates use fixtures and stubbed providers.",
        "- Whether each disposition is right: that is the reviewers' and the owner's judgment.",
        "- Who reviewed: report contents, their provenance fields, and the commits they claim are taken as declared;"
        " nothing here authenticates them. Check the named session or thread when it matters.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, runner: Callable[..., tuple[GateResult, ...]] = run_gates) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--base", required=True, help="the commit the branch is reviewed against")
    parser.add_argument("--register", help="the findings register, normally .reviews/<run>/findings.md")
    parser.add_argument(
        "--also-require",
        default="",
        help=f"comma-separated reviewers to require in addition to {', '.join(DEFAULT_REVIEWERS)}",
    )
    parser.add_argument("--plan", action="store_true", help="print the required gates and exit")
    parser.add_argument("--skip-gates", action="store_true", help="check evidence only; the result is never READY")
    parser.add_argument("--out", help="also write the report to this file")
    args = parser.parse_args(argv)

    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    base, candidate = resolve(root, args.base), resolve(root, "HEAD")
    if base is None or candidate is None:
        print(f"cannot resolve the base {args.base!r} or HEAD", file=sys.stderr)
        return 2
    gates = required_gates(changed_paths(root, base, candidate))
    if args.plan:
        for gate in gates:
            print(f"{gate.name}\t{gate.reason}")
        return 0
    if not args.register:
        parser.error("--register is required unless --plan is given")

    results: tuple[GateResult, ...] | None = None
    if not args.skip_gates and clean_tree(root):
        results = runner(root, gates, Path(tempfile.mkdtemp(prefix="readiness-")))
    extra = tuple(r.strip() for r in args.also_require.split(",") if r.strip())
    verdict = evaluate(root, base, candidate, (root / args.register).resolve(), extra, gates, results)
    text = render(verdict, base, candidate, gates, results)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if verdict.status == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
