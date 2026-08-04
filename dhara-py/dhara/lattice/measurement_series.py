"""Append-only measurement series. The conceptual centre of the project.

    A measurement is not a mutable field. It is an event that happened at a
    time.  -- roadmap section 6.2, generalised

A system that models a measurement as a column value has already lost. It has
one slot, so two readings cannot both exist in it, so one must be discarded, so
the only remaining question is which -- and every answer to that question is
wrong. Modelling it as an event removes the question.

**There is no overwrite path.** Not a discouraged one; none. Corrections are new
entries that supersede (C-03), and superseding is an annotation rather than a
deletion.

Two design decisions carry costs that are stated here rather than discovered:

**The dedup key excludes the HLC.** The same physical reading delivered by two
sync paths gets a fresh HLC on the second, so a key including it would admit
exactly the duplicate the key exists to reject (C-02). The cost is C-06: two
genuinely distinct readings agreeing in every recorded attribute collapse to
one, and one of the two weighings leaves no trace. Nothing in the data
distinguishes the two cases, and the alternative manufactures phantom weighings
on every retried sync. Phantom data in a longitudinal record is worse than an
undercount of identical readings.

**Values are integers in minor units**, with the scale declared in the schema --
grams, millimetres, tenths of a centimetre. Floating point in a longitudinal record
is a liability independent of serialisation, and this removes the cross-language
formatting problem rather than encoding around it. Pending confirmation:
DOUBTS.md D-04.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from dhara.hlc import HLC
from dhara.lattice.base import JSONValue, LatticeError

__all__ = ["DEFAULT_DEDUP_KEY", "Entry", "MeasurementSeries"]

#: Roadmap section 6.2. Deliberately excludes the HLC - see the module docstring.
DEFAULT_DEDUP_KEY: tuple[str, ...] = ("taken_at", "recorded_by", "value")


@dataclass(frozen=True, slots=True)
class Entry:
    """One measurement event.

    `recorded_by` is the **actor** who produced the reading, not the device it
    was entered on. It is a provenance fact and it is never rewritten -- not
    when a device changes hands, not during reconciliation. Pending
    confirmation: D-05.
    """

    value: int
    taken_at: str
    recorded_by: str
    hlc: HLC
    supersedes: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise LatticeError(
                f"measurement values are integers in schema-declared minor units, "
                f"got {type(self.value).__name__}. A float here would serialise "
                f"differently in Python and Dart and break canonical form."
            )
        if not self.taken_at:
            raise LatticeError("an entry must record when the measurement was taken")
        if not self.recorded_by:
            raise LatticeError("an entry must record which worker took the measurement")

    @property
    def entry_id(self) -> str:
        """Stable identity for `supersedes` references.

        The HLC is unique per originating device, so its encoding identifies the
        entry without coordination.
        """
        return self.hlc.encode()

    def dedup_key(self, fields: tuple[str, ...] = DEFAULT_DEDUP_KEY) -> tuple[object, ...]:
        return tuple(getattr(self, field) for field in fields)

    def canonical(self) -> tuple[object, ...]:
        return (self.hlc.encode(), self.taken_at, self.recorded_by, self.value, self.supersedes)

    def to_json(self) -> JSONValue:
        out: dict[str, JSONValue] = {
            "value": self.value,
            "taken_at": self.taken_at,
            "recorded_by": self.recorded_by,
            "hlc": self.hlc.to_json(),
        }
        if self.supersedes is not None:
            out["supersedes"] = self.supersedes
        return out

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, dict):
            raise LatticeError(f"entry must be an object, got {type(value).__name__}")
        return cls(
            value=int(value["value"]),  # type: ignore[arg-type]
            taken_at=str(value["taken_at"]),
            recorded_by=str(value["recorded_by"]),
            hlc=HLC.from_json(value["hlc"]),  # type: ignore[arg-type]
            supersedes=None if value.get("supersedes") is None else str(value["supersedes"]),
        )


@dataclass(frozen=True, slots=True)
class MeasurementSeries:
    entries_: frozenset[Entry] = frozenset()
    dedup_on: tuple[str, ...] = DEFAULT_DEDUP_KEY

    @classmethod
    def of(cls, *entries: Entry, dedup_on: tuple[str, ...] = DEFAULT_DEDUP_KEY) -> Self:
        return cls(frozenset(entries), dedup_on)._deduplicated()

    def append(self, entry: Entry) -> Self:
        """Append. There is deliberately no `replace` or `update` counterpart."""
        return type(self)(self.entries_ | {entry}, self.dedup_on)._deduplicated()

    def _deduplicated(self) -> Self:
        """Collapse entries sharing a dedup key to the causally earliest one.

        Choosing the **minimum** HLC rather than the maximum is what makes this a
        semilattice: min is commutative, associative and idempotent, so the
        result does not depend on the order entries arrived in. It is also the
        right answer for C-02 -- the original operation's HLC is the causally
        correct one, and the redelivery's fresh HLC is an artefact of the
        transport.
        """
        best: dict[tuple[object, ...], Entry] = {}
        for entry in self.entries_:
            key = entry.dedup_key(self.dedup_on)
            incumbent = best.get(key)
            if incumbent is None or entry.hlc < incumbent.hlc:
                best[key] = entry
        return type(self)(frozenset(best.values()), self.dedup_on)

    # -- derived views ----------------------------------------------------

    @property
    def entries(self) -> tuple[Entry, ...]:
        """Every entry, ordered by HLC.

        Ordered by causal time rather than by `taken_at`, because `taken_at` is
        worker-supplied and may be wrong (C-05). Display order is the consumer's
        choice; this order is the one that is deterministic on every replica.
        """
        return tuple(sorted(self.entries_, key=lambda e: (e.hlc.pt, e.hlc.c, e.hlc.node_id)))

    @property
    def current(self) -> tuple[Entry, ...]:
        """Entries no other entry supersedes.

        Usually one. More than one means either genuinely independent readings
        (C-01) or a concurrent supersede fork (C-03), and the review layer tells
        those apart.
        """
        superseded = {e.supersedes for e in self.entries_ if e.supersedes is not None}
        return tuple(e for e in self.entries if e.entry_id not in superseded)

    def supersede_forks(self) -> tuple[str, ...]:
        """Entry ids that more than one entry claims to supersede."""
        counts: dict[str, int] = {}
        for entry in self.entries_:
            if entry.supersedes is not None:
                counts[entry.supersedes] = counts.get(entry.supersedes, 0) + 1
        return tuple(sorted(target for target, n in counts.items() if n > 1))

    # -- lattice ----------------------------------------------------------

    def join(self, other: Self) -> Self:
        if self.dedup_on != other.dedup_on:
            raise LatticeError(
                f"cannot join series with different dedup keys: "
                f"{self.dedup_on} vs {other.dedup_on}"
            )
        return type(self)(self.entries_ | other.entries_, self.dedup_on)._deduplicated()

    def leq(self, other: Self) -> bool:
        return self.join(other).canonical() == other.canonical()

    def canonical(self) -> tuple[object, ...]:
        return tuple(sorted(e.canonical() for e in self.entries_))

    def observations(self) -> frozenset[object]:
        """Dedup keys, not entries.

        Two entries sharing a dedup key are one observation by construction, so
        counting entries would make the no-loss law fail on a legitimate dedup.
        """
        return frozenset(e.dedup_key(self.dedup_on) for e in self.entries_)

    def to_json(self) -> JSONValue:
        return [e.to_json() for e in self.entries]

    @classmethod
    def from_json(cls, value: JSONValue, dedup_on: tuple[str, ...] = DEFAULT_DEDUP_KEY) -> Self:
        if not isinstance(value, list):
            raise LatticeError(f"series must decode from a list, got {type(value).__name__}")
        return cls(frozenset(Entry.from_json(v) for v in value), dedup_on)._deduplicated()

    def __len__(self) -> int:
        return len(self.entries_)
