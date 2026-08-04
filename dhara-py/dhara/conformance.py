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

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dhara.hlc import HLC, Clock

__all__ = ["Vector", "VectorFailure", "load_vectors", "run_hlc_vector"]


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
