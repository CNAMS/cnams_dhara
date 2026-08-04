"""Hybrid logical clocks.

Two devices, both offline for a week, both with wall clocks a worker set by
hand. Wall-clock timestamps are worthless for ordering: a device three days
behind loses every conflict it participates in, for three days, systematically
and silently. The worker did her job; the system discards her work and neither
of them can tell.

An HLC fuses a Lamport counter with physical time. Causal ordering survives
arbitrary clock skew, and the value still sorts roughly chronologically for
human display. See spec/conflict-catalogue.md C-15 and C-16.

Two properties this module must have, both of which are easy to lose:

**No wall-clock reads.** Physical time arrives as an injected callable. In
production that is ``time.time``; in simulation it is virtual time under the
seed's control. Without this, clock-skew scenarios are not expressible at all
and the simulator cannot test the thing it exists to test.

**A total order that is identical on every replica.** Ties break on ``node_id``.
Without that tiebreak two replicas can order the same pair of events
differently and never converge — and every local test still passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

__all__ = ["HLC", "Clock", "PhysicalTime"]

#: Milliseconds since the Unix epoch. An integer, never a float: float
#: milliseconds lose precision above 2**53 and, worse, format differently in
#: Python and Dart, which would break canonical serialisation.
PhysicalTime = int

#: Injected source of physical time. `time.time` in production, virtual time in
#: simulation.
ClockSource = Callable[[], PhysicalTime]

#: Width of the zero-padded physical-time field in the encoded form. 13 digits
#: covers milliseconds until the year 2286; 16 leaves headroom without making
#: every timestamp on the wire wasteful.
_PT_WIDTH: Final = 16
_C_WIDTH: Final = 10


@dataclass(frozen=True, order=False, slots=True)
class HLC:
    """A point in causal time: physical time, logical counter, and origin.

    Immutable and hashable, because HLCs are used as dictionary keys in version
    vectors and as elements of tag sets in the OR-Set. A mutable timestamp in a
    set is a corruption waiting for its moment.

    Ordering is lexicographic on ``(pt, c, node_id)``. The ``node_id`` component
    is not decoration: it is what makes the order *total*, so that two replicas
    presented with the same pair of concurrent events always agree which one
    sorts first.
    """

    pt: PhysicalTime
    c: int
    node_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.pt, int) or isinstance(self.pt, bool):
            raise TypeError(f"pt must be an int in milliseconds, got {type(self.pt).__name__}")
        if self.pt < 0:
            raise ValueError(f"pt must be non-negative, got {self.pt}")
        if not isinstance(self.c, int) or isinstance(self.c, bool):
            raise TypeError(f"c must be an int, got {type(self.c).__name__}")
        if self.c < 0:
            raise ValueError(f"c must be non-negative, got {self.c}")
        if not self.node_id:
            raise ValueError("node_id must be non-empty; it is the ordering tiebreak")

    # -- ordering ---------------------------------------------------------

    def sort_key(self) -> tuple[int, int, str]:
        """The single definition of HLC order.

        Public and used by every caller that needs to order by causal time -
        the register's current value, the series' entry ordering, the
        comparison operators below. It was written out inline in three places
        before, which is three copies of one rule that can drift apart, and it
        also meant a mutation of the ordering only reached one of them.
        """
        return (self.pt, self.c, self.node_id)

    _key = sort_key

    def __lt__(self, other: HLC) -> bool:
        return self._key() < other._key()

    def __le__(self, other: HLC) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: HLC) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: HLC) -> bool:
        return self._key() >= other._key()

    # -- encoding ---------------------------------------------------------

    def encode(self) -> str:
        """Fixed-width string whose lexicographic order matches value order.

        This is why the store can use an ordinary string index for causal range
        scans, and why two replicas holding the same logical state produce the
        same bytes — which delta computation depends on.

        The node id is appended unpadded because it is the last component; its
        length cannot disturb the ordering of the fields before it.
        """
        return f"{self.pt:0{_PT_WIDTH}d}:{self.c:0{_C_WIDTH}d}:{self.node_id}"

    @classmethod
    def decode(cls, encoded: str) -> HLC:
        pt_s, c_s, node_id = encoded.split(":", 2)
        return cls(pt=int(pt_s), c=int(c_s), node_id=node_id)

    def to_json(self) -> list[object]:
        """Wire and conformance-vector form: ``[pt, c, node_id]``."""
        return [self.pt, self.c, self.node_id]

    @classmethod
    def from_json(cls, value: list[object]) -> HLC:
        if len(value) != 3:
            raise ValueError(f"HLC must be [pt, c, node_id], got {value!r}")
        pt, c, node_id = value
        return cls(pt=int(pt), c=int(c), node_id=str(node_id))  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return f"HLC({self.pt}, {self.c}, {self.node_id!r})"


class Clock:
    """A replica's hybrid logical clock.

    Holds the last timestamp this replica issued or observed. Not thread-safe by
    design: the simulator is single-threaded so that determinism is a property
    of the seed rather than of the OS scheduler, and a lock here would be a lie
    about where concurrency is handled.
    """

    __slots__ = ("_last", "_node_id", "_physical_time")

    def __init__(self, node_id: str, physical_time: ClockSource) -> None:
        if not node_id:
            raise ValueError("node_id must be non-empty; it is the ordering tiebreak")
        self._node_id = node_id
        self._physical_time = physical_time
        self._last = HLC(pt=0, c=0, node_id=node_id)

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def last(self) -> HLC:
        """The most recent timestamp issued or observed. Never regresses."""
        return self._last

    def send(self) -> HLC:
        """Issue a timestamp for a locally originated event.

        Monotonic even when the underlying physical clock moves backwards — a
        battery-dead phone restarting with a wrong clock, then correcting
        (C-16). ``max`` absorbs the regression into the physical component and
        the logical counter carries the ordering.
        """
        pt = max(self._physical_time(), self._last.pt)
        c = self._last.c + 1 if pt == self._last.pt else 0
        self._last = HLC(pt=pt, c=c, node_id=self._node_id)
        return self._last

    def receive(self, remote: HLC) -> HLC:
        """Advance this clock on observing a remote timestamp.

        This is what makes ordering causal rather than chronological: after
        observing ``remote``, everything this replica subsequently issues sorts
        after it, whatever the local wall clock says.

        Four branches, and each one is reachable. They are written out rather
        than collapsed because a subtly wrong branch here is a convergence bug
        that no single-replica test can see.
        """
        pt = max(self._physical_time(), self._last.pt, remote.pt)

        if pt == self._last.pt == remote.pt:
            # Both sides are at the new physical time: take the larger counter
            # and step past it, so this event sorts after both.
            c = max(self._last.c, remote.c) + 1
        elif pt == self._last.pt:
            # Local is at the frontier; the remote is behind. Step our counter.
            c = self._last.c + 1
        elif pt == remote.pt:
            # The remote is ahead. Adopt its counter and step past it.
            c = remote.c + 1
        else:
            # Physical time has advanced beyond both. The counter resets, which
            # is what keeps it bounded by messages-per-tick rather than by total
            # message count.
            c = 0

        self._last = HLC(pt=pt, c=c, node_id=self._node_id)
        return self._last
