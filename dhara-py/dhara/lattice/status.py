"""Status lattice: a domain join over a declared partial order.

Under last-write-wins, a record marked terminal on one device and reopened on
another resolves by whichever clock ran later (C-09). **The outcome depends on
clock skew rather than on domain meaning** -- the same two operations in the
other order give the opposite answer.

A domain join gives the same answer on every replica regardless of timing, and
gives an answer that means something.

**The order lives in the consumer, not here.** `dhara` provides the machinery
and validates the supplied function; the domain provides the order. The
`prospective < enrolled < transferred < graduated` example in roadmap section
5.4 is an illustration of the API, not a value shipped in this repository.

Validation is exhaustive over the declared value set, at construction time. An
invalid domain join is a configuration error that should fail at startup; the
alternative is discovering in month four that nothing ever converged, via a
simulator failure whose root cause is three layers away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Self, Sequence

from dhara.lattice.base import JSONValue, LatticeError

__all__ = ["StatusLattice", "StatusOrder", "join_from_total_order"]

DomainJoin = Callable[[str, str], str]


@dataclass(frozen=True, slots=True)
class StatusOrder:
    """A validated domain join over a finite value set.

    Constructing one runs the full check. There is no way to obtain an
    unvalidated `StatusOrder`, which is the point: the check cannot be skipped
    under time pressure because there is no path that skips it.
    """

    values: tuple[str, ...]
    join_fn: DomainJoin = field(compare=False)

    def __post_init__(self) -> None:
        if not self.values:
            raise LatticeError("a status order must declare at least one value")
        if len(set(self.values)) != len(self.values):
            raise LatticeError(f"duplicate values in status order: {self.values}")
        self._validate()

    def _validate(self) -> None:
        """Check the three laws exhaustively over the declared value set.

        For a realistic value set - a handful of statuses - all pairs and all
        triples is affordable, and affordable exhaustive beats sampled.
        """
        values = self.values

        for a in values:
            for b in values:
                ab = self._apply(a, b)
                ba = self._apply(b, a)
                if ab != ba:
                    raise LatticeError(
                        f"domain join is not commutative: join({a!r}, {b!r}) = {ab!r} "
                        f"but join({b!r}, {a!r}) = {ba!r}. Two replicas would reach "
                        f"different states from the same operations."
                    )

        for a in values:
            aa = self._apply(a, a)
            if aa != a:
                raise LatticeError(
                    f"domain join is not idempotent: join({a!r}, {a!r}) = {aa!r}. "
                    f"Duplicate delivery would change state."
                )

        for a in values:
            for b in values:
                for c in values:
                    left = self._apply(self._apply(a, b), c)
                    right = self._apply(a, self._apply(b, c))
                    if left != right:
                        raise LatticeError(
                            f"domain join is not associative: "
                            f"join(join({a!r}, {b!r}), {c!r}) = {left!r} but "
                            f"join({a!r}, join({b!r}, {c!r})) = {right!r}. Replicas "
                            f"that batch operations differently would diverge."
                        )

    def _apply(self, a: str, b: str) -> str:
        result = self.join_fn(a, b)
        if result not in self.values:
            raise LatticeError(
                f"domain join returned {result!r}, which is not in the declared "
                f"value set {self.values}"
            )
        return result

    def join(self, a: str, b: str) -> str:
        return self._apply(a, b)

    def check_member(self, value: str) -> None:
        if value not in self.values:
            raise LatticeError(
                f"status {value!r} is not in the declared value set {self.values}"
            )


def join_from_total_order(values: Sequence[str]) -> StatusOrder:
    """Build a `StatusOrder` from a totally ordered list, least to greatest.

    A convenience for the common case. It is *not* the only case: a genuine
    partial order with incomparable branches (C-10) needs a hand-written join,
    which is why the general form takes a function.
    """
    rank = {v: i for i, v in enumerate(values)}
    return StatusOrder(
        values=tuple(values),
        join_fn=lambda a, b: a if rank[a] >= rank[b] else b,
    )


@dataclass(frozen=True, slots=True)
class StatusLattice:
    value: str
    order: StatusOrder = field(compare=False)

    def __post_init__(self) -> None:
        self.order.check_member(self.value)

    def set(self, value: str) -> Self:
        """A local transition is a join, not an assignment.

        Writing it this way means a device cannot move a record *backwards*
        through the order by simply setting a field - the join decides, exactly
        as it would on merge.
        """
        return self.join(type(self)(value, self.order))

    def join(self, other: Self) -> Self:
        return type(self)(self.order.join(self.value, other.value), self.order)

    def leq(self, other: Self) -> bool:
        return self.order.join(self.value, other.value) == other.value

    def is_incomparable_with(self, other: Self) -> bool:
        """Neither value dominates the other.

        The join is still total and deterministic, so the engine needs no help -
        but two workers disagreeing about a record's status is an operational
        fact somebody should see (C-10).
        """
        return not self.leq(other) and not other.leq(self)

    def canonical(self) -> str:
        return self.value

    def observations(self) -> frozenset[object]:
        return frozenset({self.value})

    def to_json(self) -> JSONValue:
        return self.value

    @classmethod
    def from_json(cls, value: JSONValue, order: StatusOrder | None = None) -> Self:
        if order is None:
            raise LatticeError(
                "decoding a status lattice needs its declared order, which is "
                "supplied by the consumer's schema binding"
            )
        return cls(str(value), order)
