"""The deliberate-bug experiment, as a test.

    A harness that never fails is a harness that is not testing anything.
    -- roadmap section 7.1

This is the most important test file in the repository. Everything else asserts
that the code is right; this asserts that **the harness could tell if it were
not.**

It runs a reduced seed budget so it fits the push pipeline. The full budget runs
nightly, because harness sensitivity decays silently: a refactor that makes the
scenario generator less adversarial breaks no test except this one.
"""

from __future__ import annotations

import pytest

from sim.faults import MUTATIONS, Mutation, apply_mutation
from sim.scenario import Simulation, generate

pytestmark = [pytest.mark.sim, pytest.mark.slow]

#: Enough to catch every detectable mutation with margin, small enough for the
#: push pipeline. The nightly run uses the full 1,000.
PUSH_BUDGET = 40

DETECTABLE = [m for m in MUTATIONS.values() if m.detectable_by_simulation]
BLIND = [m for m in MUTATIONS.values() if not m.detectable_by_simulation]


def _first_failing_seed(key: str, budget: int) -> tuple[int, set[str]] | None:
    with apply_mutation(key):
        for seed in range(1, budget + 1):
            result = Simulation(generate(seed)).run()
            if not result.ok:
                return seed, {v.invariant for v in result.violations}
    return None


def test_a_clean_sweep_finds_nothing() -> None:
    """The control.

    Without it, a harness that failed on everything would be indistinguishable
    from one that catches everything.
    """
    for seed in range(1, PUSH_BUDGET + 1):
        result = Simulation(generate(seed)).run()
        assert result.ok, f"unmutated seed {seed} failed:\n{result.summary()}"


@pytest.mark.parametrize("mutation", DETECTABLE, ids=lambda m: m.key)
def test_mutation_is_detected(mutation: Mutation) -> None:
    found = _first_failing_seed(mutation.key, PUSH_BUDGET)
    assert found is not None, (
        f"{mutation.key} ({mutation.title}) survived {PUSH_BUDGET} seeds.\n"
        f"Expected to be caught by {mutation.caught_by}.\n"
        f"This usually means the scenario generator has stopped producing the "
        f"concurrency this mutation needs - fix the generator, not the invariant."
    )


@pytest.mark.parametrize("mutation", BLIND, ids=lambda m: m.key)
def test_known_blind_spot_stays_blind(mutation: Mutation) -> None:
    """Assert the documented blind spots remain blind.

    Not a waiver. If one starts being caught, either the recorded analysis was
    wrong or something meaningful changed about the execution model, and both
    are worth being told about rather than quietly absorbing.
    """
    found = _first_failing_seed(mutation.key, PUSH_BUDGET)
    assert found is None, (
        f"{mutation.key} is documented as undetectable by simulation but was "
        f"caught at seed {found[0]} by {sorted(found[1])}.\n"
        f"Recorded reason: {mutation.blind_spot_reason}\n"
        f"Update the reason, or promote it to a detectable mutation."
    )


def test_every_blind_spot_documents_itself() -> None:
    """A blind spot with no stated reason is an excuse.

    The write-up is only credible if the limits are specific, so the data
    structure requires them rather than trusting prose to keep up.
    """
    for mutation in BLIND:
        assert mutation.blind_spot_reason, f"{mutation.key} has no reason recorded"
        assert mutation.compensating_control, (
            f"{mutation.key} has no compensating control; a blind spot with "
            f"nothing else covering it is an untested behaviour, not a limit"
        )


def test_compensating_controls_actually_catch_the_blind_spots() -> None:
    """The claim that a unit test covers M3 is checked, not asserted.

    Otherwise a compensating control is a sentence in a docstring - exactly the
    kind of unverified reassurance this project exists to avoid.
    """
    from dhara.hlc import HLC

    with apply_mutation("M3"):
        a, b = HLC(5, 3, "dev_a"), HLC(5, 3, "dev_b")
        assert (a < b) == (b < a), (
            "M3 should collapse the total order; if it does not, the control "
            "below is testing nothing"
        )

    a, b = HLC(5, 3, "dev_a"), HLC(5, 3, "dev_b")
    assert (a < b) != (b < a), "unmutated ordering must be total"
