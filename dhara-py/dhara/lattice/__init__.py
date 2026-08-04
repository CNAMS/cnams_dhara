"""The five lattice types.

A fixed catalogue, not a general CRDT library. Roadmap section 2 lists
"arbitrary user-defined schemas" as a non-goal: generality here buys nothing and
costs months. Five is the number.

    GSet                union; no tombstones, and therefore no retention question
    LWWRegister         HLC-ordered current value, every loser retained
    ORSet               observed-remove; a concurrent unobserved add survives
    MeasurementSeries   append-only, deduplicated; there is no overwrite path
    StatusLattice       a domain-supplied join over a declared partial order

Which field kind maps to which is in spec/merge-semantics.md, and the mapping is
total in both directions against spec/conflict-catalogue.md.
"""

from dhara.lattice.base import JSONValue, Lattice, LatticeError
from dhara.lattice.g_set import GSet
from dhara.lattice.lww_register import LWWRegister, Observation
from dhara.lattice.measurement_series import (
    DEFAULT_DEDUP_KEY,
    Entry,
    MeasurementSeries,
)
from dhara.lattice.or_set import ORSet, Tagged
from dhara.lattice.status import StatusLattice, StatusOrder, join_from_total_order

__all__ = [
    "DEFAULT_DEDUP_KEY",
    "Entry",
    "GSet",
    "JSONValue",
    "LWWRegister",
    "Lattice",
    "LatticeError",
    "MeasurementSeries",
    "ORSet",
    "Observation",
    "StatusLattice",
    "StatusOrder",
    "Tagged",
    "join_from_total_order",
]
