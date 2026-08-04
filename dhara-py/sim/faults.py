"""The deliberate-bug experiment.

    Deliberately introduce a known-bad merge -- swap a series append for an
    overwrite -- and confirm the simulator finds it within 1,000 seeds. **A
    harness that never fails is a harness that is not testing anything.**
    Document this experiment; it is the single most credible artifact in the
    repo.  -- roadmap section 7.1

This module is that experiment. It is the reason everything else in `sim/`
exists, and the number it produces -- seeds-to-detection, per mutation -- is the
only evidence that a million passing schedules mean anything.

## Why six mutations and not one

One caught bug shows the harness can catch *that* bug. Six across different
subsystems -- series, register, clock, set, dedup, operation identity -- show it
can catch a *class* of bug.

The seeds-to-detection figures then do double duty as a **calibration signal**.
If M1 is not caught within a handful of seeds, the scenario generator has
stopped producing concurrent edits, and nothing else would report that. A
generator that has gone quiet fails no test; it just stops finding things.

## Why it runs nightly rather than once

Harness sensitivity **decays**. A refactor that makes the generator less
adversarial breaks no test -- except this one. Phase 3 replaces direct state
exchange with real sync sessions (WI-3.11) and Phase 5 puts crypto on the hot
path (WI-5.10); both change what the simulator explores, and both must re-run
this before their results are believed.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Callable

from dhara.hlc import HLC
from dhara.lattice import lww_register, measurement_series, or_set
from dhara.lattice.measurement_series import MeasurementSeries

__all__ = ["MUTATIONS", "Mutation", "apply_mutation"]


@dataclass(frozen=True, slots=True)
class Mutation:
    """A plausible wrong implementation, and which invariant should notice."""

    key: str
    title: str
    #: The invariant expected to catch it. Recorded so a mutation caught by the
    #: *wrong* invariant is visible - that usually means one of the two is
    #: measuring something other than what its name claims.
    caught_by: str
    #: Roadmap section 7.1 sets the bar at 1,000 seeds for the series overwrite.
    #: The others carry their own expectation so a regression is measurable
    #: rather than felt.
    budget: int
    patch: Callable[[], contextlib.AbstractContextManager[None]]
    #: False for mutations this harness **structurally cannot** detect. Not a
    #: waiver: each carries a reason and a compensating control, and the nightly
    #: run asserts they stay undetected - if one starts being caught, either the
    #: analysis was wrong or something meaningful changed, and both are worth
    #: knowing.
    detectable_by_simulation: bool = True
    blind_spot_reason: str = ""
    compensating_control: str = ""


# -- M1: the roadmap's own example ----------------------------------------


@contextlib.contextmanager
def _m1_series_overwrites() -> Iterator[None]:
    """Series join keeps only the incoming state.

    The exact mutation roadmap section 7.1 names. It is a mistake a reasonable
    person makes: "merge means take the newer state" is true for a register and
    catastrophic for an event log.
    """
    original = MeasurementSeries.join

    def broken(self: MeasurementSeries, other: MeasurementSeries) -> MeasurementSeries:
        return MeasurementSeries(other.entries_, self.dedup_on)

    MeasurementSeries.join = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        MeasurementSeries.join = original  # type: ignore[method-assign]


# -- M2: the costume the roadmap warns about ------------------------------


@contextlib.contextmanager
def _m2_register_discards_loser() -> Iterator[None]:
    """LWW register keeps only the winner.

    This is the data-loss bug wearing a design-decision costume. It looks
    correct from every angle that does not ask about history.
    """
    original = lww_register.LWWRegister.join

    def broken(
        self: lww_register.LWWRegister, other: lww_register.LWWRegister
    ) -> lww_register.LWWRegister:
        merged = self.observations_ | other.observations_
        if not merged:
            return type(self)(frozenset())
        winner = max(merged, key=lww_register.Observation.sort_key)
        return type(self)(frozenset({winner}))

    lww_register.LWWRegister.join = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        lww_register.LWWRegister.join = original  # type: ignore[method-assign]


# -- M3: the tiebreak that makes the order total --------------------------


@contextlib.contextmanager
def _m3_hlc_drops_node_tiebreak() -> Iterator[None]:
    """HLC ordering ignores `node_id`.

    Two replicas can then order the same pair of concurrent events differently,
    apply them in different orders, and never converge - while every
    single-replica test still passes.
    """
    original = HLC.sort_key

    def broken(self: HLC) -> tuple[int, int, str]:
        return (self.pt, self.c, "")

    HLC.sort_key = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        HLC.sort_key = original  # type: ignore[method-assign]


@contextlib.contextmanager
def _m3b_encoding_drops_node_id() -> Iterator[None]:
    """`HLC.encode()` omits the node id.

    The variant of M3 that a *simulation* can actually see, and the reason both
    exist.

    M3 breaks `sort_key`, which turns out to be undetectable end to end: this
    design's convergence rests on `encode()`, which carries the node id
    independently, and ties in `max()` resolve identically on every replica
    because they share one process. Breaking `encode()` instead collapses two
    distinct timestamps from different devices into one string, so entry
    identity and canonical form both collide - which is a corruption the
    invariants can see.
    """
    original = HLC.encode

    def broken(self: HLC) -> str:
        return f"{self.pt:016d}:{self.c:010d}:"

    HLC.encode = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        HLC.encode = original  # type: ignore[method-assign]


# -- M4: the one the property suite missed --------------------------------


@contextlib.contextmanager
def _m4_orset_removes_by_element() -> Iterator[None]:
    """OR-Set remove deletes adds instead of recording observed tags.

    Included because Phase 1 found that the entire property suite missed it: the
    strategies built values with the constructor and never called `remove()`.
    It is here to make sure the *simulator* does not have the same blind spot,
    since the simulator drives operations rather than constructing states.
    """
    original = or_set.ORSet.remove

    def broken(self: or_set.ORSet, element: str) -> or_set.ORSet:
        return type(self)(
            frozenset(t for t in self.adds if t.element != element), self.removed_tags
        )

    or_set.ORSet.remove = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        or_set.ORSet.remove = original  # type: ignore[method-assign]


# -- M5: the key that must not include the clock --------------------------


@contextlib.contextmanager
def _m5_dedup_includes_hlc() -> Iterator[None]:
    """Dedup key gains the HLC, so a redelivery is admitted as a new reading.

    Catalogue C-02. Every retried sync then manufactures a phantom measurement,
    which is worse than the duplicate it was trying to avoid.
    """
    original = measurement_series.Entry.dedup_key

    def broken(
        self: measurement_series.Entry,
        fields: tuple[str, ...] = measurement_series.DEFAULT_DEDUP_KEY,
    ) -> tuple[object, ...]:
        return (*(getattr(self, f) for f in fields), self.hlc.encode())

    measurement_series.Entry.dedup_key = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        measurement_series.Entry.dedup_key = original  # type: ignore[method-assign]


# -- M6: operation identity -----------------------------------------------


@contextlib.contextmanager
def _m6_clock_reissues_timestamps() -> Iterator[None]:
    """The clock stops advancing its logical counter within a tick.

    Operation ids are `(device_id, hlc)`, so a reissued timestamp collides and
    one operation is silently discarded as a duplicate of another. This is
    C-24's failure mode reached through a clock bug rather than an id
    collision - and C-24 itself is unreachable by construction, since the
    generator assigns unique device ids.
    """
    from dhara.hlc import Clock

    original = Clock.send

    def broken(self: Clock) -> HLC:
        pt = max(self._physical_time(), self._last.pt)  # type: ignore[attr-defined]
        self._last = HLC(pt=pt, c=0, node_id=self._node_id)  # type: ignore[attr-defined]
        return self._last  # type: ignore[attr-defined]

    Clock.send = broken  # type: ignore[method-assign]
    try:
        yield
    finally:
        Clock.send = original  # type: ignore[method-assign]


MUTATIONS: dict[str, Mutation] = {
    m.key: m
    for m in (
        Mutation("M1", "series join overwrites instead of appending",
                 "no_measurement_lost", 1_000, _m1_series_overwrites),
        Mutation("M2", "lww register discards the loser",
                 "no_observation_lost", 1_000, _m2_register_discards_loser),
        Mutation(
            "M3", "hlc tie-break drops the node id",
            "all_converged", 1_000, _m3_hlc_drops_node_tiebreak,
            detectable_by_simulation=False,
            blind_spot_reason=(
                "A tiebreak bug only diverges replicas if two replicas resolve "
                "the same tie differently. Every join here is a set union, so "
                "ordering does not affect merged state; the only order-sensitive "
                "step is max() over a tied set, and in a single-process "
                "simulation both replicas share the interpreter's hash seeding "
                "and therefore iterate identically. The bug is real in "
                "production, where two devices are two processes - it is "
                "unreachable here by construction of ADR-0007's execution model."
            ),
            compensating_control=(
                "tests/unit/test_hlc.py::test_ordering_is_lexicographic_on_pt_"
                "then_c_then_node catches it directly, and the randomised "
                "PYTHONHASHSEED CI leg covers cross-process iteration order."
            ),
        ),
        Mutation(
            "M3b", "hlc encoding drops the node id",
            "no_measurement_lost", 1_000, _m3b_encoding_drops_node_id,
            detectable_by_simulation=False,
            blind_spot_reason=(
                "Written to be the reachable variant of M3, and it is not. "
                "Collapsing two encodings only corrupts state when every other "
                "field of the two values also matches - and if they all match, "
                "the values are genuinely identical and collapsing them is "
                "correct. Adding synchronised-clock devices so ties actually "
                "occur did not change the result."
            ),
            compensating_control=(
                "tests/unit/test_hlc.py::test_encoding_sorts_lexicographically_"
                "in_value_order and the round-trip tests."
            ),
        ),
        Mutation("M4", "orset remove keys on element, not observed tags",
                 "all_converged", 1_000, _m4_orset_removes_by_element),
        Mutation("M5", "dedup key includes the hlc",
                 "no_measurement_lost", 1_000, _m5_dedup_includes_hlc),
        Mutation("M6", "clock reissues timestamps within a tick",
                 "no_duplicate_operation_ids", 1_000, _m6_clock_reissues_timestamps),
    )
}


def apply_mutation(key: str) -> contextlib.AbstractContextManager[None]:
    """Patch one merge function for the duration of a block.

    Monkey-patching rather than a build flag, deliberately: the mutation must be
    applied to the *same* code the real suite runs, so there is no chance of the
    experiment testing a differently-compiled variant that nobody ships.
    """
    if key not in MUTATIONS:
        raise KeyError(f"unknown mutation {key!r}; known: {sorted(MUTATIONS)}")
    return MUTATIONS[key].patch()
