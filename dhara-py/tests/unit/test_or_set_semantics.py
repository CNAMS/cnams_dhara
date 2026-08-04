"""Observed-remove semantics, exercised through the operations rather than the
constructor.

**Why this file exists:** mutation calibration found a gap. The law tests build
OR-Set values directly with `ORSet(adds, removed_tags)`, so a mutation that
breaks `remove()` -- keying it on the element instead of on the observed tags,
which is mutation M4 of the Phase 2 deliberate-bug experiment -- passed the
entire property suite untouched.

That is the lesson the experiment exists to teach, arriving early: a property
test only covers the code paths its strategy reaches. Laws over constructed
values prove the *algebra*; they say nothing about whether the operations that
produce those values are right.

Every test below drives the public operations.
"""

from __future__ import annotations

from dhara.hlc import HLC
from dhara.lattice import ORSet

TAG_A = HLC(1_000, 0, "dev_a")
TAG_B = HLC(1_000, 0, "dev_b")
TAG_C = HLC(2_000, 0, "dev_a")


def test_sequential_add_then_remove_removes() -> None:
    """The remove observed the add, so the add goes."""
    s = ORSet().add("x", TAG_A)
    assert "x" in s
    assert "x" not in s.remove("x")


def test_concurrent_add_survives_a_remove_that_did_not_observe_it() -> None:
    """C-14, and the whole reason this is not a simpler set.

    Replica A adds a tag. Replica B, which has never seen that add, removes
    everything it can see for that element. On merge the add survives, because
    B's remove carried the tags it observed - and it observed none.
    """
    a = ORSet().add("x", TAG_A)
    b = ORSet().remove("x")  # B has never seen any add for "x"

    assert "x" in a.join(b)
    assert "x" in b.join(a), "the result must not depend on merge direction"


def test_a_remove_only_removes_what_it_observed() -> None:
    """B saw one of two concurrent adds. Only that one is removed."""
    both = ORSet().add("x", TAG_A).add("x", TAG_B)
    b_saw_only_a = ORSet().add("x", TAG_A).remove("x")

    merged = both.join(b_saw_only_a)
    assert "x" in merged, "the unobserved add must survive"
    assert TAG_A in merged.removed_tags
    assert TAG_B not in merged.removed_tags


def test_re_add_after_remove_is_observable() -> None:
    """Without per-add tags this is indistinguishable from add-then-remove."""
    s = ORSet().add("x", TAG_A).remove("x")
    assert "x" not in s
    assert "x" in s.add("x", TAG_C)


def test_remove_is_idempotent_through_the_operation() -> None:
    s = ORSet().add("x", TAG_A)
    assert s.remove("x").canonical() == s.remove("x").remove("x").canonical()


def test_removing_an_unknown_element_is_a_no_op() -> None:
    s = ORSet().add("x", TAG_A)
    assert s.remove("absent").canonical() == s.canonical()


def test_remove_does_not_touch_other_elements() -> None:
    s = ORSet().add("x", TAG_A).add("y", TAG_B)
    after = s.remove("x")
    assert "y" in after
    assert "x" not in after


def test_operations_compose_commutatively_across_replicas() -> None:
    """Two replicas, independent operation sequences, merged both ways round."""
    a = ORSet().add("x", TAG_A).add("y", TAG_A).remove("y")
    b = ORSet().add("x", TAG_B).add("z", TAG_B)

    assert a.join(b).canonical() == b.join(a).canonical()
    assert a.join(b).elements == frozenset({"x", "z"})


def test_a_remove_never_shrinks_the_add_set() -> None:
    """Removes are recorded as observed tags, never by deleting adds.

    Deleting the add would make the remove unrepresentable to a replica that has
    not seen it, and the element would resurrect on the next merge. This is the
    assertion mutation M4 defeats, and it is why M4 was invisible to the law
    tests: it changes what `remove` *stores*, not what `join` computes.
    """
    s = ORSet().add("x", TAG_A).add("y", TAG_B)
    after = s.remove("x")
    assert after.adds == s.adds, "remove must not delete adds"
    assert after.removed_tags == frozenset({TAG_A})
