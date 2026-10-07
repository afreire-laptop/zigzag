"""Derived facts about the append-only decision history."""

from dataclasses import dataclass

from intent_harness.domain.model import Project


@dataclass(frozen=True)
class LaterChange:
    item_id: str
    item_text: str
    by: str


def later_status_changes(p: Project, index: int) -> tuple[LaterChange, ...]:
    """Status parts of decision `index` that a later decision replaced, such as a question that a reply
    left open and the user later answered. A part is current only while the item still points to this
    decision; the first later decision that changed the same item is the one that replaced it."""
    d = p.decisions[index]
    later = p.decisions[index + 1 :]
    changes: list[LaterChange] = []
    for sc in d.status_changes:
        item = p.item(sc.item_id)
        if item is None or item.decision_id == d.id:
            continue
        by = next((x.id for x in later if any(s.item_id == sc.item_id for s in x.status_changes)), None)
        if by is not None:
            changes.append(LaterChange(sc.item_id, item.text, by))
    return tuple(changes)
