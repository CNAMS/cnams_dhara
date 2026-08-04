"""Unit tests for the hybrid logical clock.

The receive path has four branches and each one gets a test that fails if that
branch alone is broken. That is deliberate: a receive path with one wrong branch
passes every test written against a single replica, and shows up months later as
two replicas that never converge.
"""

from __future__ import annotations

import pytest

from dhara.hlc import HLC, Clock


class FakeClock:
    """A physical clock under the test's control.

    The production source is `time.time`; nothing in `dhara` may read it
    directly. This is the whole reason `Clock` takes a callable.
    """

    def __init__(self, now: int = 1_000) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


# -- HLC value type -------------------------------------------------------


def test_hlc_is_immutable() -> None:
    h = HLC(1, 0, "a")
    with pytest.raises(AttributeError):
        h.pt = 2  # type: ignore[misc]


def test_hlc_is_hashable() -> None:
    """HLCs are dict keys in version vectors and elements of OR-Set tag sets."""
    assert len({HLC(1, 0, "a"), HLC(1, 0, "a"), HLC(1, 0, "b")}) == 2


def test_ordering_is_lexicographic_on_pt_then_c_then_node() -> None:
    assert HLC(1, 0, "a") < HLC(2, 0, "a")
    assert HLC(1, 0, "a") < HLC(1, 1, "a")
    assert HLC(1, 0, "a") < HLC(1, 0, "b")


def test_node_id_breaks_ties_so_the_order_is_total() -> None:
    """Without this, two replicas can order the same pair differently.

    They then apply concurrent operations in different orders, reach different
    states, and never converge - while every local test passes.
    """
    a, b = HLC(5, 3, "device_a"), HLC(5, 3, "device_b")
    assert a != b
    assert (a < b) != (b < a)
    assert sorted([b, a]) == [a, b]


def test_ordering_is_transitive_and_irreflexive() -> None:
    a, b, c = HLC(1, 0, "a"), HLC(1, 1, "a"), HLC(2, 0, "a")
    assert a < b < c
    assert a < c
    assert not a < a


def test_rejects_non_integer_physical_time() -> None:
    """Float milliseconds lose precision and format differently across
    languages, which would break canonical serialisation with Dart."""
    with pytest.raises(TypeError):
        HLC(1.5, 0, "a")  # type: ignore[arg-type]


def test_rejects_bool_because_bool_is_an_int_in_python() -> None:
    with pytest.raises(TypeError):
        HLC(True, 0, "a")  # type: ignore[arg-type]


def test_rejects_negative_components() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        HLC(-1, 0, "a")
    with pytest.raises(ValueError, match="non-negative"):
        HLC(1, -1, "a")


def test_rejects_empty_node_id() -> None:
    with pytest.raises(ValueError, match="tiebreak"):
        HLC(1, 0, "")


# -- encoding -------------------------------------------------------------


def test_encoding_sorts_lexicographically_in_value_order() -> None:
    """Fixed width is what lets the store use a plain string index for causal
    range scans, and what makes two replicas with the same state produce the
    same bytes."""
    values = [HLC(2, 0, "a"), HLC(1, 10, "a"), HLC(1, 2, "a"), HLC(1, 2, "b")]
    by_value = sorted(values)
    by_encoding = sorted(values, key=lambda h: h.encode())
    assert by_value == by_encoding


def test_encoding_round_trips() -> None:
    for h in (HLC(0, 0, "a"), HLC(10**12, 999, "device-1")):
        assert HLC.decode(h.encode()) == h


def test_node_id_containing_a_colon_round_trips() -> None:
    """The node id is the last field and is split off with maxsplit, so a colon
    inside it is harmless. Asserted rather than assumed."""
    h = HLC(1, 0, "a:b:c")
    assert HLC.decode(h.encode()) == h


def test_json_round_trips() -> None:
    h = HLC(123, 4, "n")
    assert h.to_json() == [123, 4, "n"]
    assert HLC.from_json(h.to_json()) == h


def test_json_rejects_wrong_arity() -> None:
    with pytest.raises(ValueError, match=r"\[pt, c, node_id\]"):
        HLC.from_json([1, 2])  # type: ignore[list-item]


