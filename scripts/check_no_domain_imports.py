#!/usr/bin/env python3
"""Fail the build if domain vocabulary appears in the engine or the vectors.

This is the mechanical form of the dependency rule (ADR-0001):

    cgms monorepo  ────depends on───▶  dhara
         (never the reverse)

The trap it exists to catch is specific and it is not hypothetical: you, at
2 AM during exams, writing `from app.models import Child` inside a merge
function, because it is faster than extending the schema descriptor and it
makes the failing test pass. The merge logic then knows what a child is and
is no longer a sync engine — it is a feature of one backend.

A repository boundary makes that import unavailable. This script catches the
softer versions: a field named `child_weight`, a test fixture called
`beneficiary`, a docstring that assumes what the data is.

Scope is narrower than "everything", deliberately — see plan/repo-layout.md
section 3. Prose under spec/*.md and docs/ is exempt, because the conflict
catalogue *must* describe real scenarios in real vocabulary; that is its
entire purpose, and a document cannot be imported.

Usage:
    python3 scripts/check_no_domain_imports.py            # whole tree
    python3 scripts/check_no_domain_imports.py <paths...> # specific files
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The word list lives here rather than in a config file, so changing it
# requires a commit that says why.
FORBIDDEN = [
    "child",
    "beneficiary",
    "anganwadi",
    "cgms",
    "mother",
    "immunis",
    "poshan",
    "aadhaar",
]

# Directories whose contents are checked. Everything else is prose.
IN_SCOPE = (
    "dhara-py/dhara",
    "dhara-py/sim",
    "dhara-py/tests",
    "dhara-dart/lib",
    "dhara-dart/test",
    "spec/conformance",
)

SUFFIXES = {".py", ".dart", ".json"}

# The bootstrap exemption. This checker's own tests must contain the tokens it
# rejects, or they cannot test that it rejects them. Exempting by exact path
# rather than by pattern keeps the hole one file wide: a second file cannot
# quietly acquire the exemption by being named similarly.
#
# The alternative - assembling the tokens at runtime so they never appear
# literally - would pass this checker and make the tests unreadable, which is a
# worse trade. A named exemption is visible; obfuscation is not.
SELF_TEST_EXEMPT = frozenset({"dhara-py/tests/test_domain_token_checker.py"})

# The escape hatch. Deliberately ugly to type, because every use should be a
# small decision rather than a reflex.
ESCAPE = re.compile(r"#\s*origin-note:|//\s*origin-note:")

# `child` appears inside ordinary technical words. Matching those would make
# the checker so noisy it gets disabled, which is the real failure mode.
ALLOWED_COMPOUNDS = re.compile(
    r"\b(child_process|childNodes|child_stream|childstream|grandchild)\b",
    re.I,
)

WORD = {w: re.compile(rf"\b\w*{re.escape(w)}\w*\b", re.I) for w in FORBIDDEN}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def in_scope(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    if path.suffix not in SUFFIXES:
        return False
    if rel in SELF_TEST_EXEMPT:
        return False
    return any(rel.startswith(prefix) for prefix in IN_SCOPE)


def scan(path: Path, root: Path) -> list[str]:
    problems: list[str] = []
    rel = path.resolve().relative_to(root).as_posix()

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if ESCAPE.search(line):
            continue
        cleaned = ALLOWED_COMPOUNDS.sub("", line)
        for word, pattern in WORD.items():
            match = pattern.search(cleaned)
            if match:
                problems.append(
                    f"{rel}:{lineno}: domain token {word!r} in {match.group(0)!r}\n"
                    f"    {line.strip()}"
                )
    return problems


def candidates(argv: list[str], root: Path) -> list[Path]:
    if argv:
        return [Path(a) for a in argv]
    return [
        p
        for prefix in IN_SCOPE
        for p in (root / prefix).rglob("*")
        if p.is_file()
    ]


def main(argv: list[str]) -> int:
    root = repo_root()
    problems: list[str] = []

    for path in candidates(argv, root):
        if path.is_file() and in_scope(path, root):
            problems.extend(scan(path, root))

    if not problems:
        return 0

    print("domain vocabulary found where the dependency rule forbids it:\n", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print(
        "\ndhara receives a schema descriptor at runtime. It never knows what a\n"
        "record represents. If this change genuinely needs domain knowledge, the\n"
        "fix is to extend the schema descriptor - not to name the concept here.\n"
        "If that is impossible, stop and reconsider the design: this is the\n"
        "failure the repository split exists to prevent. See ADR-0001.\n"
        "\nProse may use an explicit `# origin-note:` comment.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
