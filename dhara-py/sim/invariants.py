"""What must be true after every schedule.

    def check_invariants(replicas, server, oplog):
        assert all_converged(replicas + [server])
        assert no_measurement_lost(oplog, server.state)
        assert version_vectors_monotonic(oplog)
        assert no_duplicate_application(oplog)

    -- roadmap section 7.1

Two rules govern this module, and both exist because an invariant is easy to
write in a way that can never fail:

**Every invariant ships with a test that proves it can fail.** An invariant never
observed to fail is indistinguishable from `assert True`.
`tests/sim/test_invariants.py` injects a violation of each one.

**No invariant may compute its expectation by calling the code under test.**
`no_measurement_lost` derives what *should* be present from the harness's own
oplog. If it asked a `MeasurementSeries` what it deduplicated to, it would be
asserting that the code agrees with itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from dhara.lattice import LWWRegister, MeasurementSeries
from sim.replica import OpLog, Replica

__all__ = ["Violation", "check_all"]


@dataclass(frozen=True, slots=True)
class Violation:
    invariant: str
    detail: str

    def __str__(self) -> str:
        return f"{self.invariant}: {self.detail}"


def all_converged(replicas: Sequence[Replica]) -> list[Violation]:
    """Every live replica holds identical state.

    Checked only after the network has healed and every queue has drained.
    Replicas that have not yet exchanged everything are legitimately different,
    so checking mid-run would report a violation that is not one -- a false
    alarm is as corrosive to a harness as a missed bug, because it trains you to
    ignore output.
    """
    live = [r for r in replicas if not r.down]
    if len(live) < 2:
        return []

    reference = live[0]
    violations: list[Violation] = []
    baseline = reference.canonical()

    for replica in live[1:]:
        if replica.canonical() == baseline:
            continue
        violations.append(
            Violation(
                "all_converged",
                _diff(reference, replica),
            )
        )
    return violations


def _diff(a: Replica, b: Replica) -> str:
    """Field-wise, so a failure names the record and field rather than dumping
    two whole states."""
    ids = sorted(set(a.records) | set(b.records))
    for record_id in ids:
        if record_id not in a.records:
            return f"{b.replica_id} has record {record_id!r}, {a.replica_id} does not"
        if record_id not in b.records:
            return f"{a.replica_id} has record {record_id!r}, {b.replica_id} does not"
        left, right = a.records[record_id], b.records[record_id]
        for name in left.schema.field_names:
            lc = left.state[name].canonical()  # type: ignore[attr-defined]
            rc = right.state[name].canonical()  # type: ignore[attr-defined]
            if lc != rc:
                return (
                    f"record {record_id!r} field {name!r} differs\n"
                    f"    {a.replica_id}: {lc}\n"
                    f"    {b.replica_id}: {rc}"
                )
    return "canonical forms differ but no field-level difference was found"


def no_measurement_lost(oplog: OpLog, replicas: Sequence[Replica]) -> list[Violation]:
    """Every measurement anyone wrote is present on every live replica.

    **The headline property.** Roadmap: *a measurement that a worker recorded
    must never disappear because of a merge.*

    The expected set comes from the oplog, with dedup keys derived by the
    harness. Legitimate dedup is accounted for because the expectation is a
    *set* of keys: two writes of the same key are one expected entry, which is
    exactly the C-02/C-06 semantics -- without the invariant needing to know how
    `MeasurementSeries` implements them.
    """
    violations: list[Violation] = []
    live = [r for r in replicas if not r.down]
    if not live:
        return []

    for record_id in sorted(oplog.record_ids()):
        for field_name in live[0].schema.field_names:
            expected = oplog.measurement_keys(record_id, field_name)
            if not expected:
                continue
            for replica in live:
                record = replica.records.get(record_id)
                series = None if record is None else record.state.get(field_name)
                if not isinstance(series, MeasurementSeries):
                    violations.append(
                        Violation(
                            "no_measurement_lost",
                            f"{replica.replica_id} has no series for "
                            f"{record_id!r}.{field_name!r} but {len(expected)} "
                            f"measurements were written to it",
                        )
                    )
                    continue
                present = {(e.taken_at, e.recorded_by, e.value) for e in series.entries}
                missing = expected - present
                if missing:
                    violations.append(
                        Violation(
                            "no_measurement_lost",
                            f"{replica.replica_id} is missing {len(missing)} "
                            f"measurement(s) from {record_id!r}.{field_name!r}: "
                            f"{sorted(missing)[:3]}",
                        )
                    )
    return violations


def no_phantom_measurements(oplog: OpLog, replicas: Sequence[Replica]) -> list[Violation]:
    """No replica holds a measurement nobody wrote.

    **The twin of `no_measurement_lost`, and it was missing.** The headline
    property has two directions - nothing disappears, and nothing is invented -
    and only the first was implemented. Mutation M5 (a dedup key that includes
    the HLC) survived 1,000 seeds producing 11 entries where 10 distinct
    readings existed, because every expected entry was present and nothing
    checked the converse.

    Inventing clinical data is at least as bad as losing it: a phantom weighing
    is a data point a supervisor will act on, and it never happened.
    """
    violations: list[Violation] = []
    live = [r for r in replicas if not r.down]
    if not live:
        return []

    for record_id in sorted(oplog.record_ids()):
        for field_name in live[0].schema.field_names:
            expected = oplog.measurement_keys(record_id, field_name)
            for replica in live:
                record = replica.records.get(record_id)
                series = None if record is None else record.state.get(field_name)
                if not isinstance(series, MeasurementSeries):
                    continue
                present = {(e.taken_at, e.recorded_by, e.value) for e in series.entries}
                invented = present - expected
                if invented:
                    violations.append(
                        Violation(
                            "no_phantom_measurements",
                            f"{replica.replica_id} holds {len(invented)} measurement(s) "
                            f"nobody wrote in {record_id!r}.{field_name!r}: "
                            f"{sorted(invented)[:3]}",
                        )
                    )
                # Distinct keys and entries must be one to one. Two entries
                # sharing a key means dedup failed even when both keys were
                # legitimately written.
                if len(series.entries) != len(present):
                    violations.append(
                        Violation(
                            "no_phantom_measurements",
                            f"{replica.replica_id} has {len(series.entries)} entries "
                            f"for only {len(present)} distinct readings in "
                            f"{record_id!r}.{field_name!r}; dedup did not collapse them",
                        )
                    )
    return violations


def removals_are_honoured(oplog: OpLog, replicas: Sequence[Replica]) -> list[Violation]:
    """An element removed after being observed does not come back.

    Added because nothing checked removal semantics at all. Mutation M4 - an
    OR-Set remove that deletes adds instead of recording observed tags -
    survived, because deleting the add locally converges perfectly well: the
    peer's copy is re-merged in and the element quietly resurrects.

    Resurrection is the failure the observed-remove design exists to prevent,
    and it was the one thing the invariants did not look for.

    ⚠ Checked at **tag** level, not element level. A removal guarantees the
    absence of the adds it observed - nothing more. A concurrent add whose tag
    the remove never saw legitimately survives, and so does a later re-add
    (C-14). An element-level invariant fires on both of those, which are correct
    behaviour; this one was written that way first and seed 49 caught it.
    """
    violations: list[Violation] = []
    live = [r for r in replicas if not r.down]
    if not live:
        return []

    removed: dict[tuple[str, str], set[str]] = {}
    for op in oplog.entries:
        if op.kind == "tag_remove" and len(op.detail) == 2:
            removed.setdefault((op.record_id, op.field), set()).update(op.detail[1])

    for (record_id, field_name), tags in sorted(removed.items()):
        if not tags:
            continue
        for replica in live:
            record = replica.records.get(record_id)
            or_set = None if record is None else record.state.get(field_name)
            if or_set is None or not hasattr(or_set, "adds"):
                continue
            live_tags = {
                t.tag.encode()
                for t in or_set.adds
                if t.tag not in or_set.removed_tags
            }
            resurrected = tags & live_tags
            if resurrected:
                violations.append(
                    Violation(
                        "removals_are_honoured",
                        f"{replica.replica_id} resurrected {len(resurrected)} "
                        f"removed tag(s) in {record_id!r}.{field_name!r}",
                    )
                )
    return violations


def no_observation_lost(oplog: OpLog, replicas: Sequence[Replica]) -> list[Violation]:
    """Every register value anyone wrote is still observable.

    The retained-losers claim, checked end to end rather than at the lattice
    boundary. A register that dropped a loser passes its own unit tests if the
    current value is right; this is what notices.
    """
    violations: list[Violation] = []
    live = [r for r in replicas if not r.down]
    if not live:
        return []

    for record_id in sorted(oplog.record_ids()):
        for field_name in live[0].schema.field_names:
            expected = oplog.register_values(record_id, field_name)
            if not expected:
                continue
            expected_values = {(hlc, author, value) for hlc, author, value in expected}
            for replica in live:
                record = replica.records.get(record_id)
                register = None if record is None else record.state.get(field_name)
                if not isinstance(register, LWWRegister):
                    continue
                present = {
                    (o.hlc.encode(), o.author, o.value) for o in register.observations_
                }
                missing = expected_values - present
                if missing:
                    violations.append(
                        Violation(
                            "no_observation_lost",
                            f"{replica.replica_id} dropped {len(missing)} observed "
                            f"value(s) from {record_id!r}.{field_name!r}",
                        )
                    )
    return violations


def hlc_causality_respected(oplog: OpLog) -> list[Violation]:
    """A replica's own operations are strictly increasing in HLC.

    Anything else means the clock reissued a timestamp, which breaks operation
    identity `(device_id, hlc)` and lets one operation be discarded as a
    duplicate of another (C-24's failure mode, reachable here by a clock bug
    rather than an id collision).
    """
    violations: list[Violation] = []
    last: dict[str, object] = {}
    for op in oplog.entries:
        previous = last.get(op.replica_id)
        if previous is not None and not previous < op.hlc:  # type: ignore[operator]
            violations.append(
                Violation(
                    "hlc_causality_respected",
                    f"{op.replica_id} issued {op.hlc} after {previous}, which is "
                    f"not strictly greater",
                )
            )
        last[op.replica_id] = op.hlc
    return violations


def no_duplicate_operation_ids(oplog: OpLog) -> list[Violation]:
    """`(replica_id, hlc)` is unique across the whole run.

    This is what operation identity rests on in Phase 3. If it can be violated
    here, idempotent application is unimplementable there.
    """
    seen: set[tuple[str, str]] = set()
    violations: list[Violation] = []
    for op in oplog.entries:
        key = (op.replica_id, op.hlc.encode())
        if key in seen:
            violations.append(
                Violation("no_duplicate_operation_ids", f"operation id {key} reused")
            )
        seen.add(key)
    return violations


def review_signals_deterministic(replicas: Sequence[Replica]) -> list[Violation]:
    """Converged replicas emit identical signals.

    True by construction given the design -- signals are derived from merged
    state, so convergence implies signal equality. Asserted anyway, because
    "true by construction" is a claim about code that can be changed.
    """
    from dhara import review

    live = [r for r in replicas if not r.down]
    if len(live) < 2:
        return []

    violations: list[Violation] = []
    reference = live[0]
    for replica in live[1:]:
        for record_id in sorted(set(reference.records) & set(replica.records)):
            a = review.detect(reference.records[record_id])
            b = review.detect(replica.records[record_id])
            if a != b:
                violations.append(
                    Violation(
                        "review_signals_deterministic",
                        f"record {record_id!r}: {reference.replica_id} emitted "
                        f"{[s.code for s in a]}, {replica.replica_id} emitted "
                        f"{[s.code for s in b]}",
                    )
                )
    return violations


def derived_views_agree(replicas: Sequence[Replica]) -> list[Violation]:
    """Converged replicas agree on the values a user would actually see.

    Canonical state equality is necessary but **not sufficient**. A derived view
    - a register's current value, a series' current entries, a set's membership -
    is computed from that state, and if the computation is not itself
    deterministic, two replicas holding identical state can still show different
    things to two different workers.

    ⚠ Added because the deliberate-bug experiment found the gap. Mutation M3
    removes the `node_id` tiebreak from HLC ordering; every replica still holds
    the same observation set, so `all_converged` passes, but `max()` over that
    set now has no total order and picks by iteration order. Two replicas would
    display different names for the same subject, and nothing reported it.
    """
    live = [r for r in replicas if not r.down]
    if len(live) < 2:
        return []

    violations: list[Violation] = []
    reference = live[0]
    for replica in live[1:]:
        for record_id in sorted(set(reference.records) & set(replica.records)):
            left, right = reference.records[record_id], replica.records[record_id]
            for name in left.schema.field_names:
                a, b = left.state[name], right.state[name]
                for label, extract in _DERIVED_VIEWS.items():
                    va, vb = extract(a), extract(b)
                    if va is _NOT_APPLICABLE or vb is _NOT_APPLICABLE:
                        continue
                    if va != vb:
                        violations.append(
                            Violation(
                                "derived_views_agree",
                                f"record {record_id!r} field {name!r} {label}: "
                                f"{reference.replica_id} sees {va!r}, "
                                f"{replica.replica_id} sees {vb!r}",
                            )
                        )
    return violations


class _NotApplicable:
    def __repr__(self) -> str:
        return "<n/a>"


_NOT_APPLICABLE = _NotApplicable()


def _register_current(value: object) -> object:
    if isinstance(value, LWWRegister):
        current = value.current
        return None if current is None else (current.value, current.author)
    return _NOT_APPLICABLE


def _series_current(value: object) -> object:
    if isinstance(value, MeasurementSeries):
        return tuple(e.entry_id for e in value.current)
    return _NOT_APPLICABLE


def _set_members(value: object) -> object:
    from dhara.lattice import ORSet

    if isinstance(value, ORSet):
        return tuple(sorted(value.elements))
    return _NOT_APPLICABLE


_DERIVED_VIEWS = {
    "current value": _register_current,
    "current entries": _series_current,
    "membership": _set_members,
}


def check_all(replicas: Sequence[Replica], oplog: OpLog) -> list[Violation]:
    """Run every invariant and return **all** violations, not the first.

    Reporting only the first hides the shape of a failure: a convergence
    violation together with a lost measurement is a different bug from either
    one alone, and knowing that at a glance is worth the extra work.
    """
    return [
        *all_converged(replicas),
        *derived_views_agree(replicas),
        *no_measurement_lost(oplog, replicas),
        *no_phantom_measurements(oplog, replicas),
        *removals_are_honoured(oplog, replicas),
        *no_observation_lost(oplog, replicas),
        *hlc_causality_respected(oplog),
        *no_duplicate_operation_ids(oplog),
        *review_signals_deterministic(replicas),
    ]
