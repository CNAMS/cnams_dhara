"""Delta-state computation: send the difference, not the state.

    Sending a full record with forty measurements to convey one new one wastes
    the window.

A delta is the smallest state whose join with the peer's state yields the full
join. It is itself a lattice value, which is what makes deltas **compose**: a
device that misses three syncs receives one merged delta rather than three.

## The correctness property

For every lattice, and this is a property test rather than a code review:

    join(peer_state, delta_since(peer_vv)) == join(peer_state, full_state)

⚠ **For `LWWRegister` the delta must carry history**, not just the current
winner. Omitting it silently violates retained-losers *over the wire* while
every local test still passes, because the sender's own state is correct. That
is the failure mode this module is most likely to have, so it gets its own
property test and its own mutation.

## Why deltas are computed from what the peer has seen, not from a diff

Diffing two states requires having both. The whole point is that neither side
does: the sender has the peer's *seen-set*, not the peer's state.

⚠ **Not a `VersionVector`.** A frontier is a maximum, and `has_seen` on it is
only equivalent to "received" when operations arrive in order and without gaps -
which reordering, one of the six injected fault classes, routinely breaks.
Filtering on a frontier silently omits operations the peer never received. See
`dhara.seen` for the full analysis and
[DOUBTS.md D-16](../../DOUBTS.md#d-16) for the fix that would make the compact
form sound again.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from dhara.lattice import (
    Entry,
    GSet,
    LWWRegister,
    MeasurementSeries,
    ORSet,
    StatusLattice,
    Tagged,
)
from dhara.lattice.base import LatticeError
from dhara.schema import Record, Schema
from dhara.seen import SeenSet

__all__ = ["EMPTY_RECORD_DELTA", "delta_since", "record_delta"]

T = TypeVar("T")


def _series_delta(value: MeasurementSeries, frontier: SeenSet) -> MeasurementSeries:
    """Entries the peer's frontier has not covered.

    Filtered on the entry's own HLC, so an entry written by a replica the peer
    has never heard from is included in full.
    """
    unseen = frozenset(e for e in value.entries_ if not frontier.has_seen(e.hlc))
    return MeasurementSeries(unseen, value.dedup_on)


def _register_delta(value: LWWRegister, frontier: SeenSet) -> LWWRegister:
    """Unseen observations - **including history**.

    The current winner alone is not enough. If the peer is missing a *loser*,
    omitting it means that value exists on the sender and nowhere else, and
    retention has been violated by the transport rather than by the merge. The
    local state is correct throughout, so nothing but a delta-specific test
    catches it.
    """
    unseen = frozenset(o for o in value.observations_ if not frontier.has_seen(o.hlc))
    return LWWRegister(unseen)


def _or_set_delta(value: ORSet, frontier: SeenSet) -> ORSet:
    """**Unfiltered.** An OR-Set delta is the whole value.

    ⚠ This is not laziness; two property-test failures were needed to establish
    it. An OR-Set cannot be filtered against a version vector, because a single
    HLC means two different things inside one:

    * as a tag in `adds`, it identifies an **add**;
    * as a member of `removed_tags`, it identifies the **remove** of that add.

    A frontier records only "this replica saw HLC T". It cannot say which of the
    two the peer saw - and both filtering directions are wrong:

    | Filtering | Failure |
    |---|---|
    | Removes, by `has_seen(tag)` | The peer saw the *add*, so the remove is dropped and **the element resurrects** |
    | Adds, by `has_seen(tag)` | The peer saw only the *remove*, so the add is dropped and the two replicas hold different state for the same observable set |

    The second is milder - the element is correctly absent either way - but it
    leaves delta-synced and full-state-synced replicas with different canonical
    forms, which is a convergence failure by the definition used here.

    **Cost:** an OR-Set travels whole on any delta that includes its record.
    Tags are small and bounded by operation count rather than data volume, so
    this is affordable at v0.1 scale and is not affordable forever.

    > The fix is to give a remove its own HLC, making the two cases
    > distinguishable. That is a lattice and wire-format change, tied to the
    > tombstone-retention question. -> [DOUBTS.md D-15](../../DOUBTS.md#d-15),
    > [open-questions.md](../../plan/open-questions.md) Q2
    """
    del frontier
    return value


def _g_set_delta(value: GSet, frontier: SeenSet) -> GSet:
    """A grow-only set carries no timestamps, so it cannot be filtered.

    Sent whole. That is a real cost of choosing `GSet` over `ORSet`, alongside
    the loss of removal, and it is worth knowing before choosing it for anything
    that grows large.
    """
    del frontier
    return value


def _status_delta(value: StatusLattice, frontier: SeenSet) -> StatusLattice:
    """A status is a single position with no timestamp of its own.

    Always sent, for the same underlying reason the removes are: a frontier
    cannot express "the peer has already seen this position" unless the value
    carries its own HLC.

    The cost is small - a status is a few bytes - but it is not nothing: it
    means a record delta is never truly empty for a schema containing a status
    field, so an idle sync still spends window. `record_delta` therefore drops
    always-sent fields when nothing else changed. -> D-15
    """
    del frontier
    return value


_DELTAS: dict[type, Callable[..., object]] = {
    MeasurementSeries: _series_delta,
    LWWRegister: _register_delta,
    ORSet: _or_set_delta,
    GSet: _g_set_delta,
    StatusLattice: _status_delta,
}


def delta_since(value: object, frontier: SeenSet) -> object:
    """The smallest value whose join with a peer's state completes it."""
    handler = _DELTAS.get(type(value))
    if handler is None:
        raise LatticeError(
            f"no delta rule for {type(value).__name__}. The lattice catalogue is "
            f"closed; adding a type is a spec change."
        )
    return handler(value, frontier)


def is_empty(value: object) -> bool:
    """Does this delta carry anything?

    Used to omit a field from a record delta entirely rather than sending an
    empty container - on a 20 kbps link the field name alone is worth removing.
    """
    if isinstance(value, MeasurementSeries):
        return not value.entries_
    if isinstance(value, LWWRegister):
        return not value.observations_
    if isinstance(value, ORSet):
        return not value.adds and not value.removed_tags
    if isinstance(value, GSet):
        return not value.elements
    # A status always carries its position.
    return False


EMPTY_RECORD_DELTA: dict[str, object] = {}

#: Lattices whose values carry no HLC and therefore cannot be filtered against
#: a peer's frontier. Their deltas are the full value, always.
#:
#: ⚠ An earlier version dropped these when no *filterable* field had changed,
#: to keep an idle sync free. That was wrong in the same direction as the OR-Set
#: bug above: a peer that has never seen the record at all would then never
#: receive its status. The optimisation is unsound without a way to prove the
#: peer already has the value, which is precisely what the missing HLC would
#: provide.
#:
#: So: **correctness over bytes.** An idle sync costs a status and a tombstone
#: set per record it touches. The fix is D-15, not a cleverer filter.
_ALWAYS_SENT = frozenset({"StatusLattice", "GSet", "ORSet"})


def record_delta(
    record: Record, frontier: SeenSet, *, schema: Schema | None = None
) -> dict[str, object]:
    """Fields of a record the peer is missing something from.

    Returns a **sparse** mapping: a field with nothing unseen is omitted
    entirely rather than sent empty. That is the difference between a delta
    that costs bytes proportional to what changed and one that costs bytes
    proportional to the schema.
    """
    active = schema or record.schema
    out: dict[str, object] = {}
    for field in active.fields:
        delta = delta_since(record.state[field.name], frontier)
        if not is_empty(delta):
            out[field.name] = delta
    return out


def frontier_of(record: Record, *, schema: Schema | None = None) -> SeenSet:
    """Every HLC this record contains, as a seen-set.

    Returns a `SeenSet` rather than a `VersionVector`, deliberately: the exact
    set is what a delta may be filtered against. Building a maximum here and
    filtering on it is the bug documented in `dhara.seen`.
    """
    active = schema or record.schema
    vector = SeenSet()
    for field in active.fields:
        value = record.state[field.name]
        if isinstance(value, MeasurementSeries):
            for entry in value.entries_:
                vector = vector.observe(entry.hlc)
        elif isinstance(value, LWWRegister):
            for observation in value.observations_:
                vector = vector.observe(observation.hlc)
        elif isinstance(value, ORSet):
            for tagged in value.adds:
                vector = vector.observe(tagged.tag)
            for tag in value.removed_tags:
                vector = vector.observe(tag)
    return vector


def apply_delta(
    record: Record, delta: dict[str, object], *, schema: Schema | None = None
) -> Record:
    """Merge a sparse delta into a record.

    Omitted fields are left alone, which is what makes the sparse form safe: an
    absent field means "nothing new", never "empty".
    """
    active = schema or record.schema
    if not delta:
        return record
    state = dict(record.state)
    for name, incoming in delta.items():
        state[name] = state[name].join(incoming)  # type: ignore[attr-defined]
    return Record(active, state)


__all__ += ["apply_delta", "frontier_of", "is_empty"]

# Re-exported for callers building deltas by hand in tests.
_ = (Entry, Tagged)
