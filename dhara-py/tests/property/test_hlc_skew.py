"""HLC ordering under +/- 3 days of clock skew.

Phase 1 exit criterion: *HLC ordering correct under +/- 3 days of simulated
skew.* Roadmap section 6.1 is blunt about why this one matters -- "this is where
most homegrown sync layers quietly corrupt themselves."

The property that must hold is narrow and absolute:

    if event A causally precedes event B, then hlc(A) < hlc(B)

regardless of what any device's wall clock says. The failure it rules out is
not a crash. It is a device three days behind losing every conflict it
participates in, for three days, systematically, with nothing anywhere
reporting an error.
"""

from __future__ import annotations

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from dhara.hlc import HLC, Clock

import pytest

pytestmark = pytest.mark.property

THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000
BASE_TIME = 1_800_000_000_000  # a fixed epoch, so runs are comparable

# Offsets are drawn across the full +/- 3 day range, with the extremes and zero
# included explicitly. Hypothesis will find the extremes eventually; naming them
# means the first run tests them.
skew_ms = st.one_of(
    st.just(0),
    st.just(THREE_DAYS_MS),
    st.just(-THREE_DAYS_MS),
    st.integers(min_value=-THREE_DAYS_MS, max_value=THREE_DAYS_MS),
)

node_ids = st.sampled_from(["dev_a", "dev_b", "dev_c", "dev_d"])


class SkewedClock:
    """A device clock at a fixed offset from true time, that can also drift."""

    def __init__(self, offset_ms: int) -> None:
        self.offset = offset_ms
        self.true_now = BASE_TIME

    def tick(self, ms: int = 1) -> None:
        self.true_now += ms

    def __call__(self) -> int:
        # Clamped at zero: a device whose clock is set before the epoch is a
        # different problem, and a negative physical time is rejected by HLC.
        return max(0, self.true_now + self.offset)


@given(offsets=st.lists(skew_ms, min_size=2, max_size=4), n_events=st.integers(2, 40))
@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_causal_precedence_implies_hlc_ordering(offsets: list[int], n_events: int) -> None:
    """The core property. A causal chain across skewed devices stays ordered.

    Each event is sent by one device after receiving the previous event, so the
    chain is causal by construction. Every device's clock is at an arbitrary
    offset within +/- 3 days.
    """
    physicals = [SkewedClock(o) for o in offsets]
    clocks = [Clock(f"dev_{i}", p) for i, p in enumerate(physicals)]

    chain: list[HLC] = [clocks[0].send()]
    for i in range(1, n_events):
        clock = clocks[i % len(clocks)]
        physicals[i % len(physicals)].tick(10)
        chain.append(clock.receive(chain[-1]))

    for earlier, later in zip(chain, chain[1:], strict=False):
        assert earlier < later, (
            f"causal order violated across skewed clocks: {earlier} !< {later}"
        )


@given(
    offset_a=skew_ms,
    offset_b=skew_ms,
    n_rounds=st.integers(1, 30),
)
@settings(max_examples=400, deadline=None)
def test_concurrent_events_are_ordered_identically_on_every_replica(
    offset_a: int, offset_b: int, n_rounds: int
) -> None:
    """Two replicas must sort the same pair of concurrent events the same way.

    This is what the node_id tiebreak buys. Without it, replicas can disagree
    about the order of concurrent operations, apply them differently, and never
    converge -- and no local test can see it.
    """
    pa, pb = SkewedClock(offset_a), SkewedClock(offset_b)
    a, b = Clock("dev_a", pa), Clock("dev_b", pb)

    events: list[HLC] = []
    for _ in range(n_rounds):
        pa.tick(7)
        pb.tick(11)
        events.append(a.send())
        events.append(b.send())

    # Sorting is a pure function of the values, so any two replicas holding the
    # same set necessarily agree. What is asserted here is that the order is
    # *strict* - no two distinct events compare equal, which would leave the
    # relative order down to sort stability and therefore to arrival order.
    ordered = sorted(events)
    for x, y in zip(ordered, ordered[1:], strict=False):
        assert x < y, f"{x} and {y} are not strictly ordered; the order is not total"


