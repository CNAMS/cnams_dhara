"""Virtual time, and per-device clocks that lie about it.

Global virtual time advances only when the event loop pops an event. Nothing
sleeps, nothing reads a wall clock, and six virtual months run in milliseconds.

Each device's clock is a *view* of global time distorted three ways, because all
three happen on real phones:

    offset   set by hand, wrong from the start, +/- 3 days
    drift    a cheap oscillator gaining or losing seconds per day
    jumps    battery dies, clock resets to a default, later corrects

Device time is a **pure function** of global time and the device's own clock
state. That matters for replay: nothing about a device's clock depends on which
events it happened to process, so a replayed run produces identical timestamps.

This is what `dhara.hlc.Clock`'s injected `physical_time` callable exists for.
Without it, none of the clock-skew scenarios in the catalogue -- C-15's
three-day lag, C-16's jump forward and back -- would be expressible at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.rng import Rng

__all__ = ["DeviceClock", "Jump", "VirtualTime", "THREE_DAYS_MS"]

THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000
ONE_DAY_MS = 24 * 60 * 60 * 1000

#: A fixed epoch, so traces from different runs are comparable by eye.
EPOCH_MS = 1_800_000_000_000


class VirtualTime:
    """Global simulated time. Advanced only by the event loop."""

    __slots__ = ("_now",)

    def __init__(self, start: int = EPOCH_MS) -> None:
        self._now = start

    @property
    def now(self) -> int:
        return self._now

    def advance_to(self, when: int) -> None:
        if when < self._now:
            raise ValueError(
                f"virtual time cannot go backwards: {self._now} -> {when}. "
                f"An event was scheduled in the past, which means a delay was "
                f"computed as negative somewhere."
            )
        self._now = when


@dataclass(frozen=True, slots=True)
class Jump:
    """A discrete clock correction at a point in global time."""

    at: int
    delta_ms: int


@dataclass(slots=True)
class DeviceClock:
    """One device's view of time: offset, drift, and scheduled jumps."""

    device_id: str
    offset_ms: int = 0
    #: Milliseconds gained or lost per simulated day.
    drift_ms_per_day: int = 0
    jumps: tuple[Jump, ...] = ()
    _time: VirtualTime = field(repr=False, default_factory=VirtualTime)

    def read(self) -> int:
        """This device's current wall-clock reading, in epoch milliseconds.

        Pure in global time: the same global time always yields the same
        reading, whatever the device has been doing. Clamped at zero because
        `HLC` rejects negative physical time, and a device whose clock is set
        before the epoch is a different problem than the one being modelled.
        """
        now = self._time.now
        elapsed_days = (now - EPOCH_MS) / ONE_DAY_MS
        drift = int(self.drift_ms_per_day * elapsed_days)
        jumped = sum(j.delta_ms for j in self.jumps if j.at <= now)
        return max(0, now + self.offset_ms + drift + jumped)

    def __call__(self) -> int:
        """So a `DeviceClock` can be passed straight to `dhara.hlc.Clock`."""
        return self.read()


def make_device_clock(
    device_id: str,
    rng: Rng,
    time: VirtualTime,
    *,
    horizon_ms: int,
    hostile: bool = True,
    synchronised: bool = False,
) -> DeviceClock:
    """Generate a device clock from a seeded stream.

    Every draw happens unconditionally, in a fixed order, even when the result
    is discarded. Skipping a draw when `hostile` is false would shift every
    subsequent value in the stream, so a scenario's shape would change when a
    knob is tuned rather than when the seed changes.

    ⚠ `synchronised` exists because aggressive skew **suppresses** a whole bug
    class. With every device's clock offset by a random amount within +/- 3
    days, two devices essentially never issue timestamps with the same physical
    millisecond - so the `node_id` tiebreak that makes the total order total
    almost never actually breaks a tie, and a mutation removing it survives
    indefinitely.

    Some centres do have phones with correct time. Modelling that is both more
    realistic and the only way ties occur often enough to test.
    """
    offset = rng.integer(-THREE_DAYS_MS, THREE_DAYS_MS)
    drift = rng.integer(-5_000, 5_000)
    jump_count = rng.integer(0, 2)
    jumps = tuple(
        Jump(
            at=EPOCH_MS + rng.integer(0, max(1, horizon_ms)),
            delta_ms=rng.integer(-2 * ONE_DAY_MS, 2 * ONE_DAY_MS),
        )
        for _ in range(jump_count)
    )

    if not hostile or synchronised:
        # A quiet or synchronised clock still consumed the same draws above.
        return DeviceClock(device_id, 0, 0, (), time)

    return DeviceClock(device_id, offset, drift, jumps, time)
