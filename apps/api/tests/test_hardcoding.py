"""Application code must not know the fixture scenarios. The check is two-sided, so it cannot pass
vacuously: every term is also required to appear in the fixture data."""

import re
from pathlib import Path

from tests.support import FIXTURES

TERMS = ["restaurant", "shift manager", "incident", "migration guide", "changelog", "Button and Input", "owner"]
SOURCE = Path(__file__).resolve().parents[1] / "src" / "intent_harness"


def test_application_code_contains_no_fixture_terms() -> None:
    pattern = re.compile("|".join(map(re.escape, TERMS)), re.IGNORECASE)
    offenders = [str(p) for p in SOURCE.rglob("*.py") if pattern.search(p.read_text())]
    assert offenders == []


def test_every_term_appears_in_the_fixture_data() -> None:
    data = (FIXTURES / "journeys.json").read_text().lower()
    assert [t for t in TERMS if t.lower() not in data] == []
