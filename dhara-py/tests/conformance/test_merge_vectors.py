"""Run the shared merge conformance vectors.

These are the files the Dart implementation must reproduce in Phase 4. Every one
of them is joined in **every** permutation of replica order, because the claim
being tested is order-independence and one order tests a fraction of it.
"""

from __future__ import annotations

import pytest

from dhara.conformance import Vector, VectorFailure, load_vectors, run_merge_vector

pytestmark = pytest.mark.conformance

MERGE_VECTORS = load_vectors(kind="merge")


def test_there_are_merge_vectors_to_run() -> None:
    """A suite that silently runs nothing passes for the wrong reason."""
    assert MERGE_VECTORS, "no merge vectors found under spec/conformance/merge/"


@pytest.mark.parametrize("vector", MERGE_VECTORS, ids=lambda v: v.name)
def test_merge_vector(vector: Vector) -> None:
    run_merge_vector(vector)


def test_every_vector_traces_to_a_catalogue_entry() -> None:
    for vector in MERGE_VECTORS:
        assert vector.catalogue, f"{vector.name} names no catalogue entry"


def test_catalogue_coverage_is_recorded() -> None:
    """Which catalogue entries the Phase 1 merge layer actually covers.

    Asserted as a set rather than a count, so adding a vector for a new entry is
    a deliberate edit here and dropping one fails loudly. The eight entries not
    listed need session, identity or enrolment machinery and are annotated with
    their phase in the catalogue index.
    """
    covered = {c for v in MERGE_VECTORS for c in v.catalogue}
    expected = {
        "C-01", "C-02", "C-03", "C-04", "C-06", "C-07",
        "C-08", "C-09", "C-10", "C-12", "C-14", "C-19",
    }
    assert covered == expected, (
        f"catalogue coverage changed.\n"
        f"  newly covered: {sorted(covered - expected)}\n"
        f"  no longer covered: {sorted(expected - covered)}"
    )


def test_the_runner_detects_a_wrong_expected_state() -> None:
    """The runner must be able to fail on state.

    A conformance runner that has never rejected anything is indistinguishable
    from a loop that reads files.
    """
    good = next(v for v in MERGE_VECTORS if v.name == "c08_concurrent_register_edit")
    broken = Vector(
        path=good.path,
        data={
            **good.data,
            "expected": {
                "d_a": {
                    "value": "wrong",
                    "hlc": [1000, 0, "dev_b"],
                    "author": "s1",
                    "history": [],
                }
            },
        },
    )
    with pytest.raises(VectorFailure, match="field 'd_a' differs"):
        run_merge_vector(broken)


def test_the_runner_detects_a_missing_signal() -> None:
    """And on signals, which are half the contract.

    A vector whose expected state matches but whose signals do not is a real
    divergence: it means one implementation would surface a merge for review and
    the other would not.
    """
    good = next(v for v in MERGE_VECTORS if v.name == "c08_concurrent_register_edit")
    broken = Vector(path=good.path, data={**good.data, "expected_signals": []})
    with pytest.raises(VectorFailure, match="spurious"):
        run_merge_vector(broken)


def test_an_empty_expected_signals_block_is_a_real_assertion() -> None:
    """C-04 and C-07 assert that a clean merge emits *nothing*.

    That is the assertion which stops the review queue filling with noise, and
    a queue reviewers stop reading is worse than no queue.
    """
    quiet = [v for v in MERGE_VECTORS if not v.data["expected_signals"]]
    assert quiet, "no vector asserts the absence of signals"
    for vector in quiet:
        run_merge_vector(vector)
