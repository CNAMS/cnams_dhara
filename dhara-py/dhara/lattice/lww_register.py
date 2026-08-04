"""Last-write-wins register that never discards the loser.

    A last-write-wins register that *discards* the loser is a data-loss bug
    wearing a design-decision costume.  -- roadmap section 5.4

So the state here is not a slot. It is **the set of every value this replica has
ever observed for the field**, and "current" is derived as the HLC-maximal one.
Join is set union, which makes retention automatic rather than something a
`keep_losers` flag could switch off: there is no code path that drops an
observation, because dropping one would mean removing an element from a union.

Concurrent edits to a name spelling (C-08) are not noise. In a transliterated-
name context a contested spelling is signal -- it is one of the ways a duplicate
registration surfaces downstream. Discarding it destroys evidence and produces
the reported field symptom of "I fixed it and it went back", with nothing in the
record explaining why.

**Cleared is a value, not an absence** (C-12). `None` participates in ordering
like any other value. A wire format that omits null fields to save bytes makes
"the guardian asked for this number to be removed" unrepresentable, and the
bytes are not worth it.

Cost, stated plainly: history grows with the number of concurrent edits to a
field, unbounded in principle. For names, phone numbers and addresses that is
fine -- concurrent edits are rare and values are small. This would not be an
acceptable design for a large free-text field, and `dhara` does not offer one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from dhara.hlc import HLC
from dhara.lattice.base import JSONValue, LatticeError, canonical_scalar

__all__ = ["LWWRegister", "Observation"]

#: Values a register may hold. `None` means *cleared*, and is ordered like any
#: other value rather than treated as "no update".
RegisterValue = str | int | bool | None


@dataclass(frozen=True, slots=True, order=False)
class Observation:
    """One value, written once, by someone, at a point in causal time."""

    value: RegisterValue
    hlc: HLC
    author: str

    def __post_init__(self) -> None:
        if not self.author:
            raise LatticeError("an observation must record its author")
        if isinstance(self.value, float):
            raise LatticeError(
                "float register values are rejected: Python and Dart do not format "
                "them identically, which would break canonical serialisation. "
                "Use an integer with a declared scale."
            )

    def sort_key(self) -> tuple[int, int, str]:
        """HLC order, with `node_id` as the tiebreak that makes it total."""
        return (self.hlc.pt, self.hlc.c, self.hlc.node_id)

    def canonical(self) -> tuple[object, ...]:
        return (self.hlc.encode(), self.author, *canonical_scalar(self.value))

    def to_json(self) -> JSONValue:
        return {"value": self.value, "hlc": self.hlc.to_json(), "author": self.author}

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, dict):
            raise LatticeError(f"observation must be an object, got {type(value).__name__}")
        return cls(
            value=value["value"],  # type: ignore[arg-type]
            hlc=HLC.from_json(value["hlc"]),  # type: ignore[arg-type]
            author=str(value["author"]),
        )


@dataclass(frozen=True, slots=True)
class LWWRegister:
    """Every observed value, with the HLC-maximal one derived as current."""

    observations_: frozenset[Observation] = frozenset()

    @classmethod
    def of(cls, value: RegisterValue, hlc: HLC, author: str) -> Self:
        return cls(frozenset({Observation(value, hlc, author)}))

    def write(self, value: RegisterValue, hlc: HLC, author: str) -> Self:
        """A local write is a join with a single-observation register.

        Written this way rather than as a separate code path, so that there is
        exactly one way state changes and the laws cover it.
        """
        return self.join(type(self).of(value, hlc, author))

    # -- derived views ----------------------------------------------------

    @property
    def current(self) -> Observation | None:
        """The HLC-maximal observation, or `None` if nothing was ever written."""
        if not self.observations_:
            return None
        return max(self.observations_, key=Observation.sort_key)

    @property
    def value(self) -> RegisterValue:
        current = self.current
        return None if current is None else current.value

    @property
    def history(self) -> tuple[Observation, ...]:
        """Every non-current observation, oldest first. Never empty after a
        concurrent edit, and never pruned."""
        current = self.current
        return tuple(
            sorted(
                (o for o in self.observations_ if o != current),
                key=Observation.sort_key,
            )
        )

    def is_contested(self) -> bool:
        """True when two observations were written concurrently.

        Concurrency here means "different authors, neither causally after the
        other". Detecting it from state alone is possible because a causal write
        always carries an HLC strictly greater than everything its author had
        seen -- so equal physical time with different node ids, or interleaved
        authorship, indicates a genuine fork.

        Used by `dhara.review` to emit `concurrent_demographic_edit`.
        """
        if len(self.observations_) < 2:
            return False
        ordered = sorted(self.observations_, key=Observation.sort_key)
        latest = ordered[-1]
        return any(o.author != latest.author for o in ordered[:-1])

    # -- lattice ----------------------------------------------------------

    def join(self, other: Self) -> Self:
        return type(self)(self.observations_ | other.observations_)

    def leq(self, other: Self) -> bool:
        return self.observations_ <= other.observations_

    def canonical(self) -> tuple[tuple[object, ...], ...]:
        return tuple(sorted(o.canonical() for o in self.observations_))

    def observations(self) -> frozenset[object]:
        return frozenset(o.canonical() for o in self.observations_)

    def to_json(self) -> JSONValue:
        current = self.current
        return {
            "value": None if current is None else current.value,
            "hlc": None if current is None else current.hlc.to_json(),
            "author": None if current is None else current.author,
            # History is transmitted, not just held locally. An LWW delta that
            # omits it silently violates retention over the wire - a bug that
            # passes every local test because the local state is correct.
            "history": [o.to_json() for o in self.history],
        }

    @classmethod
    def from_json(cls, value: JSONValue) -> Self:
        if not isinstance(value, dict):
            raise LatticeError(f"register must be an object, got {type(value).__name__}")
        observations: set[Observation] = set()
        if value.get("hlc") is not None:
            observations.add(
                Observation(
                    value=value["value"],  # type: ignore[arg-type]
                    hlc=HLC.from_json(value["hlc"]),  # type: ignore[arg-type]
                    author=str(value["author"]),
                )
            )
        for entry in value.get("history", []) or []:
            observations.add(Observation.from_json(entry))
        return cls(frozenset(observations))
