"""Deterministic simulation testing for dhara.

N virtual devices and a virtual server in a single process, with a seeded PRNG
driving everything non-deterministic. Invariants are asserted after every
schedule. Seed 4471 fails, and seed 4471 replays exactly.

    from sim.runner import run_seed
    result = run_seed(4471)

The point is not that a million schedules pass. It is that the harness can be
shown to fail when the merge logic is wrong -- which is what
`docs/deliberate-bug-experiment.md` demonstrates. A harness that never fails is
a harness that is not testing anything.

Execution model: ADR-0007.
"""
