"""Shrinking, exercised on a real failure rather than a synthetic one.

A failure at seed 4471 with five devices, eighty writes and thirty faults is a
failure nobody debugs. Shrinking turns it into something a person can read in
one screen.

⚠ These tests use a **mutation** to produce the failure, which is the only
honest way to test shrinking on demand: the engine currently has no known bug,
so a genuine failing seed cannot be conjured. Using an injected fault means the
failure is real in every respect that matters to the shrinker - it arises from
the same scenario machinery, through the same invariants - while remaining
reproducible.
"""

from __future__ import annotations

import pytest

from sim.faults import apply_mutation
from sim.runner import _failure, run_seed, shrink

pytestmark = [pytest.mark.sim, pytest.mark.slow]


def _first_failure_under(mutation: str, budget: int = 40):  # type: ignore[no-untyped-def]
    with apply_mutation(mutation):
        for seed in range(1, budget + 1):
            outcome = run_seed(seed)
            if not outcome.ok:
                return _failure(outcome)
    pytest.fail(f"{mutation} produced no failure within {budget} seeds")


def test_shrinking_reduces_a_real_failure() -> None:
    """The scenario gets smaller and still fails the same way."""
    with apply_mutation("M1"):
        failure = _first_failure_under("M1")
        smaller = shrink(failure)

        original = failure.scenario
        assert (
            smaller.devices <= original.devices
            and smaller.writes <= original.writes
            and smaller.records <= original.records
        ), "shrinking produced a larger scenario"

        assert (
            smaller.devices < original.devices
            or smaller.writes < original.writes
            or smaller.records < original.records
            or smaller.horizon_ms < original.horizon_ms
        ), "shrinking reduced nothing at all"


def test_the_shrunk_scenario_still_fails_the_same_invariant() -> None:
    """Same-way matters.

    A shrunk scenario failing a *different* invariant is a different bug, and
    following it leads away from the one being debugged. The shrinker only
    accepts reductions that preserve the original invariant.
    """
    from sim.scenario import Simulation

    with apply_mutation("M1"):
        failure = _first_failure_under("M1")
        smaller = shrink(failure)

        outcome = Simulation(smaller).run()
        assert not outcome.ok, "the shrunk scenario stopped failing"
        assert set(failure.invariants) & {v.invariant for v in outcome.violations}, (
            "the shrunk scenario fails a different invariant than the original"
        )


def test_shrinking_terminates_on_a_passing_scenario() -> None:
    """A failure that does not reproduce must not send the shrinker looping.

    This happens for real: a flaky invariant, or a failure already fixed
    between the sweep and the shrink.
    """
    outcome = run_seed(1)
    assert outcome.ok, "seed 1 should pass unmutated; this test assumes it"

    from sim.runner import Failure

    never_fails = Failure(
        seed=1,
        scenario=outcome.scenario,
        invariants=("all_converged",),
        detail="fabricated",
    )
    result = shrink(never_fails, max_steps=20)
    assert result == never_fails.scenario, (
        "shrinking a scenario that does not reproduce should change nothing"
    )


def test_shrinking_is_bounded() -> None:
    """An unbounded shrink on a rare failure can outlast the sweep that found
    it, which turns a diagnosis into a second wait."""
    with apply_mutation("M1"):
        failure = _first_failure_under("M1")
        smaller = shrink(failure, max_steps=1)
        # One step can change at most one dimension.
        original = failure.scenario
        differences = sum(
            1
            for key in ("devices", "writes", "records", "horizon_ms")
            if getattr(smaller, key) != getattr(original, key)
        )
        assert differences <= 1, f"max_steps=1 changed {differences} dimensions"
