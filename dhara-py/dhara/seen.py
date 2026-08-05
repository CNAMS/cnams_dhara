"""What a replica has actually seen — as opposed to what a frontier implies.

## The bug this module exists to fix

A [`VersionVector`][dhara.version_vector.VersionVector] is a **maximum** per
replica. `has_seen(h)` answers "is `h` at or below the highest timestamp I hold
from that replica" — and that is only the same question as "have I received
`h`" if operations from a replica arrive **in order and without gaps**.

They do not. Reordering is one of the six fault classes the simulator injects,
and it is routine on the real network. A peer can hold operation `(2000, 0,
dev_a)` and not hold `(1000, 0, dev_a)`.

Filtering a delta on such a frontier omits the earlier operation. The peer never
receives it, nothing reports an error, and the data is gone — which is precisely
the failure mode this project exists to prevent, arriving through the transport
rather than through a merge.

Found by `test_a_delta_completes_the_peer_exactly`; reproducer in
`tests/unit/test_seen.py`.

## The fix, and its cost

A `SeenSet` holds the operations a replica has **actually observed**, so
`has_seen` answers the question it appears to answer.

The cost is size: an explicit set grows with operation count where a frontier is
one entry per replica. That is affordable at v0.1 scale and is not affordable
across a six-month backlog, which is why the compact form is not abandoned —
it is *demoted* from a correctness mechanism to an optimisation that requires
something it does not yet have.

> **The proper fix is per-replica sequence numbers**: a dense, monotonic counter
> alongside the HLC, so a gap is detectable and a frontier can be advanced
> contiguously. That is what makes the compact form sound, and it is a wire and
> operation-id change. → [DOUBTS.md D-16](../../DOUBTS.md#d-16)

⚠ Until then, **`VersionVector` must not be used to filter a delta.** It remains
correct for what it was built for — summarising, comparing and detecting
concurrency between replicas — and `SeenSet` carries one internally for exactly
that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Self

from dhara.hlc import HLC
from dhara.lattice.base import JSONValue, LatticeError
from dhara.version_vector import VersionVector

__all__ = ["SeenSet"]


@dataclass(frozen=True, slots=True)
class SeenSet:
    """The exact set of operations a replica has observed.

    Immutable, and a lattice like everything else: join is set union, which
    makes "what two replicas have collectively seen" a well-defined value.
    """

    observed: frozenset[str] = frozenset()
    #: Kept alongside for comparison and concurrency detection, which a frontier
    #: does correctly and cheaply. **Never** used for delta filtering.
    frontier: VersionVector = field(default_factory=VersionVector, compare=False)

    @classmethod
    def of(cls, *hlcs: HLC) -> Self:
        return cls.from_hlcs(hlcs)

    @classmethod
    def from_hlcs(cls, hlcs: Iterable[HLC]) -> Self:
        vector = VersionVector()
        encoded: set[str] = set()
        for h in hlcs:
            encoded.add(h.encode())
            vector = vector.observe(h)
        return cls(frozenset(encoded), vector)

    def observe(self, hlc: HLC) -> Self:
        if hlc.encode() in self.observed:
            return self
        return type(self)(
            self.observed | {hlc.encode()}, self.frontier.observe(hlc)
        )

    def has_seen(self, hlc: HLC) -> bool:
        """Exactly what it says.

        No inference from a maximum: an operation counts as seen only if this
        replica actually observed it.
        """
        return hlc.encode() in self.observed

    # -- lattice -----------------------------------------------------------

    def join(self, other: Self) -> Self:
        if other.observed <= self.observed:
            return self
        if self.observed <= other.observed:
            return other
        return type(self)(
            self.observed | other.observed, self.frontier.join(other.frontier)
        )

    def leq(self, other: Self) -> bool:
        return self.observed <= other.observed

    def canonical(self) -> tuple[str, ...]:
        return tuple(sorted(self.observed))

    def observations(self) -> frozenset[object]:
        return frozenset(self.observed)

    # -- wire --------------------------------------------------------------

    def to_json(self) -> JSONValue:
        return sorted(self.observed)

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, list):
            raise LatticeError(
                f"seen-set must decode from a list, got {type(value).__name__}"
            )
        return cls.from_hlcs(HLC.decode(str(v)) for v in value)

    def __len__(self) -> int:
        return len(self.observed)

    def __repr__(self) -> str:
        return f"SeenSet({len(self.observed)} operations)"
