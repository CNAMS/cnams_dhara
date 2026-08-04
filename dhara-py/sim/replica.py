"""Virtual devices and the virtual server.

Both are **full replicas** running the same `dhara` merge code. The server holds
no special authority and applies no special rules -- which resolves open question
Q3, and does so for a concrete reason rather than a preference: it halves the
state space. There is one merge implementation under test, one set of invariants,
one set of conformance vectors. A special-cased server would need its own
mutation suite and its own convergence argument.

## The oplog is ground truth, and it lives in the harness

Every operation any replica originates is recorded in a log **the harness owns
and no replica can see**. That is what makes `no_measurement_lost` checkable at
all: the invariant compares final state against what was actually written, not
against what some replica believes was written.

⚠ If the expected state were computed by calling into `dhara`, the invariant
would be circular and could never fail. The harness derives dedup keys itself.

## Sync in Phase 2 is full-state exchange

There is no session protocol yet -- that is Phase 3, and the roadmap is explicit
that the simulator comes first so it can shape the protocol's design. A sync here
ships the whole record state, sized realistically so the bandwidth model still
bites. WI-3.11 replaces this with real sessions, and re-runs the mutation suite
afterwards to confirm the harness did not lose sensitivity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from dhara.hlc import HLC, Clock
from dhara.lattice import Entry, LWWRegister, MeasurementSeries, ORSet, StatusLattice
from dhara.schema import Record, Schema
from sim.clock import DeviceClock

__all__ = ["OpLog", "Operation", "Replica"]


@dataclass(frozen=True, slots=True)
class Operation:
    """One write, as the harness recorded it happening.

    Deliberately *not* a `dhara` type. The harness must be able to say what was
    written without asking the code under test what it thinks was written.
    """

    replica_id: str
    record_id: str
    field: str
    kind: str
    hlc: HLC
    #: For a measurement: (taken_at, recorded_by, value). For a register: the
    #: value and its author. For a set: the element and its tag.
    detail: tuple[Any, ...]
    at: int

    def dedup_key(self) -> tuple[Any, ...]:
        return self.detail

    @property
    def op_id(self) -> tuple[str, str]:
        return (self.replica_id, self.hlc.encode())


class OpLog:
    """Everything anyone ever wrote. Owned by the harness, invisible to replicas.

    ## Crash-lost operations

    The no-loss property is about **merges**: roadmap, *a measurement that a
    worker recorded must never disappear because of a merge.* A write that was
    still volatile when its device lost power, and had not reached any other
    replica, is lost for a different reason - and that reason is physics, not a
    merge bug.

    Conflating the two makes the invariant fire on every crash scenario, which
    would train you to ignore it. So the harness marks such operations, and
    `no_measurement_lost` excludes exactly those.

    ⚠ The exclusion is deliberately narrow: an operation counts as crash-lost
    only if it was **neither committed locally nor already present on another
    replica** at the moment of the crash. Anything wider would be a loophole
    that quietly excuses real losses.
    """

    __slots__ = ("crash_lost", "entries")

    def __init__(self) -> None:
        self.entries: list[Operation] = []
        self.crash_lost: set[tuple[str, str]] = set()

    def record(self, op: Operation) -> None:
        self.entries.append(op)

    def mark_crash_lost(self, op: Operation) -> None:
        self.crash_lost.add(op.op_id)

    def originated_by(self, replica_id: str) -> list[Operation]:
        return [op for op in self.entries if op.replica_id == replica_id]

    def measurement_keys(self, record_id: str, field: str) -> set[tuple[Any, ...]]:
        """Distinct measurements written for one field, by the harness's own
        reckoning.

        Computed here, from the log, rather than by asking a
        `MeasurementSeries` what it deduplicated to. Using the code under test
        to compute the expectation is how an invariant becomes unfalsifiable.
        """
        return {
            op.dedup_key()
            for op in self.entries
            if op.record_id == record_id
            and op.field == field
            and op.kind == "measurement"
            and op.op_id not in self.crash_lost
        }

    def register_values(self, record_id: str, field: str) -> set[tuple[Any, ...]]:
        return {
            op.dedup_key()
            for op in self.entries
            if op.record_id == record_id
            and op.field == field
            and op.kind == "register"
            and op.op_id not in self.crash_lost
        }

    def record_ids(self) -> set[str]:
        return {op.record_id for op in self.entries}

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(slots=True)
class Replica:
    """A device or the server. Same code, same joins, same everything."""

    replica_id: str
    schema: Schema
    clock: Clock
    oplog: OpLog = field(repr=False)
    is_server: bool = False

    records: dict[str, Record] = field(default_factory=dict, repr=False)
    #: Records changed since the last successful sync. Phase 3 replaces this
    #: with a version vector; here it only needs to be honest about what is
    #: unsynced, so crash tests can check what survives.
    outbox: set[str] = field(default_factory=set, repr=False)
    #: Set on crash, cleared on restart. A crashed replica accepts nothing.
    down: bool = False
    #: Committed state, restored on restart. Everything not here is volatile
    #: and is what a crash-before-commit loses.
    durable: dict[str, str] = field(default_factory=dict, repr=False)

    applied_ops: int = 0
    duplicate_ops: int = 0

    # -- local writes ------------------------------------------------------

    def _ensure(self, record_id: str) -> Record:
        if record_id not in self.records:
            self.records[record_id] = self.schema.empty_record()
        return self.records[record_id]

    def write_measurement(
        self, record_id: str, field_name: str, value: int, taken_at: str, actor: str, at: int
    ) -> None:
        if self.down:
            return
        record = self._ensure(record_id)
        hlc = self.clock.send()
        entry = Entry(value=value, taken_at=taken_at, recorded_by=actor, hlc=hlc)
        series = record.state[field_name]
        assert isinstance(series, MeasurementSeries)
        self.records[record_id] = Record(
            self.schema, {**record.state, field_name: series.append(entry)}
        )
        self.outbox.add(record_id)
        self.oplog.record(
            Operation(
                replica_id=self.replica_id,
                record_id=record_id,
                field=field_name,
                kind="measurement",
                hlc=hlc,
                detail=(taken_at, actor, value),
                at=at,
            )
        )

    def write_register(
        self, record_id: str, field_name: str, value: object, actor: str, at: int
    ) -> None:
        if self.down:
            return
        record = self._ensure(record_id)
        hlc = self.clock.send()
        register = record.state[field_name]
        assert isinstance(register, LWWRegister)
        self.records[record_id] = Record(
            self.schema,
            {**record.state, field_name: register.write(value, hlc, actor)},  # type: ignore[arg-type]
        )
        self.outbox.add(record_id)
        self.oplog.record(
            Operation(
                replica_id=self.replica_id,
                record_id=record_id,
                field=field_name,
                kind="register",
                hlc=hlc,
                detail=(hlc.encode(), actor, value),
                at=at,
            )
        )

    def write_tag(self, record_id: str, field_name: str, element: str, at: int) -> None:
        if self.down:
            return
        record = self._ensure(record_id)
        hlc = self.clock.send()
        or_set = record.state[field_name]
        assert isinstance(or_set, ORSet)
        self.records[record_id] = Record(
            self.schema, {**record.state, field_name: or_set.add(element, hlc)}
        )
        self.outbox.add(record_id)
        self.oplog.record(
            Operation(
                replica_id=self.replica_id,
                record_id=record_id,
                field=field_name,
                kind="tag",
                hlc=hlc,
                detail=(element, hlc.encode()),
                at=at,
            )
        )

    def remove_tag(self, record_id: str, field_name: str, element: str, at: int) -> None:
        """Remove a tag, recording the tags this replica has observed.

        Present because the deliberate-bug experiment showed the generator was
        never calling it: mutation M4 - an OR-Set remove keyed on the element
        instead of on observed tags - survived 1,000 seeds untouched, for
        exactly the reason Phase 1 already documented and this module's own
        docstring already warned about. A code path the generator never drives
        is a code path the simulator does not test, at any scale.
        """
        if self.down:
            return
        record = self.records.get(record_id)
        if record is None:
            return
        or_set = record.state[field_name]
        assert isinstance(or_set, ORSet)
        if element not in or_set.elements:
            return
        self.records[record_id] = Record(
            self.schema, {**record.state, field_name: or_set.remove(element)}
        )
        self.outbox.add(record_id)
        self.oplog.record(
            Operation(
                replica_id=self.replica_id,
                record_id=record_id,
                field=field_name,
                kind="tag_remove",
                hlc=self.clock.send(),
                detail=(element,),
                at=at,
            )
        )

    def write_status(self, record_id: str, field_name: str, value: str, at: int) -> None:
        if self.down:
            return
        record = self._ensure(record_id)
        hlc = self.clock.send()
        status = record.state[field_name]
        assert isinstance(status, StatusLattice)
        self.records[record_id] = Record(
            self.schema, {**record.state, field_name: status.set(value)}
        )
        self.outbox.add(record_id)
        self.oplog.record(
            Operation(
                replica_id=self.replica_id,
                record_id=record_id,
                field=field_name,
                kind="status",
                hlc=hlc,
                detail=(value,),
                at=at,
            )
        )

    # -- sync --------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Everything this replica knows, as it would go on the wire."""
        return {rid: record.to_json() for rid, record in self.records.items()}

    def snapshot_bytes(self) -> int:
        return len(json.dumps(self.snapshot(), separators=(",", ":")).encode())

    def apply(self, snapshot: dict[str, Any], seen: Callable[[str], bool] | None = None) -> None:
        """Merge a peer's snapshot.

        Idempotent by construction rather than by a dedup cache: joining the
        same state twice is the lattice's own idempotence law, which Phase 1
        asserts over 10,000 orders per type. A duplicate delivery four hours
        later costs a merge and changes nothing.
        """
        if self.down:
            return
        for record_id, payload in snapshot.items():
            incoming = self.schema.decode_record(payload)
            before = self.records.get(record_id)
            merged = incoming if before is None else before.join(incoming)
            if before is not None and merged.canonical() == before.canonical():
                self.duplicate_ops += 1
            self.records[record_id] = merged
            self.applied_ops += 1

    def receive_hlc(self, remote: HLC) -> None:
        """Advance the causal clock on observing a peer's timestamp."""
        if not self.down:
            self.clock.receive(remote)

    def commit(self) -> None:
        """Make the current state durable. Everything after this survives a crash."""
        self.durable = {rid: json.dumps(r.to_json(), sort_keys=True) for rid, r in self.records.items()}

    def crash(self) -> None:
        """Lose volatile state. Committed state survives; the rest does not."""
        self.down = True
        self.records = {}
        self.outbox = set()

    def restart(self) -> None:
        self.down = False
        self.records = {
            rid: self.schema.decode_record(json.loads(blob))
            for rid, blob in self.durable.items()
        }

    def canonical(self) -> tuple[tuple[str, Any], ...]:
        return tuple(
            (rid, self.records[rid].canonical()) for rid in sorted(self.records)
        )


def make_replica(
    replica_id: str,
    schema: Schema,
    device_clock: DeviceClock,
    oplog: OpLog,
    *,
    is_server: bool = False,
) -> Replica:
    return Replica(
        replica_id=replica_id,
        schema=schema,
        clock=Clock(replica_id, device_clock),
        oplog=oplog,
        is_server=is_server,
    )
