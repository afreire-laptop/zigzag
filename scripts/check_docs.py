"""Checks that documentation, skills, and agent definitions stay consistent and portable.

Run from anywhere: `python3 scripts/check_docs.py`. Exits 1 and lists every problem found. It checks:

- relative Markdown links, and paths under docs/ mentioned in code or prose, resolve;
- every document under docs/ (except docs/README.md and the templates) has a `**Status:**` line;
- every template is listed in docs/README.md and has a `**Status:**` line;
- every skill in .agents/skills has valid frontmatter and is exposed to Claude Code by a relative symlink in
  .claude/skills that resolves inside the repository;
- skills, agents, and hooks contain no absolute machine paths;
- agents name an explicit model, and read-only reviewers have only read-only tools;
- raw review output under .reviews/ is neither tracked nor left un-ignored, so it cannot be committed by accident;
- run records in docs/records/ name no local path, session or thread id, or cost.
"""

import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
DOC_MENTION = re.compile(r"(?<![\w./-])(docs/[\w./-]+\.md)\b")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
ABSOLUTE_PATH = re.compile(r"(/Users/|/home/|/private/tmp|[A-Za-z]:\\\\)")
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STATUS = "**Status:**"
TEXT_SUFFIXES = {".md", ".py", ".ts", ".tsx", ".sh", ".yml", ".yaml", ".toml", ".cjs", ".json"}
SKIPPED_PREFIXES = ("packages/api-client/src/generated/", "fixtures/legacy-golden/", "scripts/tests/")
# Run records are public summaries. Raw review output, which names these, stays in the git-ignored .reviews/.
RECORD_PREFIX = "docs/records/"
RECORD_LEAKS = (
    ("a local path", re.compile(r"(/Users/|/home/|/private/tmp|~/|[A-Za-z]:\\\\)")),
    ("a session or thread id", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}")),
    ("a cost", re.compile(r"\$\s?\d")),
)
SKIPPED_FILES = {"pnpm-lock.yaml", "apps/api/uv.lock", "apps/api/openapi.json"}
READ_ONLY_AGENTS = {"spec-reviewer", "code-reviewer"}
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
PRIVATE_PREFIXES = (".reviews/",)


def tracked_files(root: Path) -> list[str]:
    """Tracked and new (not ignored) files, so a check before the first commit still sees them."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({line for line in out.splitlines() if line})


def prose_lines(text: str) -> Iterable[tuple[int, str]]:
    """Lines outside fenced code blocks, with inline code removed."""
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, INLINE_CODE.sub("", line)


def link_problems(root: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    for name in files:
        if not name.endswith(".md") or name.startswith(SKIPPED_PREFIXES):
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        for number, line in prose_lines(path.read_text(encoding="utf-8")):
            for target in LINK.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                if not (path.parent / relative).exists():
                    problems.append(f"{name}:{number}: broken link to {target}")
    return problems


def mention_problems(root: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    for name in files:
        path = root / name
        if (
            path.suffix not in TEXT_SUFFIXES
            or name.startswith(SKIPPED_PREFIXES)
            or name in SKIPPED_FILES
            or path.is_symlink()
            or not path.is_file()
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            problems.extend(
                f"{name}:{number}: mentions missing {mention}"
                for mention in DOC_MENTION.findall(line)
                if not (root / mention).exists()
            )
    return problems


def record_leaks(name: str, text: str) -> list[str]:
    """What a public run record must not contain. scripts/run_record.py applies it before writing one."""
    return [
        f"{name}:{number}: names {kind}"
        for number, line in enumerate(text.splitlines(), start=1)
        for kind, pattern in RECORD_LEAKS
        if pattern.search(line)
    ]


def record_problems(root: Path, files: list[str]) -> list[str]:
    return [
        problem
        for name in files
        if name.startswith(RECORD_PREFIX) and name.endswith(".md") and (root / name).is_file()
        for problem in record_leaks(name, (root / name).read_text(encoding="utf-8"))
    ]


def private_problems(files: list[str]) -> list[str]:
    return [f"{name}: raw review output must stay git-ignored" for name in files if name.startswith(PRIVATE_PREFIXES)]


def status_problems(root: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    for name in files:
        if not (name.startswith("docs/") and name.endswith(".md")) or name == "docs/README.md":
            continue
        head = "\n".join((root / name).read_text(encoding="utf-8").splitlines()[:12])
        if STATUS not in head:
            problems.append(f"{name}: no {STATUS} line in its first 12 lines")
    return problems


def template_problems(root: Path, files: list[str]) -> list[str]:
    index = root / "docs" / "README.md"
    listed = index.read_text(encoding="utf-8") if index.is_file() else ""
    problems: list[str] = []
    for name in files:
        if not (name.startswith("docs/templates/") and name.endswith(".md")):
            continue
        relative = name.removeprefix("docs/")
        if f"]({relative})" not in listed:
            problems.append(f"{name}: not listed in docs/README.md")
        if STATUS not in (root / name).read_text(encoding="utf-8"):
            problems.append(f"{name}: has no {STATUS} line")
    return problems


def frontmatter(text: str) -> Mapping[str, str]:
    """Top-level `key: value` pairs of a YAML frontmatter block; nested values are ignored."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip().strip("'\"")
    return {}


