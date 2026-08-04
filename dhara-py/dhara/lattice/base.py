"""The lattice contract.

Every field kind in a schema is a join-semilattice. The `join` must be:

    commutative   join(a, b) == join(b, a)
    associative   join(join(a, b), c) == join(a, join(b, c))
    idempotent    join(a, a) == a

Together these give the property the whole system rests on: replicas that have
seen the same set of operations -- **in any order, with any duplication, in any
batching** -- reach the same state. Messages arrive out of order, devices batch
differently, and duplicate delivery is routine on this network, so all three are
load-bearing rather than mathematical decoration.

Two design decisions in this module are worth stating, because both are easy to
get wrong in a way that passes every test:

**Canonical form.** Two values that are logically equal must produce identical
bytes. Delta computation compares serialised state; if a set serialises in
iteration order, two replicas holding the same state see a spurious difference
and resend forever. `canonical()` returns a fully ordered structure, and one CI
leg runs with a randomised ``PYTHONHASHSEED`` to catch any path that forgets.

**Review signals are not returned by `join`.** They are derived from the merged
state by `dhara.review`. That keeps `join` pure algebra, and it makes signal
determinism a *corollary* of convergence rather than a separate property needing
its own proof: if the state is order-independent, anything computed from it is
too.
"""

from __future__ import annotations

from typing import Protocol, Self, TypeAlias, runtime_checkable

__all__ = ["JSONValue", "Lattice", "LatticeError"]

JSONValue: TypeAlias = (
    "None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]"
)


class LatticeError(ValueError):
    """A lattice was constructed or joined in a way its contract forbids."""


@runtime_checkable
class Lattice(Protocol):
    """The interface every field kind implements.

    Implementations are immutable. `join` returns a new value and never mutates
    either operand -- a lattice that mutates in place cannot be joined twice with
    the same operand, which breaks idempotence in a way that only shows up under
    duplicate delivery.
    """

    def join(self, other: Self) -> Self:
        """Least upper bound of `self` and `other`.

        Must be commutative, associative and idempotent. Must never return a
        value that observes *less* than either operand: for every lattice here,
        the set of values reachable from `join(a, b)` is exactly the union of
        those reachable from `a` and from `b`. That is the no-silent-data-loss
        property, stated per lattice.
        """
        ...

    def leq(self, other: Self) -> bool:
        """The partial order induced by `join`: ``a <= b`` iff ``join(a, b) == b``.

        Implementations may compute this directly when that is cheaper, but the
        result must agree with the definition -- which is asserted as a property,
        not assumed.
        """
        ...

    def canonical(self) -> object:
        """A fully ordered, hashable structure for stable comparison.

        Two logically equal values must return equal canonical forms regardless
        of insertion order. This is what delta computation compares.
        """
        ...

    def to_json(self) -> JSONValue:
        """Wire and conformance-vector form. Deterministic; sorted where a set."""
        ...

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        ...


def joins_to_least_upper_bound(a: Lattice, b: Lattice) -> bool:
    """`join(a, b)` is an upper bound of both operands.

    Weaker than the three laws and useful separately: a join that satisfies
    commutativity, associativity and idempotence can still *lose* data if it
    returns something below one of its operands. This is the check that catches
    an overwrite masquerading as a merge -- which is mutation M1 of the Phase 2
    deliberate-bug experiment.
    """
    joined = a.join(b)  # type: ignore[arg-type]
    return a.leq(joined) and b.leq(joined)  # type: ignore[arg-type]
