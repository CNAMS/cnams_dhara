"""Every seed the simulator has ever failed on, forever.

Each bug the harness finds becomes a permanent fast test. The corpus grows by
one line per bug and runs in seconds, which is what makes it sustainable - and
by month four it is the most valuable file in the repository.

A seed here is not just a regression guard. It is a record of something the
harness proved it could catch, which is the same evidence the deliberate-bug
experiment provides, accumulated over time instead of injected on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.scenario import Simulation, generate

pytestmark = pytest.mark.sim

CORPUS = Path(__file__).parent / "regressions" / "seeds.txt"


def _corpus() -> list[tuple[int, str]]:
    entries = []
    for line in CORPUS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        seed, preset = line.split()
        entries.append((int(seed), preset))
    return entries


def test_the_corpus_is_parseable() -> None:
    """A corpus that silently fails to load is a suite that passes for the
    wrong reason."""
    assert _corpus(), "regression corpus is empty or unparseable"


@pytest.mark.parametrize("seed,preset", _corpus(), ids=lambda v: str(v))
def test_regression_seed(seed: int, preset: str) -> None:
    result = Simulation(generate(seed, preset)).run()
    assert result.ok, result.summary()
