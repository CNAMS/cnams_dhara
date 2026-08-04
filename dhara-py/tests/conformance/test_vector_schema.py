"""Every conformance vector validates against the shared JSON Schema.

This runs before any implementation exists, and it is the reason the schema is a
Phase 0 deliverable rather than a Phase 1 one: a vector that Python parses and
Dart rejects is a build failure with a confusing message, and the cheapest place
to catch that is a validator that is independent of both.

The validator here is deliberately hand-written rather than a jsonschema
dependency. dhara-py has no runtime dependencies by design, the subset of JSON
Schema the vectors use is small, and a validator that fails on a malformed vector
with a useful message is worth more than full draft-2020-12 coverage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

SPEC_ROOT = Path(__file__).resolve().parents[3] / "spec" / "conformance"
SCHEMA_PATH = SPEC_ROOT / "schema.json"

pytestmark = pytest.mark.conformance


def _vectors() -> list[Path]:
    return sorted(
        p
        for p in SPEC_ROOT.rglob("*.json")
        if p.name != "schema.json"
    )


class VectorError(AssertionError):
    """Raised with the vector path and the offending field, never a bare mismatch."""


def validate(vector: dict[str, Any], schema: dict[str, Any], where: str) -> None:
    """Check the subset of the schema the vectors actually use.

    Deliberately strict about `additionalProperties`: a typo in a field name is
    the failure this catches most often, and silently ignoring an unknown key
    means the vector asserts less than its author thought it did.
    """
    required = schema.get("required", [])
    for key in required:
        if key not in vector:
            raise VectorError(f"{where}: missing required field {key!r}")

    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unknown = set(vector) - set(props)
        if unknown:
            raise VectorError(f"{where}: unknown field(s) {sorted(unknown)}")

    name = vector.get("name")
    if name is not None and not re.fullmatch(r"[a-z0-9_]+", name):
        raise VectorError(f"{where}: name {name!r} must be lowercase with underscores")

    kind = vector.get("kind")
    if kind not in {"hlc", "merge", "session"}:
        raise VectorError(f"{where}: kind {kind!r} is not one of hlc, merge, session")

    catalogue = vector.get("catalogue", [])
    if not catalogue:
        raise VectorError(
            f"{where}: catalogue is empty. A vector covering nothing in the "
            f"catalogue is testing behaviour nobody decided was correct."
        )
    for entry in catalogue:
        if not re.fullmatch(r"C-[0-9]{2}", entry):
            raise VectorError(f"{where}: catalogue entry {entry!r} is not of the form C-NN")

    # Per-kind requirements, mirroring the schema's allOf/if-then block.
    per_kind = {
        "merge": ["schema", "replicas", "expected", "expected_signals"],
        "hlc": ["operations", "expected"],
        "session": ["transcript"],
    }
    for key in per_kind[kind]:
        if key not in vector:
            raise VectorError(f"{where}: kind={kind} vectors require {key!r}")


def test_schema_file_is_valid_json() -> None:
    json.loads(SCHEMA_PATH.read_text())


def test_schema_declares_the_catalogue_signal_codes() -> None:
    """The signal enum is a closed set and must match the catalogue.

    Adding a code here without a catalogue entry that needs it is how a review
    signal ends up with no defined meaning.
    """
    schema = json.loads(SCHEMA_PATH.read_text())
    codes = schema["$defs"]["reviewSignal"]["properties"]["code"]["enum"]
    catalogue = (SPEC_ROOT.parent / "conflict-catalogue.md").read_text()
    for code in codes:
        assert code in catalogue, f"signal {code!r} is in the schema but not the catalogue"


def test_a_malformed_vector_is_rejected_with_a_useful_message() -> None:
    """The validator must fail loudly on a bad vector, not skip it.

    A validator that has never been observed to reject anything is
    indistinguishable from `assert True`.
    """
    schema = json.loads(SCHEMA_PATH.read_text())

    with pytest.raises(VectorError, match="missing required field 'catalogue'"):
        validate({"name": "x", "kind": "merge"}, schema, "<fixture>")

    with pytest.raises(VectorError, match="unknown field"):
        validate(
            {"name": "x", "kind": "merge", "catalogue": ["C-01"], "typo_field": 1},
            schema,
            "<fixture>",
        )

    with pytest.raises(VectorError, match="not of the form C-NN"):
        validate({"name": "x", "kind": "merge", "catalogue": ["C1"]}, schema, "<fixture>")

    with pytest.raises(VectorError, match="require 'replicas'"):
        validate(
            {"name": "x", "kind": "merge", "catalogue": ["C-01"], "schema": {}},
            schema,
            "<fixture>",
        )


@pytest.mark.parametrize("path", _vectors(), ids=lambda p: p.stem)
def test_vector_validates(path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    vector = json.loads(path.read_text())
    validate(vector, schema, str(path.relative_to(SPEC_ROOT)))


def test_vector_directories_exist() -> None:
    """The three vector directories exist before they have contents.

    Phase 0 ships no vectors. This asserts the tree the phase 1 and phase 3
    runners will read from, so a missing directory fails here rather than as a
    silently empty test run later.
    """
    for kind in ("hlc", "merge", "sessions"):
        assert (SPEC_ROOT / kind).is_dir(), f"missing spec/conformance/{kind}/"
