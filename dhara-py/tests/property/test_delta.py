"""Delta computation: the correctness property, as a property.

    join(peer_state, delta_since(peer_vv)) == join(peer_state, full_state)

Everything in this file exists to establish that one equation, because the whole
bandwidth argument depends on it and it is the kind of claim that is easy to
believe and hard to notice being wrong: a delta that omits something produces a
peer whose state is *quietly* incomplete, with no error anywhere.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dhara.delta import apply_delta, delta_since, frontier_of, is_empty, record_delta
from dhara.hlc import HLC
from dhara.lattice import (
    Entry,
    LWWRegister,
    MeasurementSeries,
    Observation,
    ORSet,
    Tagged,
    join_from_total_order,
)
from dhara.schema import Field, Record, Schema
from dhara.seen import SeenSet
from tests.property.laws import LAW_EXAMPLES

pytestmark = pytest.mark.property

ORDER = join_from_total_order(["s0", "s1", "s2", "s3"])
SCHEMA = Schema(
    "bench",
    (
        Field("m_a", "MeasurementSeries", scale=1),
        Field("d_a", "LWWRegister"),
        Field("st_a", "StatusLattice", order=ORDER),
        Field("set_a", "ORSet"),
    ),
)

nodes = st.sampled_from(["dev_a", "dev_b", "dev_c"])
authors = st.sampled_from(["w1", "w2", "s1"])
hlcs = st.builds(
    HLC, pt=st.sampled_from([1_000, 1_001, 1_002]), c=st.integers(0, 3), node_id=nodes
)


#: A fixed universe of operations, and a record is a **subset** of it.
#:
#: This models what replicas actually are. Two replicas hold overlapping subsets
#: of the same global set of operations - that is the entire premise - and a
#: delta's job is to close the gap between two subsets.
#:
#: ⚠ Generating each record independently does not model that, and the
#: difference is not cosmetic. **One HLC identifies one operation**, globally,
#: because every write calls `Clock.send()` once and that is strictly monotonic.
#: Independent generation produces records where the same HLC is a measurement
#: on one replica and a register write on another, which is unreachable in
#: practice and makes `has_seen` ambiguous: the seen-set says "saw operation T"
#: while the two states mean different things by T.
#:
#: The delta layer's soundness genuinely rests on this uniqueness. What breaks
#: it in the real world is C-24 - duplicate device ids - which is handled at
#: enrolment, and which the catalogue already records as the quietest failure
#: available.
def _universe() -> list[tuple[str, object]]:
    ops: list[tuple[str, object]] = []
    hlcs = [
        HLC(pt, c, node)
        for pt in (1_000, 1_001, 1_002)
        for c in range(2)
        for node in ("dev_a", "dev_b", "dev_c")
    ]
    for index, h in enumerate(hlcs):
        kind = index % 3
        if kind == 0:
            ops.append(
                ("m_a", Entry(80 + index % 4, f"T1{index % 2}", "w1", h))
            )
        elif kind == 1:
            ops.append(("d_a", Observation(["x", "y", None][index % 3], h, "w1")))
        else:
            ops.append(("set_a", Tagged(["t1", "t2"][index % 2], h)))
    return ops


UNIVERSE = _universe()


@st.composite
def records(draw: st.DrawFn) -> Record:
    """A subset of the shared operation universe, plus a status position.

    Built by construction rather than by driving operations, which is
    deliberate here and not a repeat of the Phase 2 mistake: this file tests an
    algebraic identity over arbitrary *reachable* states, and reachability of
    the operations themselves is the simulator's job.
    """
    from dhara.lattice import StatusLattice

    held = draw(
        st.lists(st.sampled_from(range(len(UNIVERSE))), max_size=9, unique=True)
    )
    entries, observations, adds = [], [], []
    for index in held:
        field_name, op = UNIVERSE[index]
        if field_name == "m_a":
            entries.append(op)
        elif field_name == "d_a":
            observations.append(op)
        else:
            adds.append(op)

    # A remove can only reference an add this replica observed.
    removed = frozenset(t.tag for t in adds if draw(st.booleans()))

    return Record(
        SCHEMA,
        {
            "m_a": MeasurementSeries.of(*entries),
            "d_a": LWWRegister(frozenset(observations)),
            "st_a": StatusLattice(draw(st.sampled_from(ORDER.values)), ORDER),
            "set_a": ORSet(frozenset(adds), removed),
        },
    )


@given(sender=records(), peer=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_delta_completes_the_peer_exactly(sender: Record, peer: Record) -> None:
    """**The** property. Everything else in Phase 3 rests on it.

    A peer that applies the delta must reach precisely the state it would have
    reached by receiving the sender's entire state.
    """
    frontier = frontier_of(peer)
    delta = record_delta(sender, frontier)

    via_delta = apply_delta(peer, delta)
    via_full_state = peer.join(sender)

    assert via_delta.canonical() == via_full_state.canonical(), (
        "a delta did not complete the peer to the same state as the full join"
    )


@given(sender=records(), peer=records(), third=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_deltas_compose(sender: Record, peer: Record, third: Record) -> None:
    """A device that misses three syncs receives one merged delta.

    Without this, a backlog would have to be replayed as a sequence of separate
    deltas in order - which is exactly the fragile, order-dependent design that
    lattices exist to avoid.
    """
    frontier = frontier_of(peer)
    combined = sender.join(third)

    stepwise = apply_delta(
        apply_delta(peer, record_delta(sender, frontier)),
        record_delta(third, frontier),
    )
    at_once = apply_delta(peer, record_delta(combined, frontier))

    assert stepwise.canonical() == at_once.canonical()


@given(sender=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_delta_against_an_up_to_date_peer_carries_only_unfilterable_fields(
    sender: Record,
) -> None:
    """The common case on a healthy link — and it is *not* free.

    Every field carrying its own HLC drops out. What remains is the status and
    the OR-Set's tombstones, which carry no timestamp and so cannot be proven
    already-delivered from a frontier alone.

    ⚠ Asserted as it actually is rather than as it should be. An earlier
    version of `record_delta` dropped these to make an idle sync free, and that
    was unsound: a peer that had never seen the record would never receive its
    status. The cost is real and the fix is
    [D-15](../../DOUBTS.md#d-15), not a cleverer filter.
    """
    delta = record_delta(sender, frontier_of(sender))
    set_value = sender.state["set_a"]
    unfilterable = {"st_a"} | (
        {"set_a"} if (set_value.adds or set_value.removed_tags) else set()  # type: ignore[attr-defined]
    )
    assert set(delta) <= unfilterable, (
        f"a field carrying its own HLC survived an up-to-date frontier: "
        f"{sorted(set(delta) - unfilterable)}"
    )


@given(sender=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_delta_against_an_empty_peer_carries_everything(sender: Record) -> None:
    empty = SeenSet()
    delta = record_delta(sender, empty)
    rebuilt = apply_delta(SCHEMA.empty_record(), delta)
    assert rebuilt.canonical() == sender.canonical()


@given(sender=records(), peer=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_delta_is_never_larger_than_the_full_state(
    sender: Record, peer: Record
) -> None:
    """If a delta can exceed the state it derives from, the design has not
    earned its complexity."""
    frontier = frontier_of(peer)
    for name, part in record_delta(sender, frontier).items():
        assert part.leq(sender.state[name]), (  # type: ignore[attr-defined]
            f"delta for {name!r} is not below the sender's own state"
        )


@given(sender=records(), peer=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_the_register_delta_carries_history(sender: Record, peer: Record) -> None:
    """The failure this module is most likely to have.

    Sending only the current winner leaves a retained loser existing on the
    sender and nowhere else - retention violated by the transport rather than
    by the merge, with the sender's own state correct throughout. Nothing but
    this test notices.
    """
    frontier = frontier_of(peer)
    delta = delta_since(sender.state["d_a"], frontier)
    assert isinstance(delta, LWWRegister)

    sender_register = sender.state["d_a"]
    assert isinstance(sender_register, LWWRegister)
    unseen = {o for o in sender_register.observations_ if not frontier.has_seen(o.hlc)}

    assert delta.observations_ == frozenset(unseen), (
        "the register delta dropped observations the peer has not seen"
    )


@given(sender=records(), peer=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_the_or_set_delta_carries_removes_as_well_as_adds(
    sender: Record, peer: Record
) -> None:
    """Adds without removes resurrect deleted elements on the peer."""
    frontier = frontier_of(peer)
    delta = delta_since(sender.state["set_a"], frontier)
    assert isinstance(delta, ORSet)

    sender_set = sender.state["set_a"]
    assert isinstance(sender_set, ORSet)

    # The whole value, both halves. A single HLC means "add" inside `adds` and
    # "remove of that add" inside `removed_tags`, and a frontier cannot say
    # which the peer saw - so neither half can be filtered. Filtering removes
    # resurrects elements; filtering adds diverges canonical state.
    assert delta.removed_tags == sender_set.removed_tags
    assert delta.adds == sender_set.adds


@given(sender=records(), peer=records())
@settings(max_examples=LAW_EXAMPLES, deadline=None)
def test_a_sparse_delta_leaves_omitted_fields_alone(
    sender: Record, peer: Record
) -> None:
    """An absent field means "nothing new", never "empty".

    Getting this backwards would clear fields on the receiver - a data-loss bug
    caused entirely by an encoding choice.
    """
    frontier = frontier_of(peer)
    delta = record_delta(sender, frontier)
    applied = apply_delta(peer, delta)

    for name in SCHEMA.field_names:
        if name not in delta:
            assert applied.state[name].canonical() == peer.state[name].canonical(), (  # type: ignore[attr-defined]
                f"field {name!r} was omitted from the delta but changed anyway"
            )


def test_is_empty_recognises_each_empty_container() -> None:
    assert is_empty(MeasurementSeries())
    assert is_empty(LWWRegister())
    assert is_empty(ORSet())
    assert not is_empty(MeasurementSeries.of(Entry(80, "T10", "w1", HLC(1, 0, "a"))))


def test_an_unknown_lattice_type_is_refused() -> None:
    """The catalogue is closed; a silent pass-through would send full state
    forever without anyone noticing the delta had stopped working."""
    from dhara.lattice.base import LatticeError

    with pytest.raises(LatticeError, match="no delta rule"):
        delta_since(object(), SeenSet())
