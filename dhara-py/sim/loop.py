"""The event loop.

A priority queue of scheduled events, ordered by `(at, seq)`. Single-threaded,
virtual time only, nothing sleeps. See ADR-0007.

The `seq` tiebreak is load-bearing. Without it, two events at the same virtual
millisecond are ordered by whatever the heap does with equal keys -- which is
unspecified for equal tuples containing incomparable payloads, and unstable
across insertions. The run would then be non-reproducible in exactly the
situations that matter most: simultaneous delivery, simultaneous partition
healing, a crash landing on the same tick as a sync.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from sim.clock import VirtualTime

__all__ = ["Event", "EventLoop"]

Handler = Callable[["Event"], None]


@dataclass(frozen=True, slots=True, order=True)
class Event:
    at: int
    seq: int
    kind: str = field(compare=False)
    payload: Any = field(compare=False, default=None)


class EventLoop:
    """Deterministic discrete-event scheduler over virtual time."""

    __slots__ = ("_handlers", "_heap", "_next_seq", "_processed", "time")

    def __init__(self, time: VirtualTime) -> None:
        self.time = time
        self._heap: list[Event] = []
        self._next_seq = 0
        self._handlers: dict[str, Handler] = {}
        self._processed = 0

    @property
    def processed(self) -> int:
        return self._processed

    @property
    def pending(self) -> int:
        return len(self._heap)

    def on(self, kind: str, handler: Handler) -> None:
        if kind in self._handlers:
            raise ValueError(f"duplicate handler for event kind {kind!r}")
        self._handlers[kind] = handler

    def at(self, when: int, kind: str, payload: Any = None) -> Event:
        """Schedule at an absolute virtual time."""
        if when < self.time.now:
            raise ValueError(
                f"cannot schedule {kind!r} at {when}, which is before now "
                f"({self.time.now}). Some delay was computed as negative."
            )
        event = Event(at=when, seq=self._next_seq, kind=kind, payload=payload)
        self._next_seq += 1
        heapq.heappush(self._heap, event)
        return event

    def after(self, delay: int, kind: str, payload: Any = None) -> Event:
        return self.at(self.time.now + max(0, delay), kind, payload)

    def run(self, *, until: int | None = None, max_events: int = 5_000_000) -> None:
        """Drain the queue, or run until a deadline.

        `max_events` is a runaway guard, not a tuning knob. A scenario that
        schedules events faster than it drains them would otherwise hang a
        million-schedule sweep on one bad seed, and a hung sweep is
        indistinguishable from a slow one until someone checks.
        """
        while self._heap:
            if until is not None and self._heap[0].at > until:
                self.time.advance_to(until)
                return

            event = heapq.heappop(self._heap)
            self.time.advance_to(event.at)

            handler = self._handlers.get(event.kind)
            if handler is None:
                raise KeyError(f"no handler registered for event kind {event.kind!r}")
            handler(event)

            self._processed += 1
            if self._processed > max_events:
                raise RuntimeError(
                    f"event budget of {max_events} exhausted at virtual time "
                    f"{self.time.now}; the scenario is probably scheduling faster "
                    f"than it drains"
                )

        if until is not None:
            self.time.advance_to(until)

    def drain(self) -> Iterator[Event]:
        """Pop events without dispatching. For tests of the loop itself."""
        while self._heap:
            event = heapq.heappop(self._heap)
            self.time.advance_to(event.at)
            yield event
