"""Version vectors: what a peer already has, compactly.

    On 2G, the connection is a 90-second window at 20 kbps that dies
    mid-transfer.  -- roadmap section 6.3

That is **225 KB in the best case, and the best case does not happen.** So the
server cannot ask a client to enumerate its state, and the client cannot ask the
server to send everything. Both sides exchange a version vector instead: a map
from replica id to the highest HLC seen from that replica.

A vector is itself a lattice - join is the pointwise maximum - which means it
obeys the same three laws as everything else and can be tested by the same
harness.

## Granularity, and why it is per-replica

A vector per *record* would be exact: the server would know precisely which
records a client is missing. It is also unaffordable. For 300 records across 20
devices that is ~6,000 entries to exchange inside a 225 KB window, before any
actual data moves.

So vectors are **per-replica**. The cost is precision: a coarse vector can say
"you might be missing something from device 4" when in fact you are not, which
sends a few bytes that were not needed. **The error is always in the direction
of sending too much, never of sending too little** - it costs bandwidth, never
correctness.

> The 300-record figure is an assumption that has not been checked against a
> real centre. -> [plan/open-questions.md](../../plan/open-questions.md) Q6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Mapping, Self

from dhara.hlc import HLC
from dhara.lattice.base import JSONValue, LatticeError

__all__ = ["VersionVector"]


@dataclass(frozen=True, slots=True)
class VersionVector:
    """Highest HLC observed from each replica.

    Immutable, like every other value here: a vector that could be mutated
    in place would break the same idempotence the lattices depend on, and would
    do it in the session layer where duplicate delivery is routine.
    """

    frontier: Mapping[str, HLC] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.frontier is None:
            object.__setattr__(self, "frontier", {})
        for node, hlc in self.frontier.items():
            if hlc.node_id != node:
                raise LatticeError(
                    f"vector entry for {node!r} holds an HLC from {hlc.node_id!r}. "
                    f"A frontier entry must be that replica's own timestamp, or "
                    f"the set-difference computation is meaningless."
                )

    @classmethod
    def of(cls, *entries: HLC) -> Self:
        return cls({h.node_id: h for h in entries})

    # -- queries -----------------------------------------------------------

    def get(self, node_id: str) -> HLC | None:
        return self.frontier.get(node_id)

    def has_seen(self, hlc: HLC) -> bool:
        """Is this operation already covered by the frontier?

        The cheap membership test that keeps the seen-set bounded: an operation
        at or below the frontier needs no per-operation lookup at all, which is
        what stops a six-month backlog from exhausting a 2GB device's storage.
        """
        known = self.frontier.get(hlc.node_id)
        return known is not None and hlc <= known

    def dominates(self, other: Self) -> bool:
        """This vector has seen everything `other` has."""
        return all(
            (mine := self.frontier.get(node)) is not None and theirs <= mine
            for node, theirs in other.frontier.items()
        )

    def is_concurrent_with(self, other: Self) -> bool:
        """Neither vector dominates the other: both hold something the other
        lacks."""
        return not self.dominates(other) and not other.dominates(self)

    def missing_from(self, other: Self) -> dict[str, HLC | None]:
        """What `other` has that this vector does not.

        Returns each replica whose frontier this vector trails, with the point
        it trails from - `None` meaning "everything from this replica". That is
        precisely the request the pull phase makes.
        """
        gaps: dict[str, HLC | None] = {}
        for node, theirs in other.frontier.items():
            mine = self.frontier.get(node)
            if mine is None:
                gaps[node] = None
            elif mine < theirs:
                gaps[node] = mine
        return gaps

    # -- lattice -----------------------------------------------------------

    def observe(self, hlc: HLC) -> Self:
        """Advance the frontier past one operation."""
        known = self.frontier.get(hlc.node_id)
        if known is not None and hlc <= known:
            return self
        return type(self)({**self.frontier, hlc.node_id: hlc})

    def join(self, other: Self) -> Self:
        """Pointwise maximum.

        Absorption first, exactly as the lattices do it: `join(a, b) == a` when
        `b <= a`, which is the common case when a peer re-sends a vector that
        has not moved.
        """
        if self.dominates(other):
            return self
        if other.dominates(self):
            return other
        merged = dict(self.frontier)
        for node, theirs in other.frontier.items():
            mine = merged.get(node)
            if mine is None or mine < theirs:
                merged[node] = theirs
        return type(self)(merged)

    def leq(self, other: Self) -> bool:
        return other.dominates(self)

    def canonical(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((node, h.encode()) for node, h in self.frontier.items()))

    def observations(self) -> frozenset[object]:
        return frozenset(self.canonical())

    # -- wire --------------------------------------------------------------

    def to_json(self) -> JSONValue:
        """Compact form: node ids are implicit in the HLC's third component.

        Repeating the node id as a key and again inside the timestamp would
        waste roughly a third of the vector's bytes, and a vector is exchanged
        on **every** session before any data moves.
        """
        return [h.to_json() for _, h in sorted(self.frontier.items())]

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, list):
            raise LatticeError(
                f"version vector must decode from a list, got {type(value).__name__}"
            )
        entries = [HLC.from_json(v) for v in value]  # type: ignore[arg-type]
        return cls({h.node_id: h for h in entries})

    def __len__(self) -> int:
        return len(self.frontier)

    def __iter__(self) -> Iterator[tuple[str, HLC]]:
        return iter(sorted(self.frontier.items()))

    def __repr__(self) -> str:
        inner = ", ".join(f"{n}@{h.pt}.{h.c}" for n, h in sorted(self.frontier.items()))
        return f"VersionVector({inner})"
