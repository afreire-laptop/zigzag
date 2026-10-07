"""One handoff object per saved revision. Markdown and JSON are both rendered from it, so the two exports
cannot disagree about content, revision, or review status. Format: `intent-harness.handoff/v0`."""

import json
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from pydantic import TypeAdapter

from intent_harness.domain.history import later_status_changes
from intent_harness.domain.model import (
    INTENT_KINDS,
    INTENT_LABELS,
    IntentItem,
    OptionSource,
    Project,
    superseded_by,
)

HANDOFF_FORMAT = "intent-harness.handoff/v0"
REVIEWER = "local user"


class HandoffItem(TypedDict):
    id: str
    text: str
    basis: str


class HandoffSection(TypedDict):
    kind: str
    label: str
    items: list[HandoffItem]


class HandoffQuestion(TypedDict):
    id: str
    text: str
    status: Literal["open", "deferred"]
    effect: str
    deferEffect: str | None
    optionsConsidered: list[str]
    basis: str


class HandoffAssumption(TypedDict):
    id: str
    text: str
    support: Literal["untested"]
    basis: str
    reliance: Literal["accepted for the next step", "not accepted"]


class HandoffNeeded(TypedDict):
    id: str
    text: str
    basis: str
    effect: str


class PartlySuperseded(TypedDict):
    itemId: str
    itemText: str
    by: str


class HandoffDecision(TypedDict):
    id: str
    at: str
    action: str
    summary: str
    reason: str | None
    sourceWording: str | None
    supersededBy: str | None
    # Present only when a later decision replaced part of this one, such as a question it left open.
    partlySupersededBy: NotRequired[list[PartlySuperseded]]


class HandoffSource(TypedDict):
    id: str
    kind: str
    at: str
    interpretedBy: str
    text: str


class Handoff(TypedDict):
    format: str
    projectId: str
    title: str
    revision: int
    status: Literal["draft", "reviewed"]
    reviewedAt: str | None
    reviewer: str | None
    intent: list[HandoffSection]
    openQuestions: list[HandoffQuestion]
    assumptions: list[HandoffAssumption]
    neededLater: list[HandoffNeeded]
    decisions: list[HandoffDecision]
    sources: list[HandoffSource]


def describe_source(p: Project, item: IntentItem) -> str:
    """How a statement came to be current, in the words shown to the user and the downstream reader."""
    decision = p.decision(item.decision_id)
    corrected = f"Corrected by you ({decision.id}). Originally " if decision and decision.action == "edit" else ""
    if isinstance(item.source, OptionSource):
        q = p.question(item.source.question_id)
        option = next((o for o in q.options if o.id == item.source.option_id), None) if q else None
        label = option.label if option else item.source.option_id
        return f"{corrected}{'selected' if corrected else 'Selected'} by you from proposed options: “{label}”"
    source_input = p.input(item.source.input_id)
    where = "your reply" if source_input and source_input.kind == "reply" else "your brief"
    return f"{corrected}{'from' if corrected else 'From'} {where}: “{item.source.quote}”"


def _decision_entry(p: Project, index: int) -> HandoffDecision:
    d = p.decisions[index]
    source_input = p.input(d.input_id) if d.input_id else None
    entry: HandoffDecision = {
        "id": d.id,
        "at": d.at,
        "action": d.action,
        "summary": d.summary,
        "reason": d.reason,
        "sourceWording": source_input.text if source_input else None,
        "supersededBy": superseded_by(p, d.id),
    }
    later = later_status_changes(p, index) if entry["supersededBy"] is None else ()
    if later:
        entry["partlySupersededBy"] = [{"itemId": c.item_id, "itemText": c.item_text, "by": c.by} for c in later]
    return entry


def build_handoff(p: Project, *, review_at: str | None) -> Handoff:
    return {
        "format": HANDOFF_FORMAT,
        "projectId": p.id,
        "title": p.title,
        "revision": p.revision,
        "status": "reviewed" if review_at else "draft",
        "reviewedAt": review_at,
        "reviewer": REVIEWER if review_at else None,
        "intent": [
            {
                "kind": kind,
                "label": INTENT_LABELS[kind],
                "items": [
                    {"id": i.id, "text": i.text, "basis": describe_source(p, i)} for i in p.intent if i.kind == kind
                ],
            }
            for kind in INTENT_KINDS
        ],
        "openQuestions": [
            {
                "id": o.id,
                "text": o.text,
                "status": "deferred" if o.status == "deferred" else "open",
                "effect": o.effect,
                "deferEffect": o.defer_effect,
                "optionsConsidered": [x.label for x in o.options],
                "basis": o.basis,
            }
            for o in p.open_items
            if o.kind == "question" and o.status in ("open", "deferred")
        ],
        "assumptions": [
            {
                "id": o.id,
                "text": o.text,
                "support": "untested",
                "basis": o.basis,
                "reliance": "accepted for the next step" if o.status == "relied" else "not accepted",
            }
            for o in p.open_items
            if o.kind == "assumption"
        ],
        "neededLater": [
            {"id": o.id, "text": o.text, "basis": o.basis, "effect": o.effect}
            for o in p.open_items
            if o.kind == "needed"
        ],
        "decisions": [_decision_entry(p, n) for n in range(len(p.decisions))],
        "sources": [
            {"id": i.id, "kind": i.kind, "at": i.at, "interpretedBy": i.interpreted_by, "text": i.text}
            for i in p.inputs
        ],
    }


