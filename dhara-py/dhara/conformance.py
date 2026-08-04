"""Runner for the language-agnostic conformance vectors.

The vectors under ``spec/conformance/`` are the executable form of
``spec/merge-semantics.md``. Python and Dart both run this tree, and divergence
between them is a build failure.

This module holds the Python runner. The contract both runners must satisfy is
in ``spec/conformance/README.md``; the parts that matter most:

* validate before running, so a malformed vector fails with a useful message
  rather than a confusing one;
* apply **every permutation** of replica order -- the claim is
  order-independence, and one order tests a fraction of it;
* compare in canonical form, field-wise, so a failure names the field.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dhara import review
from dhara.hlc import HLC, Clock
from dhara.lattice import join_from_total_order
from dhara.lattice.base import LatticeError
from dhara.schema import Field, Record, Schema

__all__ = [
    "Vector",
    "VectorFailure",
    "build_schema",
    "load_vectors",
    "run_hlc_vector",
    "run_merge_vector",
]


class VectorFailure(AssertionError):
    """A vector did not produce its expected result.

    Carries the vector name and the specific step, because "expected != actual"
    on a whole state blob is not a debuggable failure message.
    """


@dataclass(frozen=True, slots=True)
class Vector:
    path: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def kind(self) -> str:
        return str(self.data["kind"])

    @property
    def catalogue(self) -> list[str]:
        return list(self.data["catalogue"])


def spec_root() -> Path:
    """Locate ``spec/conformance/`` relative to this file.

    Both implementations read the *same* tree; the Dart runner resolves it the
    same way from its own package root.
    """
    return Path(__file__).resolve().parents[2] / "spec" / "conformance"


def load_vectors(kind: str | None = None, root: Path | None = None) -> list[Vector]:
    base = root or spec_root()
    vectors = [
        Vector(path=p, data=json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(base.rglob("*.json"))
        if p.name != "schema.json"
    ]
    if kind is not None:
        vectors = [v for v in vectors if v.kind == kind]
    return vectors


class _ScriptedClock:
    """Physical time supplied per operation by the vector, not by the wall clock.

    A vector that depended on real time would not be reproducible, which would
    defeat the purpose of having it.
    """

    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def run_hlc_vector(vector: Vector) -> None:
    """Replay an HLC transcript and check the clock state after every step.

    Checking after *every* step rather than only at the end is deliberate: two
    compensating errors can produce the right final value from a wrong path, and
    the path is what the implementation has to get right.
    """
    physical = _ScriptedClock()
    clocks: dict[str, Clock] = {}
    issued: list[HLC] = []

    for step, op in enumerate(vector.data["operations"]):
        node = str(op["node"])
        if node not in clocks:
            clocks[node] = Clock(node, physical)
        physical.now = int(op["physical_time"])

        if op["op"] == "send":
            got = clocks[node].send()
        elif op["op"] == "receive":
            got = clocks[node].receive(HLC.from_json(op["remote"]))
        else:  # pragma: no cover - the schema constrains this
            raise VectorFailure(f"{vector.name}: unknown op {op['op']!r}")

        issued.append(got)

        if "expect" in op:
            want = HLC.from_json(op["expect"])
            if got != want:
                raise VectorFailure(
                    f"{vector.name} step {step} ({op['op']} on {node}): "
                    f"expected {want}, got {got}"
                )

    expected = vector.data.get("expected", {})

    if "final" in expected:
        want = HLC.from_json(expected["final"])
        if issued[-1] != want:
            raise VectorFailure(
                f"{vector.name}: final clock expected {want}, got {issued[-1]}"
            )

    if "sorted" in expected:
        want_order = [HLC.from_json(h) for h in expected["sorted"]]
        got_order = sorted(issued)
        if got_order != want_order:
            raise VectorFailure(
                f"{vector.name}: sort order expected {want_order}, got {got_order}"
            )


# ---------------------------------------------------------------- merge ---


def build_schema(spec: dict[str, Any]) -> Schema:
    """Construct a `Schema` from a vector's schema block.

    A status field's order arrives *in the vector* because in production it
    arrives from the consumer's schema binding. `dhara` never holds one, and a
    vector that omitted it could not be run at all -- which is the dependency
    rule showing up in the file format.
    """
    fields: list[Field] = []
    for f in spec["fields"]:
        kind = f["lattice"]
        order = join_from_total_order(f["order"]) if kind == "StatusLattice" else None
        fields.append(
            Field(
                name=f["name"],
                lattice=kind,
                dedup_on=tuple(f.get("dedup_on", ("taken_at", "recorded_by", "value"))),
                scale=int(f.get("scale", 0)),
                order=order,
                review_when_contested=bool(f.get("review_when_contested", True)),
            )
        )
    return Schema(name=spec["name"], fields=tuple(fields))


def run_merge_vector(vector: Vector) -> None:
    """Join a vector's replicas in **every** order and check the result.

    Running all `n!` permutations is not thoroughness for its own sake: the
    claim being tested *is* order-independence, so one order tests a fraction of
    it. For n <= 4 the factorial is small enough that exhaustive is free, and
    exhaustive beats sampled when it is affordable.
    """
    data = vector.data
    schema = build_schema(data["schema"])

    names = sorted(data["replicas"])
    if len(names) > 5:
        raise VectorFailure(
            f"{vector.name}: {len(names)} replicas is too many to permute "
            f"exhaustively; split the vector"
        )

    try:
        replicas = {n: schema.decode_record(data["replicas"][n]) for n in names}
    except LatticeError as exc:
        raise VectorFailure(f"{vector.name}: could not decode replicas: {exc}") from exc

    expected = schema.decode_record(data["expected"])
    want_signals = frozenset(s["code"] for s in data["expected_signals"])

    baseline: tuple[tuple[str, object], ...] | None = None

    for order in itertools.permutations(names):
        merged = replicas[order[0]]
        for name in order[1:]:
            merged = merged.join(replicas[name])

        if baseline is None:
            baseline = merged.canonical()
        elif merged.canonical() != baseline:
            raise VectorFailure(
                f"{vector.name}: replica order {order} produced a different state "
                f"than the first order. The join is not order-independent, which "
                f"means these replicas would never converge."
            )

        _assert_fields_match(vector, schema, merged, expected, order)

        got_signals = review.codes(
            review.detect(merged, inputs=tuple(replicas[n] for n in order))
        )
        if got_signals != want_signals:
            missing = sorted(want_signals - got_signals)
            spurious = sorted(got_signals - want_signals)
            raise VectorFailure(
                f"{vector.name} in order {order}: review signals differ.\n"
                f"  missing:  {missing or 'none'}\n"
                f"  spurious: {spurious or 'none'}"
            )


def _assert_fields_match(
    vector: Vector,
    schema: Schema,
    merged: Record,
    expected: Record,
    order: tuple[str, ...],
) -> None:
    """Compare field by field.

    "Expected != actual" on a whole record is not a debuggable failure message,
    and a 40-entry series makes it unreadable. Naming the field turns a wall of
    JSON into one line.
    """
    for name in schema.field_names:
        got = merged.state[name].canonical()  # type: ignore[attr-defined]
        want = expected.state[name].canonical()  # type: ignore[attr-defined]
        if got != want:
            raise VectorFailure(
                f"{vector.name} in order {order}: field {name!r} differs.\n"
                f"  expected {want}\n"
                f"  got      {got}"
            )
