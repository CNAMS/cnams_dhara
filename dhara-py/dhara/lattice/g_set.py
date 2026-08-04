"""Grow-only set. Join is union.

The simplest lattice, built first to validate the base contract and the law
harness on something with no subtlety.

Prefer it over `ORSet` whenever elements are **never removed** -- an append-only
audit list, a set of immutable identifiers. It has no tombstones, and therefore
no retention question, which is worth a great deal on a 2GB device where the
OR-Set's observed-tag set grows monotonically until a policy collects it.

Choosing `GSet` is a claim that removal will never be needed. Migrating to
`ORSet` later is a schema *and* wire-format change, so the claim should be made
deliberately rather than because `GSet` was the easier thing on the day.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Self

from dhara.lattice.base import JSONValue, LatticeError

__all__ = ["GSet"]


@dataclass(frozen=True, slots=True)
class GSet:
    elements: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for element in self.elements:
            if not isinstance(element, str):
                raise LatticeError(
                    f"GSet elements must be strings for canonical ordering, "
                    f"got {type(element).__name__}"
                )

    @classmethod
    def of(cls, *elements: str) -> Self:
        return cls(frozenset(elements))

    def add(self, element: str) -> Self:
        return type(self)(self.elements | {element})

    def join(self, other: Self) -> Self:
        return type(self)(self.elements | other.elements)

    def leq(self, other: Self) -> bool:
        return self.elements <= other.elements

    def canonical(self) -> tuple[str, ...]:
        return tuple(sorted(self.elements))

    def observations(self) -> frozenset[object]:
        """Everything this value has seen. Used by the no-loss law check."""
        return frozenset(self.elements)

    def to_json(self) -> JSONValue:
        return sorted(self.elements)

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, list):
            raise LatticeError(f"GSet must decode from a list, got {type(value).__name__}")
        return cls(frozenset(str(v) for v in value))

    def __iter__(self) -> Iterable[str]:  # type: ignore[override]
        return iter(sorted(self.elements))

    def __contains__(self, element: str) -> bool:
        return element in self.elements

    def __len__(self) -> int:
        return len(self.elements)
