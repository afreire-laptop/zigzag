"""Enforce line and branch coverage separately, for the whole API and for the domain core.

coverage.py's `fail_under` checks one combined percentage, so this reads `coverage.json` instead.
Every module under src/intent_harness is measured, including any that tests never import."""

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "api": ("src/intent_harness/", 85.0, 80.0),
    "domain": ("src/intent_harness/domain/", 90.0, 90.0),
}


def main() -> int:
    files: dict[str, dict[str, dict[str, int]]] = json.loads(Path("coverage.json").read_text())["files"]
    source = sorted(str(p) for p in Path("src/intent_harness").rglob("*.py"))
    unmeasured = [p for p in source if p not in files]
    failed = False
    if unmeasured:
        print(f"Not measured at all: {', '.join(unmeasured)}")
        failed = True
    for name, (prefix, line_min, branch_min) in THRESHOLDS.items():
        summaries = [f["summary"] for path, f in files.items() if path.startswith(prefix)]
        statements = sum(s["num_statements"] for s in summaries)
        covered = sum(s["covered_lines"] for s in summaries)
        branches = sum(s["num_branches"] for s in summaries)
        covered_branches = sum(s["covered_branches"] for s in summaries)
        lines = 100.0 * covered / statements if statements else 100.0
        branch = 100.0 * covered_branches / branches if branches else 100.0
        ok = lines >= line_min and branch >= branch_min
        failed |= not ok
        print(
            f"{name:7} lines {lines:5.1f}% (min {line_min:.0f})  branches {branch:5.1f}% (min {branch_min:.0f})"
            f"  {'ok' if ok else 'BELOW THRESHOLD'}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
