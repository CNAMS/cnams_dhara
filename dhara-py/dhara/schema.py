"""The runtime interface between `dhara` and any domain.

This module is the entire reason the dependency rule is enforceable. `dhara`
never imports a domain model; it receives a `Schema` at runtime that says which
field names exist and which lattice each one uses. Everything that would
otherwise require knowing what a record *represents* arrives through here:

    * which lattice a field uses
    * a measurement field's dedup key and its scale in minor units
    * a status field's declared partial order and its join function
    * which fields are significant enough to review when contested

The mapping from a domain field to a `Field` here lives in the consumer's
`schema_binding`, in the consumer's repository. This module never sees it.

A `Record` is a mapping from field name to lattice value, and its join is
**field-wise and independent**. That independence is what makes "one actor
corrects a name while another edits an address" a non-event (C-04, C-07), and
it is the property most easily broken later by a well-meaning cross-field
validation rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Mapping, Self

from dhara.lattice import (
    DEFAULT_DEDUP_KEY,
    GSet,
    JSONValue,
    LatticeError,
    LWWRegister,
    MeasurementSeries,
    ORSet,
    StatusLattice,
    StatusOrder,
)

__all__ = ["Field", "LatticeKind", "Record", "Schema"]

#: The closed catalogue. Adding a kind is a spec change, not a configuration
#: change - which is the point of it being closed.
LATTICES: dict[str, type] = {
    "GSet": GSet,
    "LWWRegister": LWWRegister,
    "MeasurementSeries": MeasurementSeries,
    "ORSet": ORSet,
    "StatusLattice": StatusLattice,
}

LatticeKind = str


@dataclass(frozen=True, slots=True)
class Field:
    """One field's binding: a name, a lattice, and that lattice's options."""

    name: str
    lattice: LatticeKind

    #: MeasurementSeries only. Deliberately excludes the HLC - see
    #: spec/merge-semantics.md section 4 and catalogue C-02.
    dedup_on: tuple[str, ...] = DEFAULT_DEDUP_KEY

    #: MeasurementSeries only. Decimal places the consumer's minor units
    #: represent, carried so a renderer can display 9200 grams as 9.2 kg.
    #: `dhara` never uses it arithmetically; values stay integers throughout.
    scale: int = 0

    #: StatusLattice only. Supplied by the consumer, validated on construction.
    order: StatusOrder | None = dc_field(default=None, compare=False)

    #: Whether a contested value on this field is worth a human's attention.
    #: A field where concurrent edits are routine and harmless should set this
    #: false, or the review queue fills with noise and supervisors stop reading
    #: it - which is worse than having no queue.
    review_when_contested: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise LatticeError("a field must have a name")
        if self.lattice not in LATTICES:
            raise LatticeError(
                f"unknown lattice {self.lattice!r} for field {self.name!r}. "
                f"Known: {', '.join(sorted(LATTICES))}. The catalogue is closed; "
                f"adding a kind is a spec change."
            )
        if self.lattice == "StatusLattice" and self.order is None:
            raise LatticeError(
                f"field {self.name!r} is a StatusLattice and must declare its "
                f"order. The order is domain knowledge and is supplied by the "
                f"consumer's schema binding, never by dhara."
            )
        if self.lattice != "StatusLattice" and self.order is not None:
            raise LatticeError(f"field {self.name!r} declares an order but is not a status")
        if self.scale < 0:
            raise LatticeError(f"field {self.name!r} has a negative scale")

    def empty(self) -> object:
        """The identity value for this field's lattice.

        Every lattice here has one, which is what lets a record join against a
        peer that has never seen a field at all.
        """
        if self.lattice == "MeasurementSeries":
            return MeasurementSeries(frozenset(), self.dedup_on)
        if self.lattice == "StatusLattice":
            assert self.order is not None
            return StatusLattice(self.order.values[0], self.order)
        return LATTICES[self.lattice]()

    def decode(self, value: JSONValue) -> object:
        if self.lattice == "MeasurementSeries":
            return MeasurementSeries.from_json(value, self.dedup_on)
        if self.lattice == "StatusLattice":
            assert self.order is not None
            return StatusLattice.from_json(value, self.order)
        return LATTICES[self.lattice].from_json(value)  # type: ignore[attr-defined,no-any-return]

    def to_json(self) -> JSONValue:
        out: dict[str, JSONValue] = {"name": self.name, "lattice": self.lattice}
        if self.lattice == "MeasurementSeries":
            out["dedup_on"] = list(self.dedup_on)
            out["scale"] = self.scale
        if self.lattice == "StatusLattice" and self.order is not None:
            out["order"] = list(self.order.values)
        return out


@dataclass(frozen=True, slots=True)
class Schema:
    name: str
    fields: tuple[Field, ...]
    #: Precomputed in __post_init__. Rebuilding it per access was 135,000
    #: tuple constructions across a 120-seed sample, for a value that cannot
    #: change on a frozen dataclass.
    _names: tuple[str, ...] = dc_field(default=(), compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.fields:
            raise LatticeError(f"schema {self.name!r} declares no fields")
        seen: set[str] = set()
        for f in self.fields:
            if f.name in seen:
                raise LatticeError(f"duplicate field {f.name!r} in schema {self.name!r}")
            seen.add(f.name)
        object.__setattr__(self, "_names", tuple(f.name for f in self.fields))

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise LatticeError(f"schema {self.name!r} has no field {name!r}")

    @property
    def field_names(self) -> tuple[str, ...]:
        return self._names

    def empty_record(self) -> Record:
        return Record(self, {f.name: f.empty() for f in self.fields})

    def decode_record(self, values: Mapping[str, JSONValue]) -> Record:
        """Build a record from partial state.

        Missing fields are filled with their lattice's identity, so a replica
        that has never touched a field joins correctly against one that has.
        """
        state: dict[str, object] = {}
        for f in self.fields:
            state[f.name] = f.decode(values[f.name]) if f.name in values else f.empty()
        unknown = set(values) - set(self.field_names)
        if unknown:
            raise LatticeError(
                f"record carries fields not in schema {self.name!r}: {sorted(unknown)}"
            )
        return Record(self, state)

    def to_json(self) -> JSONValue:
        return {"name": self.name, "fields": [f.to_json() for f in self.fields]}


@dataclass(frozen=True, slots=True)
class Record:
    """A schema's worth of lattice values, joined field-wise."""

    schema: Schema = dc_field(compare=False)
    state: Mapping[str, object]

    def __getitem__(self, name: str) -> object:
        return self.state[name]

    def join(self, other: Self) -> Self:
        """Field-wise, independent, and deliberately without cross-field logic.

        No field's merged value may depend on another field's. That
        independence is what makes concurrent edits to different fields a
        non-event, and adding a "if status is terminal, ignore measurements"
        rule here would break convergence: two replicas applying the rule at
        different points in their merge order would reach different states.

        Cross-field policy belongs in the consumer, applied to the merged
        result.
        """
        if other.schema.name != self.schema.name:
            raise LatticeError(
                f"cannot join records of different schemas: "
                f"{self.schema.name!r} and {other.schema.name!r}"
            )
        return type(self)(
            self.schema,
            {
                name: self.state[name].join(other.state[name])  # type: ignore[attr-defined]
                for name in self.schema.field_names
            },
        )

    def leq(self, other: Self) -> bool:
        return all(
            self.state[name].leq(other.state[name])  # type: ignore[attr-defined]
            for name in self.schema.field_names
        )

    def canonical(self) -> tuple[tuple[str, object], ...]:
        return tuple(
            (name, self.state[name].canonical())  # type: ignore[attr-defined]
            for name in sorted(self.schema.field_names)
        )

    def to_json(self) -> JSONValue:
        return {
            name: self.state[name].to_json()  # type: ignore[attr-defined]
            for name in sorted(self.schema.field_names)
        }
