"""Review signals: the engine saying "I merged this, and a human should look."

Roadmap section 6.2's last row -- *genuinely ambiguous -> surface to supervisor
review queue* -- is a feature, not a cop-out. **A sync engine that admits it does
not know is more trustworthy than one that silently guesses.**

Open question Q1 is settled here: **`dhara` emits the signal, the consumer owns
the UI.** "This merge is ambiguous" is a property of the merge, so the engine is
the only thing that can know it. What to *do* about it -- who reviews, what the
screen shows, what counts as a resolution -- is entirely domain policy, and
putting any of it here would violate the dependency rule.

**Signals are derived from merged state, not returned by `join`.**

That is the load-bearing design decision in this module, and it buys two things:

1. `join` stays pure algebra, so the lattice laws are about state and nothing
   else.
2. **Signal determinism becomes a corollary of convergence** rather than a
   separate property needing its own proof. If replicas converge on state -- which
   the laws guarantee -- then anything computed from that state is identical on
   every replica, in every merge order. Phase 2's
   `review_signals_are_deterministic` invariant is then true by construction.

The alternative, accumulating signals during a join, makes them a function of
the *path* rather than the destination: two replicas reaching the same state by
different merge orders would emit different signals, and the Phase 4 conformance
comparison would fail for reasons that have nothing to do with merge semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Mapping

from dhara.lattice import LWWRegister, MeasurementSeries, StatusLattice
from dhara.lattice.base import JSONValue
from dhara.schema import Record, Schema

__all__ = ["SIGNAL_CODES", "ReviewSignal", "detect"]

#: The closed set declared by spec/conflict-catalogue.md. Adding a code
#: requires a catalogue entry that needs it - a signal with no defined meaning
#: is worse than no signal, because a supervisor cannot act on it.
SIGNAL_CODES: frozenset[str] = frozenset(
    {
        "multiple_weights_same_day",
        "superseded_fork",
        "implausible_taken_at",
        "concurrent_demographic_edit",
        "reenrolment_after_graduation",
        "concurrent_status_transition",
        "delete_update_conflict",
        "duplicate_candidate",
        "stale_replica_beyond_retention",
        "replica_state_regressed",
        "duplicate_device_id",
    }
)


@dataclass(frozen=True, slots=True, order=True)
class ReviewSignal:
    """One thing the engine merged but will not adjudicate.

    Carries enough evidence for a human to decide without re-deriving the merge:
    which field, and the competing values with their authors.
    """

    code: str
    field: str
    evidence: tuple[str, ...] = dc_field(default=())

    def __post_init__(self) -> None:
        # Evidence is normalised here rather than at the call sites, so that no
        # call site can get it wrong. It is built from frozensets whose
        # iteration order is not part of their value, and unsorted evidence
        # makes two replicas that reached identical state emit signals that
        # compare unequal - which would fail the Phase 4 conformance comparison
        # for a reason that has nothing to do with merge semantics.
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence)))

        if self.code not in SIGNAL_CODES:
            raise ValueError(
                f"unknown review signal {self.code!r}. The set is closed and is "
                f"declared by spec/conflict-catalogue.md; adding one requires a "
                f"catalogue entry that needs it."
            )

    def to_json(self) -> JSONValue:
        return {"code": self.code, "fields": [self.field]}


def _series_signals(name: str, series: MeasurementSeries) -> list[ReviewSignal]:
    signals: list[ReviewSignal] = []

    # C-01: two measurements for one field on one day. Grouped by the date part
    # of `taken_at` as the schema declares it, never by either device's local
    # clock - two devices can disagree about what day it is.
    #
    # Counts **current** entries only, not every entry. A correction chain
    # (C-03) has three entries on one day and one current value, and it is one
    # actor working carefully rather than two actors disagreeing - the
    # catalogue says C-03 emits nothing. Counting every entry would fire on
    # every correction, which is both wrong and the fastest way to make
    # reviewers stop reading the queue.
    by_day: dict[str, int] = {}
    for entry in series.current:
        day = entry.taken_at.split("T", 1)[0]
        by_day[day] = by_day.get(day, 0) + 1
    if any(count > 1 for count in by_day.values()):
        signals.append(ReviewSignal("multiple_weights_same_day", name))

    # C-03: two entries both claiming to supersede the same one. The state
    # converges, but "current" is then ambiguous and a human should resolve it.
    if series.supersede_forks():
        signals.append(ReviewSignal("superseded_fork", name, series.supersede_forks()))

    return signals


def _register_signals(name: str, register: LWWRegister, review: bool) -> list[ReviewSignal]:
    # C-08, C-12, C-19. Only when the field is declared worth reviewing: a field
    # where concurrent edits are routine and harmless would otherwise fill the
    # queue with noise, and a queue supervisors stop reading is worse than none.
    if review and register.is_contested():
        return [
            ReviewSignal(
                "concurrent_demographic_edit",
                name,
                tuple(f"{o.author}={o.value!r}" for o in register.observations_),
            )
        ]
    return []


def _status_signals(
    name: str, merged: StatusLattice, inputs: tuple[StatusLattice, ...]
) -> list[ReviewSignal]:
    # C-10. The join is total and deterministic, so the engine needs no help -
    # but two actors disagreeing about a record's status is an operational fact.
    for i, a in enumerate(inputs):
        for b in inputs[i + 1 :]:
            if a.is_incomparable_with(b):
                return [
                    ReviewSignal("concurrent_status_transition", name, (a.value, b.value))
                ]
    return []


def detect(
    merged: Record,
    *,
    inputs: tuple[Record, ...] = (),
    schema: Schema | None = None,
) -> tuple[ReviewSignal, ...]:
    """Every signal the merged state warrants, as a sorted tuple.

    Sorted so the result is comparable as a value rather than as a sequence
    whose order happens to match. `inputs` is optional and only needed for the
    signals that are a property of the *operands* rather than of the result --
    incomparable status branches being the only one, since the join collapses
    them and the merged value alone cannot say they were incomparable.
    """
    active = schema or merged.schema
    signals: list[ReviewSignal] = []

    for f in active.fields:
        value = merged.state[f.name]

        if isinstance(value, MeasurementSeries):
            signals.extend(_series_signals(f.name, value))
        elif isinstance(value, LWWRegister):
            signals.extend(_register_signals(f.name, value, f.review_when_contested))
        elif isinstance(value, StatusLattice) and inputs:
            operands = tuple(
                r.state[f.name] for r in inputs if isinstance(r.state[f.name], StatusLattice)
            )
            signals.extend(_status_signals(f.name, value, operands))  # type: ignore[arg-type]

    return tuple(sorted(signals))


def as_json(signals: tuple[ReviewSignal, ...]) -> list[JSONValue]:
    return [s.to_json() for s in signals]


def codes(signals: tuple[ReviewSignal, ...]) -> frozenset[str]:
    """Signal codes as a set.

    Conformance vectors compare signals as a set: signal *order* is not part of
    the contract, signal *content* is.
    """
    return frozenset(s.code for s in signals)


def evidence_by_code(signals: tuple[ReviewSignal, ...]) -> Mapping[str, tuple[str, ...]]:
    return {s.code: s.evidence for s in signals}
