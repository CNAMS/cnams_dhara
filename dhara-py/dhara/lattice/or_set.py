"""Observed-remove set.

A remove carries **the set of tags it observed**, not the element. So a
concurrent add whose tag the remove never saw survives (C-14).

The alternative -- keying removes on the element -- means one actor clearing
stale tags erases a tag another actor added concurrently, without ever having
seen it. The concurrent add is lost with no trace and no signal. That is the
failure this lattice exists to prevent, and it is not hypothetical: keying on
the element is the natural thing to write if you model a set as "the elements
currently in it".

Three cases, all distinct, all tested:

    add, then remove (the remove observed the add)   -> removed
    add and remove concurrently (remove did not see) -> **present**
    add, remove, add again                           -> present

Cost: tombstones. Observed tags cannot be discarded while any replica may still
hold an unsynced remove referencing them, so the tag set grows monotonically
until a retention policy collects it -- and collecting too early resurrects
removed flags on a six-month-offline device (C-20). The retention period is
open question Q2 and is deliberately not decided here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from dhara.hlc import HLC
from dhara.lattice.base import JSONValue, LatticeError

__all__ = ["ORSet", "Tagged"]


@dataclass(frozen=True, slots=True)
class Tagged:
    """One add: an element and the unique tag identifying that add.

    The tag is what makes re-adding after a remove observable. Without it, "add
    X, remove X, add X again" is indistinguishable from "add X, remove X".
    """

    element: str
    tag: HLC

    def canonical(self) -> tuple[str, str]:
        return (self.element, self.tag.encode())

    def to_json(self) -> JSONValue:
        return {"element": self.element, "tag": self.tag.to_json()}

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, dict):
            raise LatticeError(f"tagged add must be an object, got {type(value).__name__}")
        return cls(element=str(value["element"]), tag=HLC.from_json(value["tag"]))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ORSet:
    adds: frozenset[Tagged] = frozenset()
    removed_tags: frozenset[HLC] = frozenset()

    @classmethod
    def of(cls, *pairs: tuple[str, HLC]) -> Self:
        return cls(frozenset(Tagged(e, t) for e, t in pairs))

    def add(self, element: str, tag: HLC) -> Self:
        return type(self)(self.adds | {Tagged(element, tag)}, self.removed_tags)

    def remove(self, element: str) -> Self:
        """Remove every tag for `element` **that this replica has observed**.

        Tags added concurrently elsewhere are, by definition, not in `self.adds`
        yet, so they are not removed -- which is the whole point.
        """
        observed = frozenset(t.tag for t in self.adds if t.element == element)
        return type(self)(self.adds, self.removed_tags | observed)

    # -- derived view -----------------------------------------------------

    @property
    def elements(self) -> frozenset[str]:
        return frozenset(t.element for t in self.adds if t.tag not in self.removed_tags)

    def __contains__(self, element: str) -> bool:
        return element in self.elements

    # -- lattice ----------------------------------------------------------

    def join(self, other: Self) -> Self:
        return type(self)(
            self.adds | other.adds,
            self.removed_tags | other.removed_tags,
        )

    def leq(self, other: Self) -> bool:
        return self.adds <= other.adds and self.removed_tags <= other.removed_tags

    def canonical(self) -> tuple[object, ...]:
        return (
            tuple(sorted(t.canonical() for t in self.adds)),
            tuple(sorted(h.encode() for h in self.removed_tags)),
        )

    def observations(self) -> frozenset[object]:
        """Adds *and* removes both count as observations.

        A join that dropped a remove would resurrect an element, which is the
        mirror image of losing an add and just as wrong.
        """
        return frozenset(t.canonical() for t in self.adds) | frozenset(
            ("removed", h.encode()) for h in self.removed_tags
        )

    def to_json(self) -> JSONValue:
        return {
            "adds": sorted((t.to_json() for t in self.adds), key=lambda d: (d["element"], str(d["tag"]))),  # type: ignore[index,call-overload]
            "removed_tags": sorted((h.to_json() for h in self.removed_tags), key=str),
        }

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, dict):
            raise LatticeError(f"or-set must be an object, got {type(value).__name__}")
        return cls(
            adds=frozenset(Tagged.from_json(a) for a in value.get("adds", []) or []),
            removed_tags=frozenset(
                HLC.from_json(h) for h in value.get("removed_tags", []) or []  # type: ignore[arg-type]
            ),
        )