# -- send -----------------------------------------------------------------


def test_send_advances_the_counter_when_physical_time_is_frozen() -> None:
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    # The first send starts a fresh physical tick (last.pt is 0), so its
    # counter is 0. Subsequent sends within the same tick step it.
    assert [clock.send().c for _ in range(3)] == [0, 1, 2]


def test_send_resets_the_counter_when_physical_time_advances() -> None:
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    clock.send()
    physical.now = 2_000
    issued = clock.send()
    assert (issued.pt, issued.c) == (2_000, 0)


def test_send_is_strictly_monotonic_over_many_calls() -> None:
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    issued = [clock.send() for _ in range(1_000)]
    assert all(a < b for a, b in zip(issued, issued[1:], strict=False))


def test_send_stays_monotonic_when_the_physical_clock_jumps_backwards() -> None:
    """C-16. A phone whose battery died restarts with a wrong clock, then
    corrects. It must never issue a timestamp it has already issued."""
    physical = FakeClock(10_000)
    clock = Clock("a", physical)
    before = clock.send()

    physical.now = 1_000  # three hours backwards
    after = clock.send()

    assert after > before
    assert after.pt == before.pt, "the physical component must not regress"
    assert after.c == before.c + 1, "the logical counter absorbs the regression"


def test_send_never_reads_the_wall_clock() -> None:
    """The injected source is the only source. If this ever fails, the
    simulator's clock-skew scenarios are silently not being tested."""
    calls = 0

    def counting() -> int:
        nonlocal calls
        calls += 1
        return 5_000

    Clock("a", counting).send()
    assert calls == 1


# -- receive: one test per branch -----------------------------------------


def test_receive_branch_all_three_equal() -> None:
    """pt == last.pt == remote.pt: take max counter and step past it."""
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    clock.send()  # last = (1000, 0)
    got = clock.receive(HLC(1_000, 5, "b"))
    assert (got.pt, got.c) == (1_000, 6)


def test_receive_branch_local_is_at_the_frontier() -> None:
    """pt == last.pt only: the remote is behind; step our own counter."""
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    clock.send()  # last = (1000, 0)
    got = clock.receive(HLC(500, 9, "b"))
    assert (got.pt, got.c) == (1_000, 1)


def test_receive_branch_remote_is_ahead() -> None:
    """pt == remote.pt only: adopt the remote counter and step past it."""
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    clock.send()
    got = clock.receive(HLC(9_000, 4, "b"))
    assert (got.pt, got.c) == (9_000, 5)


def test_receive_branch_physical_time_exceeds_both() -> None:
    """pt greater than both: the counter resets, which is what keeps it
    bounded by messages-per-tick rather than by total message count."""
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    clock.send()
    physical.now = 50_000
    got = clock.receive(HLC(9_000, 4, "b"))
    assert (got.pt, got.c) == (50_000, 0)


def test_receive_advances_past_a_future_timestamp() -> None:
    """A device two days ahead does not poison ordering: everything issued
    after observing it still sorts after it (C-16)."""
    physical = FakeClock(1_000)
    clock = Clock("a", physical)
    future = HLC(1_000 + 2 * 86_400_000, 0, "b")
    assert clock.receive(future) > future
    assert clock.send() > future


def test_causality_survives_a_message_received_before_its_local_successor() -> None:
    """The property everything else rests on: if a causally precedes b, then
    hlc(a) < hlc(b), regardless of the two devices' wall clocks."""
    a_physical, b_physical = FakeClock(10_000), FakeClock(1_000)  # b is 9s behind
    a, b = Clock("a", a_physical), Clock("b", b_physical)

    e1 = a.send()
    b.receive(e1)
    e2 = b.send()  # causally after e1, on a clock that is behind

    assert e1 < e2


def test_receive_does_not_regress_on_a_stale_remote() -> None:
    physical = FakeClock(5_000)
    clock = Clock("a", physical)
    high = clock.send()
    got = clock.receive(HLC(1, 0, "b"))
    assert got > high
