#!/usr/bin/env python3
"""Reject commit messages carrying co-author or tool-attribution trailers.

Commits in this repository are authored by the repository owner. This is the
mechanical form of the rule in plan/commit-conventions.md section 6.

It exists as a hook rather than a convention because the cost curve is steep: a
trailer caught here costs one re-edit, and the same trailer caught after the
branch is public costs a history rewrite that breaks every clone and every SHA
already cited in the CGMS repository.

Usage (pre-commit passes the message file path):
    python3 scripts/check_no_attribution_trailers.py .git/COMMIT_EDITMSG
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matched case-insensitively against whole lines of the commit body.
FORBIDDEN = [
    (re.compile(r"^\s*co-authored-by\s*:", re.I), "co-author trailer"),
    (re.compile(r"^\s*co-committed-by\s*:", re.I), "co-committer trailer"),
    (re.compile(r"generated\s+with\b", re.I), "tool-attribution line"),
    (re.compile(r"^\s*(created|authored|written)\s+by\s+.*\b(ai|bot|assistant)\b", re.I),
     "tool-attribution line"),
    (re.compile(r"\b(claude|copilot|chatgpt|gpt-[0-9])\b", re.I), "tool name"),
]


def check(message: str) -> list[str]:
    problems: list[str] = []
    for lineno, line in enumerate(message.splitlines(), start=1):
        # Comment lines are stripped by git before the message is stored.
        if line.startswith("#"):
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(line):
                problems.append(f"  line {lineno}: {label} — {line.strip()!r}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_no_attribution_trailers.py <commit-msg-file>", file=sys.stderr)
        return 2

    problems = check(Path(argv[1]).read_text(encoding="utf-8"))
    if not problems:
        return 0

    print("commit message carries attribution that does not belong here:", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    print(
        "\nCommits in this repository are authored by the repository owner.\n"
        "See plan/commit-conventions.md section 6.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
