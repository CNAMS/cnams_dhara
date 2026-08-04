"""Algebraic laws for every lattice type.

Phase 1 exit criterion: *property tests green over 10,000 randomised operation
orders per lattice.* Each type below runs `LAW_EXAMPLES` Hypothesis examples,
and each example builds its values from a randomised sequence of operations, so
the operation-order coverage is the product of the two.

A fast property test is usually a weak one. The strategies here are deliberately
adversarial: a small value space so collisions actually happen, HLCs that
frequently tie on physical time so the `node_id` tiebreak is exercised, and a
handful of authors so concurrent edits by different people are common rather
than rare.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dhara.hlc import HLC
from dhara.lattice import (
    Entry,
    GSet,
    LWWRegister,
    MeasurementSeries,
    Observation,
    ORSet,
    StatusLattice,
    Tagged,
    join_from_total_order,
)
from tests.property.laws import LAW_EXAMPLES, assert_lattice_laws

pytestmark = pytest.mark.property

# A small space so collisions happen. Uniform random values across a large space
# almost never produce two concurrent edits to the same thing, which is the only
# interesting case.
elements = st.sampled_from(["a", "b", "c", "d"])
authors = st.sampled_from(["w1", "w2", "s1"])
nodes = st.sampled_from(["dev_a", "dev_b", "dev_c"])

# Physical times drawn from a tiny set so ties are frequent and the node_id
# tiebreak is genuinely exercised rather than incidentally.
hlcs = st.builds(
    HLC,
    pt=st.sampled_from([1_000, 1_001, 1_002]),
    c=st.integers(0, 3),
    node_id=nodes,
)


# -- GSet -----------------------------------------------------------------

g_sets = st.builds(lambda es: GSet(frozenset(es)), st.lists(elements, max_size=5))


@given(a=g_sets, b=g_sets, c=g_sets)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_gset_laws(a: GSet, b: GSet, c: GSet) -> None:
    assert_lattice_laws(a, b, c, decode=GSet.from_json, observations=GSet.observations)


# -- LWWRegister ----------------------------------------------------------

observations_ = st.builds(
    Observation,
    value=st.one_of(st.none(), st.text(min_size=0, max_size=3), st.integers(-5, 5)),
    hlc=hlcs,
    author=authors,
)
registers = st.builds(
    lambda os: LWWRegister(frozenset(os)), st.lists(observations_, max_size=4)
)


@given(a=registers, b=registers, c=registers)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_lww_register_laws(a: LWWRegister, b: LWWRegister, c: LWWRegister) -> None:
    assert_lattice_laws(
        a, b, c, decode=LWWRegister.from_json, observations=LWWRegister.observations
    )


@given(a=registers, b=registers)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_lww_join_never_shrinks_the_observed_set(a: LWWRegister, b: LWWRegister) -> None:
    """The no-silent-data-loss property for this lattice, stated directly.

    For any a and b, the values observable in join(a, b) are exactly the union
    of those observable in a and in b. This is what makes retention provable
    rather than asserted, and it is what mutation M2 of the deliberate-bug
    experiment violates.
    """
    joined = a.join(b)
    assert joined.observations() == a.observations() | b.observations()
    assert len(joined.observations_) >= max(len(a.observations_), len(b.observations_))


# -- ORSet ----------------------------------------------------------------

tagged = st.builds(Tagged, element=elements, tag=hlcs)
or_sets = st.builds(
    lambda adds, removed: ORSet(frozenset(adds), frozenset(removed)),
    st.lists(tagged, max_size=5),
    st.lists(hlcs, max_size=3),
)


@given(a=or_sets, b=or_sets, c=or_sets)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_or_set_laws(a: ORSet, b: ORSet, c: ORSet) -> None:
    assert_lattice_laws(a, b, c, decode=ORSet.from_json, observations=ORSet.observations)


# -- MeasurementSeries ----------------------------------------------------

entries = st.builds(
    Entry,
    value=st.integers(80, 84),
    taken_at=st.sampled_from(["T10:15", "T11:40"]),
    recorded_by=authors,
    hlc=hlcs,
    supersedes=st.none(),
)
series = st.builds(
    lambda es: MeasurementSeries.of(*es), st.lists(entries, max_size=5)
)


@given(a=series, b=series, c=series)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_measurement_series_laws(
    a: MeasurementSeries, b: MeasurementSeries, c: MeasurementSeries
) -> None:
    assert_lattice_laws(
        a,
        b,
        c,
        decode=MeasurementSeries.from_json,
        observations=MeasurementSeries.observations,
    )


@given(a=series, b=series)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_series_join_never_removes_an_observation(
    a: MeasurementSeries, b: MeasurementSeries
) -> None:
    """The load-bearing assertion of the whole project.

    Phase 2's deliberate-bug experiment disables exactly this by replacing the
    append with an overwrite (mutation M1). It is written as its own test, at
    the top level, so that when the experiment runs it is obvious which
    assertion the injected bug defeats.
    """
    joined = a.join(b)
    assert joined.observations() == a.observations() | b.observations()


@given(entry=entries, later=hlcs)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_redelivery_with_a_fresh_hlc_dedups(entry: Entry, later: HLC) -> None:
    """C-02. The same physical reading, re-issued on another path.

    The dedup key excludes the HLC precisely so this collapses. If it ever
    stops collapsing, every retried sync manufactures a phantom weighing.
    """
    redelivered = Entry(
        value=entry.value,
        taken_at=entry.taken_at,
        recorded_by=entry.recorded_by,
        hlc=later,
        supersedes=entry.supersedes,
    )
    merged = MeasurementSeries.of(entry).join(MeasurementSeries.of(redelivered))
    assert len(merged) == 1
    assert merged.entries[0].hlc == min(entry.hlc, later), (
        "dedup must keep the causally earliest of the two deliveries, or the "
        "choice depends on arrival order and the join is not commutative"
    )


# -- StatusLattice --------------------------------------------------------

ORDER = join_from_total_order(["s0", "s1", "s2", "s3"])
statuses = st.builds(lambda v: StatusLattice(v, ORDER), st.sampled_from(ORDER.values))


@given(a=statuses, b=statuses, c=statuses)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_status_lattice_laws(a: StatusLattice, b: StatusLattice, c: StatusLattice) -> None:
    assert_lattice_laws(
        a,
        b,
        c,
        # The declared order is not in the serialised value - it lives in the
        # consumer's schema binding. Decoding needs it supplied.
        decode=lambda v: StatusLattice.from_json(v, ORDER),
        # No no-loss check, and this is the one lattice where that is correct.
        # See test_status_does_not_retain_history below.
        observations=None,
    )


@given(a=statuses, b=statuses)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_status_does_not_retain_history_and_that_is_deliberate(
    a: StatusLattice, b: StatusLattice
) -> None:
    """The one lattice exempt from the no-loss property, stated as a test.

    Every other lattice here retains: a register keeps its losers, a series
    keeps every entry, an OR-Set keeps every tag. A status lattice does not,
    because its state is a **position in a declared order**, not a set of
    observations. Joining `s0` and `s1` yields `s1` and `s0` is gone from the
    state.

    That is not data loss. The transition history lives in the operation log,
    which is where a "who moved this record and when" question is answered from;
    the state answers "where is it now". Retaining prior positions in the state
    would make the join non-idempotent or the state unbounded, and would
    duplicate what the oplog already holds.

    Written as an explicit assertion rather than an omission, so that a future
    reader finding no no-loss check here knows it was a decision.
    """
    joined = a.join(b)
    assert joined.observations() == frozenset({joined.value})
    assert len(joined.observations()) == 1


@given(a=statuses, b=statuses)
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_status_join_is_independent_of_clock_order(
    a: StatusLattice, b: StatusLattice
) -> None:
    """C-09 and C-10, as a property.

    The whole reason this is not an LWW register: the result must not depend on
    which device's clock ran later. Since neither operand carries a timestamp,
    the join *cannot* consult one - which is the design, stated as a test.
    """
    assert a.join(b).value == b.join(a).value