@given(offsets=st.lists(skew_ms, min_size=2, max_size=4), n_events=st.integers(2, 60))
@settings(max_examples=300, deadline=None)
def test_the_logical_counter_stays_bounded(offsets: list[int], n_events: int) -> None:
    """The failure that looks like success.

    A device far in the past increments its counter on every message it
    receives. If physical time never advances past the frontier, the counter
    grows without bound -- eventually dominating the sort and, over a long
    offline period, overflowing anything that assumes it is small.

    The bound is messages-per-physical-tick, not total message count. Here
    physical time advances between events, so the counter must stay small.
    """
    physicals = [SkewedClock(o) for o in offsets]
    clocks = [Clock(f"dev_{i}", p) for i, p in enumerate(physicals)]

    last = clocks[0].send()
    for i in range(1, n_events):
        for p in physicals:
            p.tick(1_000)  # a full second between events
        last = clocks[i % len(clocks)].receive(last)

    assert last.c <= len(clocks) + 1, (
        f"logical counter reached {last.c} with physical time advancing; "
        f"it should stay bounded by messages per tick, not total messages"
    )


@given(n_events=st.integers(1, 200))
@settings(max_examples=200, deadline=None)
def test_a_device_three_days_behind_does_not_lose_every_edit(n_events: int) -> None:
    """C-15, stated as the property that matters.

    A worker's phone is three days behind. She works for a week. Her operations
    must not be systematically ordered below a peer's simply because her clock
    is wrong -- once she has observed a peer's event, everything she issues
    afterwards sorts above it.
    """
    behind = SkewedClock(-THREE_DAYS_MS)
    ahead = SkewedClock(0)
    worker = Clock("worker", behind)
    peer = Clock("peer", ahead)

    peer_event = peer.send()
    worker.receive(peer_event)

    for _ in range(n_events):
        behind.tick(1_000)
        assert worker.send() > peer_event, (
            "an operation from a device three days behind sorted below a peer "
            "event it had already observed"
        )


@given(
    forward_jump=st.integers(1, 2 * 24 * 60 * 60 * 1000),
    back_jump=st.integers(1, 2 * 24 * 60 * 60 * 1000),
    n=st.integers(1, 20),
)
@settings(max_examples=300, deadline=None)
def test_a_clock_jumping_forward_then_back_never_reissues_a_timestamp(
    forward_jump: int, back_jump: int, n: int
) -> None:
    """C-16. A dead battery, a wrong default clock, then a network correction.

    The device must never issue an HLC less than or equal to one it has already
    issued, whatever its physical clock does in between.
    """
    physical = SkewedClock(0)
    clock = Clock("dev", physical)

    issued = [clock.send() for _ in range(n)]

    physical.offset = forward_jump
    issued.extend(clock.send() for _ in range(n))

    physical.offset = forward_jump - back_jump
    issued.extend(clock.send() for _ in range(n))

    for earlier, later in zip(issued, issued[1:], strict=False):
        assert earlier < later, f"clock reissued or regressed: {earlier} >= {later}"


@given(remote_offset=skew_ms, local_offset=skew_ms)
@settings(max_examples=400, deadline=None)
def test_receive_always_advances_past_the_remote(
    remote_offset: int, local_offset: int
) -> None:
    """Whatever the two clocks say, observing an event puts us after it."""
    remote_physical = SkewedClock(remote_offset)
    local_physical = SkewedClock(local_offset)
    remote = Clock("remote", remote_physical)
    local = Clock("local", local_physical)

    remote_event = remote.send()
    assume(remote_event.pt >= 0)

    assert local.receive(remote_event) > remote_event
    assert local.send() > remote_event
