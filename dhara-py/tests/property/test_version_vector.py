"""Version vectors obey the lattice laws, and their comparisons agree with them.

A vector is a lattice, so it gets the same treatment as every other lattice
here — the same law checkers, the same adversarial strategies, the same no-loss
property. That is the payoff of having built the harness generically in Phase 1.

The extra assertions below are about the *comparisons* — `dominates`,
`missing_from`, `has_seen`. Those are second implementations of the order the
join already defines, and second implementations drift. Each is checked against
the join rather than against intuition.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dhara.hlc import HLC
from dhara.version_vector import VersionVector
from tests.property.laws import LAW_EXAMPLES, assert_lattice_laws

pytestmark = pytest.mark.property

nodes = st.sampled_from(["dev_a", "dev_b", "dev_c"])
hlcs = st.builds(
    HLC, pt=st.sampled_from([1_000, 1_001, 1_002]), c=st.integers(0, 3), node_id=nodes
)
vectors = st.builds(
    lambda hs: VersionVector.of(*hs), st.lists(hlcs, max_size=4)
)


@given(a=vectors, b=vectors, c=vectors)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_version_vector_laws(
    a: VersionVector, b: VersionVector, c: VersionVector
) -> None:
    assert_lattice_laws(
        a,
        b,
        c,
        decode=VersionVector.from_json,
        # No no-loss check. A frontier holds a maximum per replica, not a
        # history, so joining a higher timestamp replaces a lower one - see
        # test_a_frontier_does_not_retain_superseded_entries below.
        observations=None,
    )


@given(a=vectors, b=vectors)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_frontier_does_not_retain_superseded_entries(
    a: VersionVector, b: VersionVector
) -> None:
    """The second lattice exempt from the no-loss property, stated as a test.

    `StatusLattice` is the first, for the same underlying reason: its state is
    a position rather than a set of observations. A frontier says "everything
    from this replica up to here", so a higher entry *subsumes* a lower one -
    retaining the lower would be redundant, and would make the vector grow
    without bound over a six-month backlog.

    Nothing is lost, because the superseded entry is implied: `has_seen`
    answers yes for every operation at or below the frontier.
    """
    joined = a.join(b)
    for node, hlc in joined:
        for source in (a, b):
            theirs = source.get(node)
            if theirs is not None:
                assert theirs <= hlc, "the join must not go backwards"
                assert joined.has_seen(theirs), (
                    "a superseded entry must still be implied by the frontier"
                )


@given(a=vectors, b=vectors)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_dominates_agrees_with_join(a: VersionVector, b: VersionVector) -> None:
    """`a` dominates `b` exactly when joining `b` into `a` changes nothing.

    `dominates` is a second implementation of the order that `join` defines.
    Checking it against the join is what stops the two drifting apart — and
    they would, because `dominates` is the one used on the hot path.
    """
    assert a.dominates(b) == (a.join(b).canonical() == a.canonical())


@given(a=vectors, b=vectors)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_concurrency_is_mutual_non_domination(
    a: VersionVector, b: VersionVector
) -> None:
    assert a.is_concurrent_with(b) == (not a.dominates(b) and not b.dominates(a))
    assert a.is_concurrent_with(b) == b.is_concurrent_with(a)


@given(a=vectors, b=vectors)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_missing_from_is_empty_exactly_when_dominating(
    a: VersionVector, b: VersionVector
) -> None:
    """The pull request is empty precisely when there is nothing to pull.

    A false negative here — reporting no gap when one exists — is silent data
    loss at the session layer, which no merge-level invariant would catch.
    """
    assert (a.missing_from(b) == {}) == a.dominates(b)


@given(a=vectors, h=hlcs)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_observing_an_operation_makes_it_seen(a: VersionVector, h: HLC) -> None:
    assert a.observe(h).has_seen(h)


@given(a=vectors, h=hlcs)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_observe_is_idempotent_and_monotonic(a: VersionVector, h: HLC) -> None:
    once = a.observe(h)
    assert once.canonical() == once.observe(h).canonical()
    assert a.leq(once), "observing an operation must never lose ground"


@given(a=vectors, h=hlcs)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_has_seen_never_claims_an_unobserved_operation(
    a: VersionVector, h: HLC
) -> None:
    """The direction that matters.

    Claiming to have seen something you have not means the operation is
    rejected as a duplicate and never applied — silent loss. The reverse
    (claiming not to have seen something you have) costs a redundant send and
    is caught by idempotent application.
    """
    if a.has_seen(h):
        known = a.get(h.node_id)
        assert known is not None and h <= known


def test_a_frontier_entry_must_be_that_replicas_own_timestamp() -> None:
    """Guards the one way this type can be built into nonsense.

    A frontier keyed by one replica but holding another's timestamp makes
    `missing_from` compute a gap against the wrong replica, which sends the
    wrong data and reports success.
    """
    from dhara.lattice.base import LatticeError

    with pytest.raises(LatticeError, match="own timestamp"):
        VersionVector({"dev_a": HLC(1_000, 0, "dev_b")})


def test_wire_form_omits_the_redundant_node_id() -> None:
    """A vector is exchanged on every session before any data moves, so a third
    of its bytes is worth removing."""
    vector = VersionVector.of(HLC(1_000, 0, "dev_a"), HLC(2_000, 1, "dev_b"))
    assert vector.to_json() == [[1_000, 0, "dev_a"], [2_000, 1, "dev_b"]]
    assert VersionVector.from_json(vector.to_json()).canonical() == vector.canonical()
