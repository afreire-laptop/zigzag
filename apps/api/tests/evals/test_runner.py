"""The evaluation runner, exercised with a scripted model: independent cases survive failures, dependencies
are reported as blocked, the budget is enforced, and the summary separates validity, checks, and judgment."""

import json

import pytest
from evals.cases import CASES, base_state
from evals.run import Budget, main, run, summarize

from intent_harness.application.ports import AssessRequest, CallAttempt, ModelCallError, ModelReply, Usage
from tests.support import canned

pytestmark = pytest.mark.anyio
EMPTY = json.dumps({"extracted": [], "resolutions": [], "newItems": [], "focus": None})


class Stub:
    """Answers the clear brief with its fixture reading, breaks the ambiguous brief, and otherwise proposes nothing."""

    def __init__(self, cost: float | None = 0.01) -> None:
        self.calls: list[AssessRequest] = []
        self.cost = cost

    @property
    def label(self) -> str:
        return "stub"

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply:
        self.calls.append(request)
        if request.text and request.text.startswith("Help independent restaurants"):
            raw = "{ broken"
        elif request.text and request.text.startswith("Frontend engineers"):
            raw = json.dumps(canned("clear brief"))
        elif request.text and request.text.startswith("Nurses lose time"):
            attempts.append(CallAttempt(1, "not-processed", http_status=503))
            raise ModelCallError("model-unavailable", "Gateway down.", retryable=True)
        else:
            raw = EMPTY
        attempts.append(CallAttempt(1, "answered", http_status=200, cost=self.cost))
        return ModelReply(
            raw=raw,
            interpreted_by="stub",
            requested_model="stub",
            served_model="stub-1",
            provider="StubCloud",
            usage=Usage(cost=self.cost),
        )


async def test_cases_run_independently_and_dependencies_are_blocked_not_dropped() -> None:
    stub = Stub()
    attempts = await run(CASES, stub, Budget(10.0, 100), repeats=2)
    by_case = {(a.case, a.repeat): a for a in attempts}
    assert len(attempts) == 2 * len(CASES)
    assert by_case[("ambiguous-brief", 1)].status == "invalid"
    assert by_case[("ambiguous-brief", 1)].issues == ["The response was not valid JSON."]
    assert by_case[("reply-to-live-brief", 1)].status == "blocked"
    assert by_case[("reply-to-live-brief", 1)].blocked_by == "ambiguous-brief"
    assert by_case[("negation-control", 1)].status == "error"
    clear = by_case[("clear-brief", 1)]
    assert clear.status == "valid"
    assert all(clear.checks.values())
    assert (clear.served_model, clear.provider, clear.cost) == ("stub-1", "StubCloud", 0.01)
    short = by_case[("short-reply", 2)]
    assert short.status == "valid"
    assert short.checks["answers the focus question"] is False  # the stub proposed nothing: a mechanical failure
    summary = summarize(attempts, CASES, model="stub-model", budget=Budget(10.0, 100))
    assert "| clear-brief | 2 / 2 | 8 / 8 |" in summary
    assert "blocked by ambiguous-brief" in summary
    assert summary.splitlines()[4].endswith("| Human verdict |")
    assert "## What to judge" in summary


async def test_the_budget_stops_the_run_and_unknown_cost_stops_it_early() -> None:
    statuses = [a.status for a in await run(CASES, Stub(cost=0.5), Budget(1.0, 100), repeats=1)]
    assert statuses[:2] == ["valid", "invalid"]  # $0.50 each: the third call would exceed $1.00
    assert statuses.count("blocked") == 1  # the chained case is blocked, not hidden among the skipped
    assert statuses.count("skipped-budget") == len(CASES) - 3
    unknown = Budget(10.0, 100)
    statuses = [a.status for a in await run(CASES, Stub(cost=None), unknown, repeats=1)]
    assert unknown.unknown_cost
    assert statuses.count("skipped-budget") == len(CASES) - 2
    capped = Budget(10.0, 3)
    await run(CASES, Stub(), capped, repeats=1)
    assert capped.calls == 3


class Gateway:
    """Records each call's scripted attempts, then answers or fails as the live client would."""

    def __init__(self, script: list[tuple[list[CallAttempt], str | ModelCallError]]) -> None:
        self.script = script

    @property
    def label(self) -> str:
        return "gateway"

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply:
        recorded, result = self.script.pop(0)
        attempts.extend(recorded)
        if isinstance(result, ModelCallError):
            raise result
        return ModelReply(raw=result, interpreted_by="gateway", requested_model="gateway")


async def test_every_request_counts_and_an_ambiguous_one_stops_the_run() -> None:
    gateway = Gateway(
        [
            ([CallAttempt(1, "not-processed", failure="ConnectError"), CallAttempt(2, "answered", cost=0.01)], EMPTY),
            (
                [CallAttempt(1, "ambiguous", failure="ReadTimeout")],
                ModelCallError("model-timeout", "No answer in time.", retryable=True),
            ),
        ]
    )
    budget = Budget(10.0, 100)
    attempts = await run(CASES, gateway, budget, repeats=1)
    assert (budget.calls, budget.spent, budget.unknown_cost) == (3, 0.01, True)
    assert (attempts[0].requests, attempts[0].cost) == (2, 0.01)
    assert (attempts[1].status, attempts[1].requests, attempts[1].cost) == ("error", 1, None)
    assert {a.status for a in attempts[2:]} <= {"skipped-budget", "blocked"}
    assert gateway.script == []  # nothing further was sent
    summary = summarize(attempts, CASES, model="gateway", budget=budget)
    assert "Requests submitted: 3." in summary
    assert "incomplete" in summary


def test_bases_cover_choice_and_deferral() -> None:
    assert base_state("ambiguous-selected").decisions[-1].action == "select"
    assert base_state("ambiguous-deferred").decisions[-1].action == "defer"


def test_the_runner_refuses_to_spend_without_live_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTENT_MODEL_MODE", raising=False)
    assert main(["--budget-usd", "1", "--max-calls", "1"]) == 2
    monkeypatch.setenv("INTENT_MODEL_MODE", "fixtur")
    assert main(["--budget-usd", "1", "--max-calls", "1"]) == 2
    with pytest.raises(SystemExit):
        main([])
