"""Run the shared HLC conformance vectors.

These are the same files the Dart implementation will run in Phase 4. If the two
disagree, the build fails - that is the whole point of writing them as data
rather than as tests in either language.
"""

from __future__ import annotations

import pytest

from dhara.conformance import Vector, VectorFailure, load_vectors, run_hlc_vector

pytestmark = pytest.mark.conformance

HLC_VECTORS = load_vectors(kind="hlc")


def test_there_are_hlc_vectors_to_run() -> None:
    """A conformance suite that silently runs nothing passes for the wrong
    reason. This is the guard against a path change quietly emptying it."""
    assert HLC_VECTORS, "no hlc vectors found under spec/conformance/hlc/"


@pytest.mark.parametrize("vector", HLC_VECTORS, ids=lambda v: v.name)
def test_hlc_vector(vector: Vector) -> None:
    run_hlc_vector(vector)


def test_every_vector_names_a_catalogue_entry() -> None:
    """A vector covering nothing in the catalogue tests behaviour nobody
    decided was correct."""
    for vector in HLC_VECTORS:
        assert vector.catalogue, f"{vector.name} names no catalogue entry"


def test_the_runner_fails_on_a_wrong_expectation() -> None:
    """The runner must be able to fail.

    A conformance runner that has never rejected anything is indistinguishable
    from a loop that reads files.
    """
    good = HLC_VECTORS[0]
    broken = Vector(
        path=good.path,
        data={
            **good.data,
            "operations": [
                {**op, "expect": [1, 0, "wrong"]} if "expect" in op else op
                for op in good.data["operations"]
            ],
        },
    )
    with pytest.raises(VectorFailure, match="expected"):
        run_hlc_vector(broken)
