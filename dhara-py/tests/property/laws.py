"""Reusable algebraic law checkers.

Adding a lattice type should cost three lines of test, not thirty. Every lattice
in `dhara` is handed to `assert_lattice_laws` with a Hypothesis strategy that
produces values of that type, and the same five properties are checked for all
of them.

The fifth property is the one that is not in the textbook definition and is the
reason this project exists: **a join never loses an observation.** A join can be
commutative, associative and idempotent and still discard data -- `max` on a
single slot is all three, and it is exactly the last-write-wins behaviour the
catalogue spends 24 entries arguing against.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from hypothesis import strategies as st

from dhara.lattice.base import Lattice

T = TypeVar("T", bound=Lattice)

#: Roadmap Phase 1 exit criterion: 10,000 randomised operation orders per type.
#: Hypothesis draws examples rather than enumerating orders, so the budget is
#: split between example count and the operation-sequence length inside each.
LAW_EXAMPLES = 1_000
LAW_SEQUENCE = 10


def assert_commutative(a: T, b: T) -> None:
    assert a.join(b).canonical() == b.join(a).canonical(), (
        f"join is not commutative:\n  join(a, b) = {a.join(b).canonical()}\n"
        f"  join(b, a) = {b.join(a).canonical()}"
    )


def assert_associative(a: T, b: T, c: T) -> None:
    left = a.join(b).join(c)
    right = a.join(b.join(c))
    assert left.canonical() == right.canonical(), (
        f"join is not associative:\n  (a.b).c = {left.canonical()}\n"
        f"  a.(b.c) = {right.canonical()}"
    )


def assert_idempotent(a: T) -> None:
    assert a.join(a).canonical() == a.canonical(), (
        "join is not idempotent; duplicate delivery would corrupt state"
    )


def assert_leq_agrees_with_join(a: T, b: T) -> None:
    """`a <= b` must hold exactly when `join(a, b) == b`.

    A `leq` computed independently of `join` is a second implementation of the
    order, and the two drift. This is what stops them.
    """
    joined = a.join(b)
    assert a.leq(joined), "a is not <= join(a, b)"
    assert b.leq(joined), "b is not <= join(a, b)"
    assert a.leq(b) == (joined.canonical() == b.canonical()), (
        f"leq disagrees with join: leq={a.leq(b)}, join(a,b)==b="
        f"{joined.canonical() == b.canonical()}"
    )


def assert_join_loses_nothing(a: T, b: T, observations: Callable[[T], frozenset[object]]) -> None:
    """The no-silent-data-loss property, per lattice.

    `observations` extracts everything a value has ever seen -- entries for a
    series, observed values for a register, tags for a set. The join's
    observation set must be exactly the union of its operands'.

    Not the textbook lattice contract, and the most important assertion in this
    module. `max` on a single slot satisfies all three algebraic laws and
    destroys data on every concurrent write.
    """
    joined = a.join(b)
    expected = observations(a) | observations(b)
    got = observations(joined)
    missing = expected - got
    assert not missing, f"join dropped observations: {sorted(map(str, missing))}"


def assert_canonical_is_order_stable(a: T, b: T) -> None:
    """Two ways of building the same value serialise identically.

    Guards the convergence bug that hides in set iteration order: replicas whose
    equal states produce unequal bytes see a spurious delta and resend forever.
    """
    assert a.join(b).canonical() == b.join(a).join(a).canonical()


def assert_json_round_trips(a: T, decode: Callable[[object], T]) -> None:
    restored = decode(a.to_json())
    assert restored.canonical() == a.canonical(), (
        f"json round-trip changed the value:\n  before {a.canonical()}\n"
        f"  after  {restored.canonical()}"
    )


def assert_lattice_laws(
    a: T,
    b: T,
    c: T,
    *,
    decode: Callable[[object], T],
    observations: Callable[[T], frozenset[object]] | None = None,
) -> None:
    """Every law, for one triple of values.

    Called from a Hypothesis-driven test per lattice type, so a single call site
    covers the whole contract.

    `decode` is passed rather than the class, because `StatusLattice.from_json`
    needs the declared domain order to decode at all -- the order lives in the
    consumer's schema binding, never in the serialised value. That asymmetry is
    the dependency rule showing up in the type signature, and it is correct.
    """
    assert_commutative(a, b)
    assert_associative(a, b, c)
    assert_idempotent(a)
    assert_idempotent(b)
    assert_leq_agrees_with_join(a, b)
    assert_canonical_is_order_stable(a, b)
    assert_json_round_trips(a, decode)
    if observations is not None:
        assert_join_loses_nothing(a, b, observations)


def triples(values: st.SearchStrategy[T]) -> st.SearchStrategy[tuple[T, T, T]]:
    return st.tuples(values, values, values)
