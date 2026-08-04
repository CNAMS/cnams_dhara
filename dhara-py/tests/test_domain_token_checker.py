"""The dependency-rule checker must actually reject things.

A checker that has never been observed to fail is indistinguishable from
`assert True`. These tests are the checker's own deliberate-bug experiment, in
miniature: feed it a violation and confirm it says so, with the file, the line
and the offending token.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_no_domain_imports.py"


def run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(p) for p in paths)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_repository_is_clean() -> None:
    """The real check. Runs over the whole in-scope tree."""
    result = run()
    assert result.returncode == 0, result.stderr


def test_a_domain_token_is_rejected(tmp_path: Path) -> None:
    offender = REPO / "dhara-py" / "tests" / "_tmp_domain_violation.py"
    offender.write_text("def weigh(child_id: str) -> None: ...\n")
    try:
        result = run(offender)
        assert result.returncode == 1
        assert "child" in result.stderr
        assert "_tmp_domain_violation.py:1" in result.stderr
    finally:
        offender.unlink()


def test_the_message_names_the_remedy(tmp_path: Path) -> None:
    """A failure message that only says 'no' teaches nothing.

    The remedy - extend the schema descriptor - is the whole point, and it is
    what a tired author needs to read at the moment the check fires.
    """
    offender = REPO / "dhara-py" / "tests" / "_tmp_domain_violation2.py"
    offender.write_text("BENEFICIARY = 1\n")
    try:
        result = run(offender)
        assert "schema descriptor" in result.stderr
        assert "ADR-0001" in result.stderr
    finally:
        offender.unlink()


def test_an_origin_note_comment_is_allowed() -> None:
    offender = REPO / "dhara-py" / "tests" / "_tmp_origin_note.py"
    offender.write_text("# origin-note: spun out of a child growth monitoring project\nX = 1\n")
    try:
        assert run(offender).returncode == 0
    finally:
        offender.unlink()


def test_ordinary_technical_words_are_not_flagged() -> None:
    """`child_process` and `childNodes` are not domain vocabulary.

    A checker noisy enough to be disabled protects nothing, so the compound
    allowlist is part of the design rather than a workaround.
    """
    ok = REPO / "dhara-py" / "tests" / "_tmp_compound.py"
    ok.write_text("import subprocess  # child_process style naming\nX = 1\n")
    try:
        assert run(ok).returncode == 0
    finally:
        ok.unlink()


@pytest.mark.parametrize("token", ["beneficiary", "anganwadi", "cgms", "poshan", "aadhaar"])
def test_each_forbidden_token_is_caught(token: str) -> None:
    offender = REPO / "dhara-py" / "tests" / f"_tmp_{token}.py"
    offender.write_text(f"{token}_field = 1\n")
    try:
        assert run(offender).returncode == 1, f"{token} was not caught"
    finally:
        offender.unlink()


def test_this_file_is_the_only_exempt_file() -> None:
    """The bootstrap exemption stays exactly one file wide.

    This test file must contain the tokens it tests for, so it is exempt by
    exact path. If a second path ever appears in that set, it is far more likely
    to be a real violation somebody worked around than a second bootstrap
    problem — so the size of the set is itself an assertion.
    """
    source = SCRIPT.read_text()
    start = source.index("SELF_TEST_EXEMPT = frozenset({")
    end = source.index("})", start)
    exempt = source[start:end]
    assert exempt.count('"') == 2, "more than one path is exempt from the checker"
    assert "test_domain_token_checker.py" in exempt


def test_prose_outside_the_scope_is_not_checked() -> None:
    """spec/*.md and docs/ are exempt.

    The conflict catalogue must describe real scenarios in real vocabulary -
    that is its purpose, and a document cannot be imported. This asserts the
    exemption rather than leaving it as an accident of the glob.
    """
    catalogue = REPO / "spec" / "conflict-catalogue.md"
    assert catalogue.exists()
    assert "child" in catalogue.read_text().lower()
    assert run().returncode == 0
