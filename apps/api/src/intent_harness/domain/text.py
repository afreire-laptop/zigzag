"""Text matching used to check that quoted wording really comes from the user, and that it reads as an
instruction rather than a hedge. These are mechanical signals; they do not establish faithful meaning."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

_QUOTES_SINGLE = re.compile("[\u2018\u2019\u02bc`]")
_QUOTES_DOUBLE = re.compile("[\u201c\u201d]")
_DASHES = re.compile("[\u2013\u2014]")
_SPACE = re.compile(r"\s+")
_EDGES = re.compile(r"^[\s\"'.,;:!?…-]+|[\s\"'.,;:!?…-]+$")


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = _QUOTES_SINGLE.sub("'", s)
    s = _QUOTES_DOUBLE.sub('"', s)
    s = _DASHES.sub("-", s)
    return _SPACE.sub(" ", s)


def normalize_for_match(s: str) -> str:
    """Tolerant comparison form: case, quote style, dash style, spacing, and edge punctuation ignored."""
    return _EDGES.sub("", _fold(s))


def quote_found(quote: str, text: str) -> bool:
    q = normalize_for_match(quote)
    return len(q) > 0 and q in normalize_for_match(text)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_TRAILING_WORD = re.compile(r"\s+\S*$")


def title_from(brief: str) -> str:
    first = _SENTENCE_END.split(brief.strip())[0]
    if len(first) <= 90:
        return first
    return f"{_TRAILING_WORD.sub('', first[:88])}…"


HedgeKind = Literal["uncertain", "conditional", "suggestion", "negated"]

_MARKERS: tuple[tuple[HedgeKind, re.Pattern[str]], ...] = (
    (
        "uncertain",
        re.compile(
            r"\b(not sure|unsure|uncertain|don'?t know|do not know|unclear|not clear|wonder(?:ing)?|"
            r"maybe|perhaps|possibly|might|could)\b"
        ),
    ),
    ("conditional", re.compile(r"\b(if|unless|in case|assuming|provided that|whether)\b")),
    (
        "suggestion",
        re.compile(
            r"\b(suggest(?:ion|ed)?|consider|what about|how about|one option|for example|for instance|"
            r"e\.g|should we|could we|would it)\b"
        ),
    ),
)
_NEGATION = re.compile(r"\b(not|no|never|without|don'?t|do not|doesn'?t|does not|isn'?t|won'?t|avoid)\b")
_CLAUSE_BREAK = re.compile(r"[.;!?\n]")
_LEAD_WORDS = 4


@dataclass(frozen=True)
class Hedge:
    kind: HedgeKind
    marker: str


def hedge_around(quote: str, text: str, *, negation_expected: bool) -> Hedge | None:
    """Whether the clause around a quote frames it as uncertain, conditional, a suggestion or question,
    or (unless `negation_expected`) negated. Looks at the clause up to the quote and its first words."""
    t = _fold(text)
    q = normalize_for_match(quote)
    at = t.find(q) if q else -1
    if at < 0:
        return None
    breaks = [m.end() for m in _CLAUSE_BREAK.finditer(t, 0, at)]
    before = t[breaks[-1] if breaks else 0 : at]
    lead = " ".join(q.split(" ")[:_LEAD_WORDS])
    window = f"{before} {lead}"
    for kind, pattern in _MARKERS:
        if found := pattern.search(window):
            return Hedge(kind, found.group(0))
    end = _CLAUSE_BREAK.search(t, at + len(q))
    if end and end.group(0) == "?":
        return Hedge("suggestion", "?")
    if not negation_expected and (found := _NEGATION.search(before)):
        return Hedge("negated", found.group(0))
    return None