def skill_problems(root: Path) -> list[str]:
    problems: list[str] = []
    canonical = root / ".agents" / "skills"
    exposed = root / ".claude" / "skills"
    skills = sorted(p.name for p in canonical.iterdir() if p.is_dir()) if canonical.is_dir() else []
    for skill in skills:
        fields = frontmatter((canonical / skill / "SKILL.md").read_text(encoding="utf-8"))
        if fields.get("name") != skill:
            problems.append(f".agents/skills/{skill}/SKILL.md: frontmatter name must be {skill!r}")
        if not SKILL_NAME.match(skill) or len(skill) > 64:
            problems.append(f".agents/skills/{skill}: name must be lowercase words joined by hyphens")
        description = fields.get("description", "")
        if not description or len(description) > 1024:
            problems.append(f".agents/skills/{skill}/SKILL.md: description must be 1-1024 characters")
        link = exposed / skill
        if not link.is_symlink():
            problems.append(f".claude/skills/{skill}: missing; it must be a symlink to ../../.agents/skills/{skill}")
            continue
        target = link.readlink()
        if target.is_absolute():
            problems.append(f".claude/skills/{skill}: symlink target {target} is absolute")
        elif link.resolve() != (canonical / skill).resolve():
            problems.append(f".claude/skills/{skill}: symlink resolves to {link.resolve()}, not the canonical skill")
    if exposed.is_dir():
        problems.extend(
            f".claude/skills/{entry.name}: has no canonical skill in .agents/skills"
            for entry in sorted(exposed.iterdir())
            if entry.name not in skills
        )
    return problems


def portability_problems(root: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    for name in files:
        path = root / name
        if not name.startswith((".agents/", ".claude/")) and name not in {"AGENTS.md", "CLAUDE.md"}:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if ABSOLUTE_PATH.search(line):
                problems.append(f"{name}:{number}: absolute machine path")
    return problems


def agent_problems(root: Path) -> list[str]:
    problems: list[str] = []
    agents = root / ".claude" / "agents"
    for path in sorted(agents.glob("*.md")) if agents.is_dir() else []:
        fields = frontmatter(path.read_text(encoding="utf-8"))
        name = fields.get("name", "")
        where = f".claude/agents/{path.name}"
        if not name or not fields.get("description"):
            problems.append(f"{where}: needs a name and a description")
        if not fields.get("model") or fields.get("model") == "inherit":
            problems.append(f"{where}: must name an explicit model")
        tools = {t.strip() for t in fields.get("tools", "").split(",") if t.strip()}
        if name in READ_ONLY_AGENTS and (not tools or not tools <= READ_ONLY_TOOLS):
            problems.append(
                f"{where}: a read-only reviewer may use only {sorted(READ_ONLY_TOOLS)}, not {sorted(tools)}"
            )
    return problems


def check(root: Path) -> list[str]:
    files = tracked_files(root)
    return [
        *link_problems(root, files),
        *mention_problems(root, files),
        *status_problems(root, files),
        *template_problems(root, files),
        *skill_problems(root),
        *portability_problems(root, files),
        *agent_problems(root),
        *private_problems(files),
        *record_problems(root, files),
    ]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"docs check: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("docs check: links, status lines, templates, skills, and agents are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