def _day(iso: str) -> str:
    return iso.replace("T", " ", 1)[:16] + " UTC"


def _quote_block(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.split("\n"))


def status_line(h: Handoff) -> str:
    if h["status"] == "reviewed" and h["reviewedAt"] is not None:
        return f"Reviewed. Revision {h['revision']}, reviewed {_day(h['reviewedAt'])} by {h['reviewer']}."
    return f"DRAFT. Revision {h['revision']} has not been reviewed."


def render_markdown(h: Handoff) -> str:
    out: list[str] = [f"# Intent handoff: {h['title']}", "", f"**Status: {status_line(h)}**", ""]
    if h["status"] == "draft":
        out += ["_This draft may change. Do not treat it as reviewed direction._", ""]

    for section in h["intent"]:
        out += [f"## {section['label']}", ""]
        if not section["items"]:
            out.append("- Not established.")
        for item in section["items"]:
            out += [f"- {item['text']}  ", f"  _{item['basis']}_"]
        out.append("")

    out += ["## Open questions", ""]
    if not h["openQuestions"]:
        out.append("- None recorded.")
    for q in h["openQuestions"]:
        state = "left open by you" if q["status"] == "deferred" else "not yet answered"
        out.append(f"- **{q['text']}** ({state})  ")
        out.append(f"  What it changes: {q['effect']}  ")
        if q["optionsConsidered"]:
            out.append(f"  Options proposed, none selected: {'; '.join(q['optionsConsidered'])}  ")
        if q["deferEffect"]:
            out.append(f"  While open: {q['deferEffect']}  ")
        out.append(f"  _Basis: {q['basis']}_")
    out.append("")

    out += ["## Assumptions (untested)", ""]
    if not h["assumptions"]:
        out.append("- None recorded.")
    for a in h["assumptions"]:
        out += [f"- {a['text']}  ", f"  _Support: untested. {a['basis']} Reliance: {a['reliance']}._"]
    out.append("")

    out += ["## Needed later", ""]
    if not h["neededLater"]:
        out.append("- None recorded.")
    for n in h["neededLater"]:
        out += [f"- {n['text']}  ", f"  _{n['effect']} Basis: {n['basis']}_"]
    out.append("")

    out += ["## Decisions", ""]
    if not h["decisions"]:
        out.append("- None recorded.")
    for d in h["decisions"]:
        superseded = f" _(superseded by {d['supersededBy']})_" if d["supersededBy"] else ""
        parts = d.get("partlySupersededBy", [])
        if parts:
            changed = "; ".join(f"“{c['itemText']}” by {c['by']}" for c in parts)
            superseded += f" _(partly superseded: {changed})_"
        out.append(f"- {d['id']} · {_day(d['at'])} · {d['summary']}{superseded}  ")
        out.append(
            "  In your own words; see Sources." if d["sourceWording"] else f"  Reason: {d['reason'] or 'not given'}"
        )
    out.append("")

    out += ["## Sources", ""]
    for s in h["sources"]:
        label = "Brief" if s["kind"] == "brief" else "Reply"
        out += [f"### {label} {s['id']} · {_day(s['at'])} · read by {s['interpretedBy']}", ""]
        out += [_quote_block(s["text"]), ""]
    out += ["---", "", f"_{HANDOFF_FORMAT} · project {h['projectId']} · {status_line(h)}_", ""]
    return "\n".join(out)


HANDOFF_ADAPTER: TypeAdapter[Handoff] = TypeAdapter(Handoff)


def render_json(h: Handoff) -> str:
    return json.dumps(h, indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Exports:
    revision: int
    status: Literal["draft", "reviewed"]
    markdown: str
    json: str


def render_exports(p: Project, *, review_at: str | None) -> Exports:
    h = build_handoff(p, review_at=review_at)
    return Exports(p.revision, h["status"], render_markdown(h), render_json(h))


def current_exports(p: Project) -> Exports:
    """The fixed reviewed copy when this revision is reviewed, otherwise a labeled draft."""
    reviewed = next((r for r in p.reviews if r.revision == p.revision), None)
    if reviewed:
        return Exports(p.revision, "reviewed", reviewed.markdown, reviewed.json_copy)
    return render_exports(p, review_at=None)


@dataclass(frozen=True)
class HandoffChange:
    section: str
    added: tuple[str, ...]
    removed: tuple[str, ...]


def _lines(h: Handoff) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {s["label"]: [i["text"] for i in s["items"]] for s in h["intent"]}
    sections["Open questions"] = [
        f"{q['text']} ({'left open' if q['status'] == 'deferred' else 'not yet answered'})" for q in h["openQuestions"]
    ]
    sections["Assumptions"] = [f"{a['text']} ({a['reliance']})" for a in h["assumptions"]]
    sections["Needed later"] = [n["text"] for n in h["neededLater"]]
    sections["Decisions"] = [
        d["summary"]
        + (" (superseded)" if d["supersededBy"] else " (partly superseded)" if d.get("partlySupersededBy") else "")
        for d in h["decisions"]
    ]
    return sections


def diff_handoffs(previous: Handoff, current: Handoff) -> tuple[HandoffChange, ...]:
    """What the reader would see differently compared with the last reviewed copy."""
    before = _lines(previous)
    changes: list[HandoffChange] = []
    for section, items in _lines(current).items():
        old = before.get(section, [])
        added = tuple(x for x in items if x not in old)
        removed = tuple(x for x in old if x not in items)
        if added or removed:
            changes.append(HandoffChange(section, added, removed))
    return tuple(changes)
