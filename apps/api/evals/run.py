"""Live evaluation runner. Separate from the deterministic gates; it never runs in CI.

    uv run python -m evals.run --budget-usd 2.00 --max-calls 40 --repeats 2 [--cases short-reply,clear-brief]

It needs INTENT_MODEL_MODE=live with INTENT_OPENROUTER_API_KEY and INTENT_MODEL, and refuses to start without a
spending budget. Every request submitted counts against the budget, including automatic retries; a request whose
cost is unknown, such as one that timed out after it was sent, stops the run. Every case runs through the same
validation and transitions as the app. Results go to observations/ (git-ignored): raw responses, schema validity,
mechanical checks, latency, cost, and failures, plus a Markdown summary with an empty column for the human verdict.
Record judged results in docs/evaluations/live-model-observations.md; only reviewed, sanitized evidence is committed."""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from evals.cases import CASES, Case, base_state
from intent_harness.adapters.model.openrouter import OpenRouterClient
from intent_harness.application.assessment import PROMPT_VERSION, LiveAssessor
from intent_harness.application.ports import Assessor, AssessRequest, CallAttempt, ModelCallError, known_cost
from intent_harness.config import ConfigError, load_config
from intent_harness.domain.model import Project
from intent_harness.domain.proposal import Invalid, ProposalContext, Valid, validate_proposal
from intent_harness.domain.transitions import apply_reassessment, apply_user_text, create_project

AT = "2026-10-06T12:00:00.000Z"


@dataclass
class Attempt:
    case: str
    repeat: int
    status: str  # valid | invalid | error | blocked | skipped-budget
    seconds: float = 0.0
    requests: int = 0  # submitted to the model, automatic retries included
    cost: float | None = None  # None when any request's cost is unknown
    served_model: str | None = None
    provider: str | None = None
    issues: list[str] = field(default_factory=list[str])
    notes: list[str] = field(default_factory=list[str])
    checks: dict[str, bool] = field(default_factory=dict[str, bool])
    error: str | None = None
    raw: str | None = None
    blocked_by: str | None = None


class Budget:
    """Stops before spending beyond the limit. Every submitted request counts as a call. A request whose cost is
    unknown stops the run, including one that may have been processed without an answer: the budget can no
    longer be enforced honestly."""

    def __init__(self, usd: float, max_calls: int) -> None:
        self.usd, self.max_calls = usd, max_calls
        self.spent, self.calls, self.unknown_cost = 0.0, 0, False

    def allows(self) -> bool:
        return not self.unknown_cost and self.calls < self.max_calls and self.spent < self.usd

    def record(self, attempts: Sequence[CallAttempt]) -> None:
        self.calls += len(attempts)
        cost = known_cost(attempts)
        if cost is None:
            self.unknown_cost = True
        else:
            self.spent += cost


def _request(case: Case, project: Project | None) -> tuple[AssessRequest, ProposalContext]:
    if case.mode == "brief":
        return AssessRequest(mode="brief", project=None, text=case.text), ProposalContext("brief", case.text, None)
    assert project is not None
    if case.mode == "reply":
        target = project.focus_id
        return (
            AssessRequest(mode="reply", project=project, text=case.text, question_id=target),
            ProposalContext("reply", case.text, project, target),
        )
    event = project.decisions[-1].summary
    return AssessRequest(mode="reassess", project=project, event=event), ProposalContext("reassess", None, project)


def _apply(case: Case, project: Project | None, valid: Valid, served: str) -> Project:
    if case.mode == "brief":
        assert case.text is not None
        return create_project(project_id="eval", at=AT, brief=case.text, proposal=valid.proposal, interpreted_by=served)
    assert project is not None
    if case.mode == "reply":
        assert case.text is not None
        return apply_user_text(
            project,
            at=AT,
            kind="reply",
            text=case.text,
            question_id=project.focus_id,
            proposal=valid.proposal,
            interpreted_by=served,
        )
    return apply_reassessment(project, at=AT, proposal=valid.proposal, proposed_by=served)


