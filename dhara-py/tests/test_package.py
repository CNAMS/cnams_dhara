"""Smoke tests, so the suite is non-empty before there is anything to test.

Phase 0's deliverable is "CI running an empty test suite" — the value being
that the pipeline is proven before there is anything at stake. A suite that
collects zero tests passes for the wrong reason, so it collects these.
"""

import dhara


def test_package_imports() -> None:
    assert dhara.__version__


def test_protocol_version_is_an_integer() -> None:
    """The wire protocol version is an integer, not a semver string.

    It is compared with < and > during handshake negotiation, and a string
    comparison there would order "10" before "9".
    """
    assert isinstance(dhara.PROTOCOL_VERSION, int)
    assert dhara.PROTOCOL_VERSION >= 1
