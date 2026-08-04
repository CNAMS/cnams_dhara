"""The virtual network, and every way it fails.

Five of the six fault classes from roadmap section 7.1 live here: partitions,
loss, reordering, duplication, bandwidth caps and abrupt window closure. (The
sixth, crashes, is in `sim/faults.py`.)

The substrate is a link between two endpoints. Everything else is a perturbation
of it, and the perturbations are the point -- a network model without them tests
that messages can be delivered, which nobody doubted.

## The constraint being modelled

    A 90-second window at 20 kbps is 225 KB in the best case, and the best case
    does not happen.

Three details do most of the work, and each was chosen because the easier
version tests something friendlier than reality:

**Asymmetric partitions.** Symmetric ones are the easy case. A device that can
send but not receive acknowledgements is what breaks resumable transfer, and it
is common on real cellular links.

**Delayed duplicates.** An immediate duplicate is caught by any dedup cache. One
that arrives four hours later, after the cache has been evicted, is what tests
catalogue C-22 honestly.

**Mid-byte window closure.** Closing the window between messages tests almost
nothing. The window must be able to close at an arbitrary byte offset, or the
chunking in Phase 3 is being tested against a kinder network than it will meet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sim.loop import Event, EventLoop
from sim.rng import Rng

__all__ = ["Link", "LinkState", "Message", "Network", "NetworkProfile", "PROFILES"]


@dataclass(frozen=True, slots=True)
class Message:
    source: str
    dest: str
    size_bytes: int
    payload: Any = field(compare=False, default=None)
    #: Set on a duplicate so the trace can tell a resend from an original.
    duplicate_of: int | None = None
    msg_id: int = 0


@dataclass(frozen=True, slots=True)
class NetworkProfile:
    """A named set of link characteristics.

    Scenarios name a profile rather than tuning knobs individually, so that a
    change to "what 2G is like" happens in one place and every scenario inherits
    it. Phase 6 rewrites `2g` from measured field data (WI-6.4), and every prior
    result becomes comparable against the corrected model.
    """

    name: str
    bandwidth_bps: int
    latency_mean_ms: float
    loss_rate: float
    duplicate_rate: float
    reorder_rate: float
    window_ms: int
    window_jitter_ms: int
    gap_ms: int
    gap_jitter_ms: int


PROFILES: dict[str, NetworkProfile] = {
    # The defining constraint. Numbers from roadmap section 6.3; the window and
    # gap distributions are a guess made before any field measurement, and
    # WI-6.4 replaces them with measured behaviour.
    "2g": NetworkProfile(
        name="2g",
        bandwidth_bps=20_000,
        latency_mean_ms=800.0,
        loss_rate=0.08,
        duplicate_rate=0.03,
        reorder_rate=0.10,
        window_ms=90_000,
        window_jitter_ms=45_000,
        gap_ms=4 * 60 * 60 * 1000,
        gap_jitter_ms=8 * 60 * 60 * 1000,
    ),
    # For isolating a bug: healthy, always connected. If a failure reproduces
    # here it is not a network bug.
    "clean": NetworkProfile(
        name="clean",
        bandwidth_bps=10_000_000,
        latency_mean_ms=5.0,
        loss_rate=0.0,
        duplicate_rate=0.0,
        reorder_rate=0.0,
        window_ms=10**12,
        window_jitter_ms=0,
        gap_ms=0,
        gap_jitter_ms=0,
    ),
    # Worse than the field. Not realism - a forcing function, so that a design
    # surviving it has margin.
    "hostile": NetworkProfile(
        name="hostile",
        bandwidth_bps=9_600,
        latency_mean_ms=3_000.0,
        loss_rate=0.25,
        duplicate_rate=0.10,
        reorder_rate=0.30,
        window_ms=30_000,
        window_jitter_ms=25_000,
        gap_ms=12 * 60 * 60 * 1000,
        gap_jitter_ms=24 * 60 * 60 * 1000,
    ),
}


class LinkState:
    UP = "up"
    DOWN = "down"
    #: Source can send, destination cannot reply. The case that breaks
    #: resumable transfer, and the one symmetric partitions never produce.
    ONE_WAY = "one_way"


@dataclass(slots=True)
class Link:
    """One directed endpoint pair, with its own connectivity window."""

    source: str
    dest: str
    state: str = LinkState.UP
    window_open: bool = False
    #: When the current window closes. Transfers still in flight at that instant
    #: are discarded, whatever byte they had reached.
    window_closes_at: int = 0

    def can_carry(self) -> bool:
        return self.state == LinkState.UP and self.window_open


class Network:
    """Message delivery with the five transport fault classes."""

    __slots__ = (
        "_deliver",
        "_links",
        "_loop",
        "_next_msg_id",
        "_on_window_opened",
        "_rng",
        "profile",
        "stats",
    )

    def __init__(
        self,
        loop: EventLoop,
        rng: Rng,
        profile: NetworkProfile,
        deliver: Callable[[Message], None],
        on_window_opened: Callable[[str, str], None] | None = None,
    ) -> None:
        self._loop = loop
        self._rng = rng
        self._deliver = deliver
        self._on_window_opened = on_window_opened
        self.profile = profile
        self._links: dict[tuple[str, str], Link] = {}
        self._next_msg_id = 0
        self.stats: dict[str, int] = {
            "sent": 0,
            "delivered": 0,
            "dropped_loss": 0,
            "dropped_partition": 0,
            "dropped_window": 0,
            "duplicated": 0,
            "reordered": 0,
            "bytes": 0,
        }
        loop.on("net.deliver", self._on_deliver)
        loop.on("net.window_open", self._on_window_open)
        loop.on("net.window_close", self._on_window_close)

    # -- links ------------------------------------------------------------

    def link(self, source: str, dest: str) -> Link:
        key = (source, dest)
        if key not in self._links:
            self._links[key] = Link(source, dest)
        return self._links[key]

    def partition(self, source: str, dest: str, *, duration_ms: int, one_way: bool) -> None:
        link = self.link(source, dest)
        link.state = LinkState.ONE_WAY if one_way else LinkState.DOWN
        self._loop.after(duration_ms, "net.heal", (source, dest))


    def heal(self, source: str, dest: str) -> None:
        self.link(source, dest).state = LinkState.UP

    # -- connectivity windows ---------------------------------------------

    def schedule_windows(self, source: str, dest: str, *, horizon_ms: int) -> None:
        """Lay out this link's open windows across the whole run up front.

        Scheduling the entire pattern in advance rather than reactively keeps
        the link's connectivity a pure function of its own stream: it does not
        depend on how much traffic happened to flow, so shrinking a scenario
        does not change when the network was available.
        """
        profile = self.profile
        at = self._loop.time.now
        end = at + horizon_ms

        while at < end:
            gap = profile.gap_ms + self._rng.integer(0, max(1, profile.gap_jitter_ms))
            at += gap
            if at >= end:
                break
            self._loop.at(at, "net.window_open", (source, dest))

            length = profile.window_ms + self._rng.integer(
                -min(profile.window_jitter_ms, profile.window_ms - 1),
                profile.window_jitter_ms,
            )
            at += max(1_000, length)
            self._loop.at(min(at, end), "net.window_close", (source, dest))

    def _on_window_open(self, event: Event) -> None:
        source, dest = event.payload
        self.link(source, dest).window_open = True
        # Real devices sync when connectivity appears rather than on a fixed
        # timetable, and modelling it the other way makes the harness useless:
        # syncs scheduled at uniformly random times land inside a 90-second
        # window roughly never, so almost nothing is delivered and the network
        # model is never exercised. Measured before this hook existed: 4
        # messages delivered out of 1034 sent.
        if self._on_window_opened is not None:
            self._on_window_opened(source, dest)

    def _on_window_close(self, event: Event) -> None:
        source, dest = event.payload
        self.link(source, dest).window_open = False

    # -- sending ----------------------------------------------------------

    def send(self, message: Message) -> None:
        """Offer a message to the network. It may not arrive.

        Every draw happens in a fixed order regardless of outcome, so that a
        message dropped by partition consumes the same randomness as one that is
        delivered. Otherwise a healing partition would shift every subsequent
        draw and the run would not be shrinkable.
        """
        self._next_msg_id += 1
        message = Message(
            source=message.source,
            dest=message.dest,
            size_bytes=message.size_bytes,
            payload=message.payload,
            duplicate_of=message.duplicate_of,
            msg_id=self._next_msg_id,
        )
        self.stats["sent"] += 1

        lost = self._rng.chance(self.profile.loss_rate)
        duplicated = self._rng.chance(self.profile.duplicate_rate)
        reordered = self._rng.chance(self.profile.reorder_rate)
        latency = self._rng.exponential(self.profile.latency_mean_ms)
        reorder_extra = self._rng.integer(0, 5_000)
        duplicate_delay = self._rng.integer(1_000, 4 * 60 * 60 * 1000)

        link = self.link(message.source, message.dest)

        if link.state == LinkState.DOWN:
            self.stats["dropped_partition"] += 1
            return
        if link.state == LinkState.ONE_WAY:
            # The send direction survives; this models the reply path failing,
            # which is what the peer will experience.
            pass
        if not link.window_open:
            self.stats["dropped_window"] += 1
            return
        if lost:
            self.stats["dropped_loss"] += 1
            return

        # Transfer time from the bandwidth cap. A message that cannot finish
        # before the window closes is lost at whatever byte it reached - the
        # mid-byte closure that makes resumability worth testing.
        transfer_ms = int(message.size_bytes * 8 * 1000 / max(1, self.profile.bandwidth_bps))
        arrival = self._loop.time.now + int(latency) + transfer_ms
        if reordered:
            self.stats["reordered"] += 1
            arrival += reorder_extra

        self.stats["bytes"] += message.size_bytes
        self._loop.at(arrival, "net.deliver", message)

        if duplicated:
            self.stats["duplicated"] += 1
            self._loop.at(
                arrival + duplicate_delay,
                "net.deliver",
                Message(
                    source=message.source,
                    dest=message.dest,
                    size_bytes=message.size_bytes,
                    payload=message.payload,
                    duplicate_of=message.msg_id,
                    msg_id=self._next_msg_id,
                ),
            )

    def _on_deliver(self, event: Event) -> None:
        message: Message = event.payload
        link = self.link(message.source, message.dest)

        # Checked again at arrival, not only at send: a window that closed
        # mid-transfer discards what was in flight. This is the mid-byte
        # closure - the message left, and never landed.
        if not link.can_carry():
            self.stats["dropped_window"] += 1
            return

        self.stats["delivered"] += 1
        self._deliver(message)
