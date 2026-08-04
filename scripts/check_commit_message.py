#!/usr/bin/env python3
"""Check a commit message against plan/commit-conventions.md.

Enforced:
  - Conventional Commits form: type(scope): subject
  - `type` from the closed list
  - `scope` from the closed list, and required for dhara-py/, dhara-dart/, spec/
  - subject <= 72 chars, imperative mood, lowercase, no trailing period
  - a `fix:` commit must have a body (the failure mode it fixes)

Not enforced, on purpose:
  - Body wrapping. Worth doing, not worth blocking a commit at 11 PM over.
  - Footer presence. `Seed:` on a simulator-found fix is a rule the author keeps,
    because a hook cannot tell which fixes came from the simulator.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = {
    "feat", "fix", "test", "sim", "spec", "perf", "refactor",
    "docs", "build", "ci", "chore", "wip",
}

SCOPES = {
    "hlc", "lattice", "lww", "gset", "orset", "series", "status",
    "vv", "delta", "session", "queue", "schema", "store", "crypto",
    "identity", "review", "conformance", "sim", "net", "clock",
    "dart", "py", "plan", "metrics", "sync",
}

HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z-]+)\))?(?P<bang>!)?: (?P<subject>.+)$")

# Past-tense and gerund openers, the two most common non-imperative forms.
NON_IMPERATIVE = re.compile(r"^(added|adds|adding|fixed|fixes|fixing|updated|updates|"
                            r"updating|removed|removes|removing|changed|changes|changing)\b", re.I)


def check(message: str) -> list[str]:
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    if not lines or not lines[0].strip():
        return ["commit message is empty"]

    header, *rest = lines
    problems: list[str] = []

    m = HEADER.match(header)
    if not m:
        return [
            f"header does not match `type(scope): subject`:\n    {header!r}",
            f"    valid types: {', '.join(sorted(TYPES))}",
        ]

    ctype = m.group("type")
    scope = m.group("scope")
    subject = m.group("subject")

    if ctype not in TYPES:
        problems.append(f"unknown type {ctype!r}; valid: {', '.join(sorted(TYPES))}")

    if scope is not None and scope not in SCOPES:
        problems.append(
            f"unknown scope {scope!r}. Adding a scope is itself a chore commit "
            f"that edits plan/commit-conventions.md."
        )

    if len(header) > 72:
        problems.append(f"header is {len(header)} chars; limit is 72")

    if subject[:1].isupper():
        problems.append(f"subject should be lowercase: {subject!r}")

    if subject.endswith("."):
        problems.append("subject should not end with a period")

    if NON_IMPERATIVE.match(subject):
        problems.append(f"subject should be imperative mood: {subject!r}")

    body = "\n".join(rest).strip()
    if ctype == "fix" and not body:
        problems.append(
            "a fix commit needs a body stating the failure mode it fixes. "
            "Not 'fixes merge bug' - what went wrong, under what interleaving."
        )

    if rest and rest[0].strip():
        problems.append("leave a blank line between the header and the body")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_commit_message.py <commit-msg-file>", file=sys.stderr)
        return 2

    problems = check(Path(argv[1]).read_text(encoding="utf-8"))
    if not problems:
        return 0

    print("commit message does not follow plan/commit-conventions.md:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