async def run_case(case: Case, repeat: int, assessor: Assessor, budget: Budget, results: dict[str, Project]) -> Attempt:
    project: Project | None = None
    if case.base and case.base.startswith("case:"):
        dependency = case.base.removeprefix("case:")
        project = results.get(dependency)
        if project is None:
            return Attempt(case.id, repeat, "blocked", blocked_by=dependency)
    elif case.base:
        project = base_state(case.base)
    if not budget.allows():
        return Attempt(case.id, repeat, "skipped-budget")
    request, ctx = _request(case, project)
    started = time.monotonic()
    requests: list[CallAttempt] = []
    try:
        reply = await assessor.assess(request, requests)
    except ModelCallError as e:
        budget.record(requests)
        return Attempt(
            case.id,
            repeat,
            "error",
            seconds=time.monotonic() - started,
            requests=len(requests),
            cost=known_cost(requests),
            error=f"{e.kind}: {e.message}",
        )
    seconds = time.monotonic() - started
    budget.record(requests)
    attempt = Attempt(
        case.id,
        repeat,
        "invalid",
        seconds=round(seconds, 2),
        requests=len(requests),
        cost=known_cost(requests),
        served_model=reply.served_model,
        provider=reply.provider,
        raw=reply.raw,
    )
    result = validate_proposal(reply.raw, ctx)
    if isinstance(result, Invalid):
        attempt.issues = list(result.issues)
        return attempt
    after = _apply(case, project, result, reply.interpreted_by)
    attempt.status, attempt.notes = "valid", list(result.notes)
    attempt.checks = {name: check(result.proposal, after) for name, check in case.checks.items()}
    results.setdefault(case.id, after)
    return attempt


async def run(cases: Sequence[Case], assessor: Assessor, budget: Budget, repeats: int) -> list[Attempt]:
    attempts: list[Attempt] = []
    results: dict[str, Project] = {}
    ordered = sorted(cases, key=lambda c: bool(c.base and c.base.startswith("case:")))  # dependencies first
    for repeat in range(1, repeats + 1):
        for case in ordered:  # sequential on purpose: one paid call at a time, within the budget
            attempt = await run_case(case, repeat, assessor, budget, results)
            attempts.append(attempt)
    return attempts


def summarize(attempts: Sequence[Attempt], cases: Sequence[Case], *, model: str, budget: Budget) -> str:
    lines = [
        f"# Evaluation summary: {model} (prompt {PROMPT_VERSION})",
        "",
        f"Requests submitted: {budget.calls}. Reported cost: ${budget.spent:.4f}"
        + (
            " (incomplete: at least one request's cost is unknown, possibly one that was processed without an"
            " answer; the run stopped)."
            if budget.unknown_cost
            else "."
        ),
        "",
        "| Case | Valid / attempts | Mechanical checks passed | Median seconds | Failures | Human verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        mine = [a for a in attempts if a.case == case.id]
        ran = [a for a in mine if a.status in ("valid", "invalid", "error")]
        valid = [a for a in mine if a.status == "valid"]
        checks = [ok for a in valid for ok in a.checks.values()]
        seconds = statistics.median([a.seconds for a in ran]) if ran else None
        failures = [
            a.status if a.status != "blocked" else f"blocked by {a.blocked_by}" for a in mine if a.status != "valid"
        ]
        lines.append(
            f"| {case.id} | {len(valid)} / {len(ran)} | {sum(checks)} / {len(checks)} | "
            f"{'' if seconds is None else f'{seconds:.1f}'} | {', '.join(failures) or 'none'} | |"
        )
    lines += ["", "## What to judge", ""] + [f"- **{c.id}**: {c.judge}" for c in cases]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget-usd", type=float, required=True, help="Stop before reported spend exceeds this.")
    parser.add_argument(
        "--max-calls",
        type=int,
        required=True,
        help="Start no further case once this many requests were submitted, automatic retries included.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--cases", default="", help="Comma-separated case ids; all when empty.")
    parser.add_argument("--out", default="../../observations")
    given = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(given[1:] if given[:1] == ["--"] else given)  # pnpm forwards a literal "--"
    try:
        config = load_config(os.environ)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2
    if config.model_mode != "live" or config.openrouter_api_key is None or config.model is None:
        print(
            "Live evaluation needs INTENT_MODEL_MODE=live, INTENT_OPENROUTER_API_KEY, and INTENT_MODEL. "
            "Live verification not run.",
            file=sys.stderr,
        )
        return 2
    wanted = {c for c in args.cases.split(",") if c}
    cases = [c for c in CASES if not wanted or c.id in wanted]
    client = OpenRouterClient(
        api_key=config.openrouter_api_key.get_secret_value(),
        model=config.model,
        base_url=config.openrouter_base_url,
        reasoning_effort=config.reasoning_effort,
        attempt_timeout_seconds=config.attempt_timeout_seconds,
        max_attempts=config.max_attempts,
    )
    budget = Budget(args.budget_usd, args.max_calls)
    attempts = asyncio.run(
        run(cases, LiveAssessor(client, max_output_tokens=config.max_output_tokens), budget, args.repeats)
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = config.model.replace("/", "_")
    (out / f"{stamp}-{slug}.json").write_text(
        json.dumps(
            {"model": config.model, "prompt": PROMPT_VERSION, "attempts": [asdict(a) for a in attempts]}, indent=2
        )
    )
    summary = summarize(attempts, cases, model=config.model, budget=budget)
    (out / f"{stamp}-{slug}.md").write_text(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
