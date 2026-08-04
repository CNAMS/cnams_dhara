"""Record-level joins and the signals derived from them.

Two properties here matter more than the rest:

**Field-wise independence.** No field's merged value may depend on another
field's. It is what makes concurrent edits to different fields a non-event
(C-04, C-07), and it is the property most easily broken later by a well-meaning
cross-field validation rule.

**Signal determinism.** Signals are derived from merged state, so two replicas
that converge must emit identical signals - including identical evidence.
That is asserted here rather than assumed, because the first implementation got
it wrong: evidence was built from frozenset iteration order, and two merge
orders produced signals that compared unequal despite identical state.
"""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dhara import review
from dhara.hlc import HLC
from dhara.lattice import Entry, LWWRegister, join_from_total_order
from dhara.schema import Field, Record, Schema

pytestmark = pytest.mark.property

ORDER = join_from_total_order(["s0", "s1", "s2", "s3"])

SCHEMA = Schema(
    "bench",
    (
        Field("m_a", "MeasurementSeries", scale=1),
        Field("m_b", "MeasurementSeries", scale=1),
        Field("d_a", "LWWRegister"),
        Field("d_b", "LWWRegister"),
        Field("st_a", "StatusLattice", order=ORDER),
        Field("set_a", "ORSet"),
        Field("g_a", "GSet"),
    ),
)

authors = st.sampled_from(["w1", "w2", "s1"])
nodes = st.sampled_from(["dev_a", "dev_b"])
hlcs = st.builds(
    HLC, pt=st.sampled_from([1_000, 1_001]), c=st.integers(0, 2), node_id=nodes
)


@st.composite
def records(draw: st.DrawFn) -> Record:
    state: dict[str, object] = {}
    for f in SCHEMA.fields:
        if f.lattice == "MeasurementSeries":
            n = draw(st.integers(0, 2))
            state[f.name] = [
                Entry(
                    value=draw(st.integers(80, 83)),
                    taken_at=draw(st.sampled_from(["2026-05-01T10:15", "2026-05-02T11:40"])),
                    recorded_by=draw(authors),
                    hlc=draw(hlcs),
                ).to_json()
                for _ in range(n)
            ]
        elif f.lattice == "LWWRegister":
            if draw(st.booleans()):
                state[f.name] = LWWRegister.of(
                    draw(st.sampled_from(["x", "y", None])), draw(hlcs), draw(authors)
                ).to_json()
        elif f.lattice == "StatusLattice":
            state[f.name] = draw(st.sampled_from(ORDER.values))
    return SCHEMA.decode_record(state)


@given(a=records(), b=records())
@settings(max_examples=500, deadline=None)
def test_record_join_is_commutative(a: Record, b: Record) -> None:
    assert a.join(b).canonical() == b.join(a).canonical()


@given(a=records(), b=records(), c=records())
@settings(max_examples=500, deadline=None)
def test_record_join_is_associative(a: Record, b: Record, c: Record) -> None:
    assert a.join(b).join(c).canonical() == a.join(b.join(c)).canonical()


@given(a=records())
@settings(max_examples=500, deadline=None)
def test_record_join_is_idempotent(a: Record) -> None:
    assert a.join(a).canonical() == a.canonical()


@given(a=records(), b=records())
@settings(max_examples=500, deadline=None)
def test_fields_merge_independently(a: Record, b: Record) -> None:
    """C-04 and C-07: a field's merged value depends on that field alone.

    Checked by joining the whole records, then joining each field in isolation,
    and requiring the two to agree. A cross-field rule anywhere in `Record.join`
    breaks this immediately.
    """
    joined = a.join(b)
    for name in SCHEMA.field_names:
        isolated = a.state[name].join(b.state[name])  # type: ignore[attr-defined]
        assert joined.state[name].canonical() == isolated.canonical(), (  # type: ignore[attr-defined]
            f"field {name!r} merged differently in isolation than in the record; "
            f"some cross-field logic has crept into Record.join"
        )


@given(a=records(), b=records(), c=records())
@settings(max_examples=300, deadline=None)
def test_signals_are_identical_across_every_merge_order(
    a: Record, b: Record, c: Record
) -> None:
    """Signal determinism, as a corollary of convergence.

    Every permutation of three replicas produces the same state, so it must
    produce the same signals - codes *and* evidence. Evidence equality is the
    part that caught a real bug: it was built from frozenset iteration order and
    differed between merge orders despite identical state.
    """
    results = []
    for x, y, z in itertools.permutations((a, b, c)):
        merged = x.join(y).join(z)
        results.append((merged.canonical(), review.detect(merged, inputs=(x, y, z))))

    first_state, first_signals = results[0]
    for state, signals in results[1:]:
        assert state == first_state, "replicas did not converge"
        assert signals == first_signals, (
            f"identical state produced different signals across merge orders:\n"
            f"  {first_signals}\n  {signals}"
        )


@given(a=records(), b=records())
@settings(max_examples=300, deadline=None)
def test_every_emitted_signal_is_in_the_declared_set(a: Record, b: Record) -> None:
    """The signal set is closed by the catalogue.

    A code with no catalogue entry has no defined meaning, and a supervisor
    cannot act on it.
    """
    for signal in review.detect(a.join(b), inputs=(a, b)):
        assert signal.code in review.SIGNAL_CODES


@given(a=records())
@settings(max_examples=300, deadline=None)
def test_a_record_joined_with_empty_is_unchanged(a: Record) -> None:
    """Every lattice has an identity, which is what lets a replica join against
    a peer that has never seen a field at all."""
    assert a.join(SCHEMA.empty_record()).canonical() == a.canonical()
