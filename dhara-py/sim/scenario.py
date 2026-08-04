"""Seeded scenario generation, and the simulation that runs one.

A seed picks a whole world: how many devices, how skewed their clocks, what they
write, when they try to sync, and what the network does to them.

## Two decisions that determine whether this finds anything

**Generate by driving operations, never by constructing states.**

Phase 1 taught this the expensive way. Mutation M4 -- an OR-Set remove keyed on
the element instead of on observed tags -- passed the entire property suite,
because the strategies built values with the constructor and never called
`remove()`. **Laws over constructed values prove the algebra and say nothing
about whether the operations producing them are right.** At this scale the same
mistake would silently exempt every write path from the whole simulation, and
nothing would report it.

So every state change here goes through `Replica.write_*`.

**Bias hard toward concurrency.**

Uniform random writes over a large record space almost never produce two
concurrent edits to the same field, which is the only interesting case. The
generator uses a deliberately tiny record space, a high write rate, and long
partitions, so collisions are the norm rather than an accident. If the mutation
suite's detection times get worse, this is the first place to look -- a generator
that has stopped producing concurrency fails nothing except the experiment.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from dhara.lattice import (
    LWWRegister,
    MeasurementSeries,
    ORSet,
    StatusLattice,
    join_from_total_order,
)
from dhara.schema import Field, Record, Schema
from sim.clock import EPOCH_MS, VirtualTime, make_device_clock
from sim.invariants import Violation, check_all
from sim.loop import Event, EventLoop
from sim.network import PROFILES, Message, Network, NetworkProfile
from sim.replica import OpLog, Operation, Replica, make_replica
from sim.rng import Rng

__all__ = ["Scenario", "SimResult", "Simulation", "generate", "PRESETS"]

SERVER_ID = "server"

#: Neutral field ids. The engine may not know what a record represents, and
#: neither may its test harness - `scripts/check_no_domain_imports.py` covers
#: `sim/` for exactly this reason.
STATUS_ORDER = ("s0", "s1", "s2", "s3")

BENCH_SCHEMA = Schema(
    "bench",
    (
        Field("m_a", "MeasurementSeries", scale=1),
        Field("m_b", "MeasurementSeries", scale=0),
        Field("d_a", "LWWRegister"),
        Field("d_b", "LWWRegister"),
        Field("st_a", "StatusLattice", order=join_from_total_order(list(STATUS_ORDER))),
        Field("set_a", "ORSet"),
    ),
)


@dataclass(frozen=True, slots=True)
class Scenario:
    """Everything a seed decided. Serialisable, so a failure is a value."""

    seed: int
    devices: int
    records: int
    writes: int
    profile: str
    horizon_ms: int
    crash_rate: float
    partition_rate: float

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Scenario:
        return cls(**data)


PRESETS: dict[str, dict[str, Any]] = {
    # Small, healthy, no faults. If a failure reproduces here, it is a merge bug
    # and not a network one - which is the first question to ask.
    "quiet": {"profile": "clean", "crash_rate": 0.0, "partition_rate": 0.0},
    # The default. Real 2G, real crashes, real partitions.
    "hostile": {"profile": "2g", "crash_rate": 0.05, "partition_rate": 0.25},
    # One device, six virtual months of accumulated writes. The shape of the
    # Phase 3 exit criterion, available early so the session design meets it.
    "six_months_offline": {
        "profile": "2g",
        "crash_rate": 0.02,
        "partition_rate": 0.6,
        "devices": 2,
        "records": 4,
        "writes": 600,
        "horizon_ms": 180 * 24 * 60 * 60 * 1000,
    },
}


def generate(seed: int, preset: str = "hostile") -> Scenario:
    rng = Rng(seed, "scenario")
    overrides = PRESETS[preset]

    return Scenario(
        seed=seed,
        devices=overrides.get("devices", rng.integer(2, 5)),
        # Deliberately tiny. A large record space is a concurrency-suppression
        # device dressed up as realism.
        records=overrides.get("records", rng.integer(1, 3)),
        writes=overrides.get("writes", rng.integer(10, 80)),
        profile=overrides["profile"],
        horizon_ms=overrides.get("horizon_ms", rng.integer(1, 30) * 24 * 60 * 60 * 1000),
        crash_rate=overrides["crash_rate"],
        partition_rate=overrides["partition_rate"],
    )


@dataclass(slots=True)
class SimResult:
    scenario: Scenario
    violations: list[Violation]
    events: int
    operations: int
    bytes_sent: int
    net_stats: dict[str, int]
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        head = f"seed {self.scenario.seed} [{self.scenario.profile}]"
        if self.ok:
            return (
                f"{head} OK - {self.operations} ops, {self.events} events, "
                f"{self.bytes_sent} bytes"
            )
        return f"{head} FAILED\n  " + "\n  ".join(str(v) for v in self.violations)


class Simulation:
    """One scenario, run to quiescence, then checked."""

    def __init__(self, scenario: Scenario, *, trace: bool = False) -> None:
        self.scenario = scenario
        self.rng = Rng(scenario.seed, "sim")
        self.time = VirtualTime(EPOCH_MS)
        self.loop = EventLoop(self.time)
        self.oplog = OpLog()
        self.trace_on = trace
        self.trace: list[dict[str, Any]] = []
        self.profile: NetworkProfile = PROFILES[scenario.profile]

        self.replicas: dict[str, Replica] = {}
        self._build_replicas()

        self.network = Network(
            self.loop,
            self.rng.child("net"),
            self.profile,
            self._on_message,
            self._on_window_opened,
        )
        self.loop.on("sim.write", self._on_write)
        self.loop.on("sim.sync", self._on_sync)
        self.loop.on("sim.crash", self._on_crash)
        self.loop.on("sim.restart", self._on_restart)
        self.loop.on("sim.partition", self._on_partition)
        self.loop.on("net.heal", self._on_heal)

        self._schedule()

    # -- construction ------------------------------------------------------

    def _build_replicas(self) -> None:
        scenario = self.scenario
        for index in range(scenario.devices):
            device_id = f"dev_{index}"
            clock = make_device_clock(
                device_id,
                self.rng.child("clock", device_id),
                self.time,
                horizon_ms=scenario.horizon_ms,
                hostile=scenario.profile != "clean",
            )
            self.replicas[device_id] = make_replica(
                device_id, BENCH_SCHEMA, clock, self.oplog
            )

        server_clock = make_device_clock(
            SERVER_ID,
            self.rng.child("clock", SERVER_ID),
            self.time,
            horizon_ms=scenario.horizon_ms,
            hostile=False,  # servers keep time; devices do not
        )
        self.replicas[SERVER_ID] = make_replica(
            SERVER_ID, BENCH_SCHEMA, server_clock, self.oplog, is_server=True
        )

    @property
    def devices(self) -> list[Replica]:
        return [r for r in self.replicas.values() if not r.is_server]

    def _schedule(self) -> None:
        scenario = self.scenario
        rng = self.rng.child("schedule")
        horizon = scenario.horizon_ms

        for device in self.devices:
            self.network.schedule_windows(device.replica_id, SERVER_ID, horizon_ms=horizon)
            self.network.schedule_windows(SERVER_ID, device.replica_id, horizon_ms=horizon)

        for _ in range(scenario.writes):
            self.loop.at(EPOCH_MS + rng.integer(0, horizon), "sim.write", None)

        # Sync attempts are generated independently of writes, so a device tries
        # to sync whether or not it has anything to say - which is what real
        # devices do, and what produces the empty-sync and duplicate-delivery
        # paths worth testing.
        for _ in range(max(4, scenario.writes // 2)):
            self.loop.at(EPOCH_MS + rng.integer(0, horizon), "sim.sync", None)

        for device in self.devices:
            if rng.chance(scenario.crash_rate * 4):
                at = EPOCH_MS + rng.integer(0, horizon)
                self.loop.at(at, "sim.crash", device.replica_id)
                self.loop.at(
                    at + rng.integer(1_000, 6 * 60 * 60 * 1000),
                    "sim.restart",
                    device.replica_id,
                )
            # Partitions are installed when their event fires, not at
            # scheduling time - otherwise every scenario would start partitioned
            # and the duration would mean nothing.
            if rng.chance(scenario.partition_rate):
                at = EPOCH_MS + rng.integer(0, horizon)
                self.loop.at(
                    at,
                    "sim.partition",
                    (
                        device.replica_id,
                        rng.integer(60_000, 10 * 24 * 60 * 60 * 1000),
                        rng.chance(0.4),
                    ),
                )

    # -- handlers ----------------------------------------------------------

    def _on_write(self, event: Event) -> None:
        del event
        rng = self.rng.child("write", self.loop.processed)
        device = rng.choice(self.devices)
        if device.down:
            return

        record_id = f"r{rng.integer(0, self.scenario.records - 1)}"
        actor = rng.choice(["w1", "w2", "s1"])
        now = self.time.now
        day = f"2026-05-{rng.integer(1, 3):02d}"
        kind = rng.integer(0, 9)

        if kind <= 4:
            field_name = rng.choice(["m_a", "m_b"])
            value = rng.integer(80, 84)
            taken_at = f"{day}T{rng.integer(8, 17):02d}:00"
            device.write_measurement(record_id, field_name, value, taken_at, actor, now)

            # Re-record the identical reading with a fresh HLC. This is the
            # C-02 shape: one physical event entered twice, or an operation
            # re-issued on another path. It is NOT the same as re-delivering
            # the same state - a duplicated message carries the original HLC
            # and dedups under any key.
            #
            # Added because mutation M5 - a dedup key that includes the HLC -
            # survived 1,000 seeds. The generator had no way to produce two
            # entries that differ only in their clock, so the one thing the
            # dedup key exists to reject was never attempted.
            if rng.chance(0.25):
                device.write_measurement(
                    record_id, field_name, value, taken_at, actor, now
                )
        elif kind <= 7:
            field_name = rng.choice(["d_a", "d_b"])
            value = rng.choice(["alpha", "beta", None])
            device.write_register(record_id, field_name, value, actor, now)
        elif kind == 8:
            device.write_status(record_id, "st_a", rng.choice(list(STATUS_ORDER)), now)
        elif rng.chance(0.5):
            device.write_tag(record_id, "set_a", rng.choice(["t1", "t2", "t3"]), now)
        else:
            device.remove_tag(record_id, "set_a", rng.choice(["t1", "t2", "t3"]), now)

        self._trace("write", device=device.replica_id, record=record_id)

    def _on_window_opened(self, source: str, dest: str) -> None:
        """Connectivity appeared: try to sync, after a small random delay.

        The delay matters. Without it every device in the block fires in the
        same millisecond when a shared window opens, which is a thundering herd
        rather than a schedule - and Phase 3's jittered backoff (WI-3.9) exists
        precisely because that is what really happens when a tower recovers.
        """
        if dest != SERVER_ID:
            return
        rng = self.rng.child("window", source, self.loop.processed)
        self.loop.after(rng.integer(0, 5_000), "sim.sync", source)

    def _on_sync(self, event: Event) -> None:
        rng = self.rng.child("sync", self.loop.processed)
        device = (
            self.replicas[event.payload]
            if isinstance(event.payload, str)
            else rng.choice(self.devices)
        )
        if device.down or device.is_server:
            return

        payload = device.snapshot()
        size = device.snapshot_bytes()
        self.network.send(Message(device.replica_id, SERVER_ID, size, payload))

        server = self.replicas[SERVER_ID]
        if not server.down:
            reply = server.snapshot()
            self.network.send(
                Message(SERVER_ID, device.replica_id, server.snapshot_bytes(), reply)
            )
        self._trace("sync", device=device.replica_id, bytes=size)

    def _on_message(self, message: Message) -> None:
        target = self.replicas.get(message.dest)
        if target is None or target.down:
            return
        target.apply(message.payload)
        target.commit()
        self._trace(
            "deliver",
            source=message.source,
            dest=message.dest,
            duplicate=message.duplicate_of is not None,
        )

    def _on_crash(self, event: Event) -> None:
        replica = self.replicas[event.payload]
        self._mark_crash_losses(replica)
        replica.crash()
        self._trace("crash", device=replica.replica_id)

    def _mark_crash_losses(self, replica: Replica) -> None:
        """Record which of this replica's writes die with it.

        An operation is crash-lost only if it is **both** absent from the
        replica's own durable state **and** absent from every other replica. If
        it reached the server before the power failed, it survives and the
        no-loss invariant must still demand it.

        The narrowness is the point. A wider rule would be a loophole that
        excuses genuine merge losses whenever a crash happened to occur in the
        same run.
        """
        durable = {
            rid: self.schema_decode(blob) for rid, blob in replica.durable.items()
        }
        others = [r for r in self.replicas.values() if r is not replica and not r.down]

        for op in self.oplog.originated_by(replica.replica_id):
            if self._present(durable.get(op.record_id), op):
                continue
            if any(self._present(o.records.get(op.record_id), op) for o in others):
                continue
            self.oplog.mark_crash_lost(op)

    def schema_decode(self, blob: str) -> Record:
        return BENCH_SCHEMA.decode_record(json.loads(blob))

    @staticmethod
    def _present(record: Record | None, op: Operation) -> bool:
        """Is this operation's effect visible in `record`?

        Checked against the *effect* rather than an operation id, because a
        replica stores merged state and has no memory of which operation put a
        value there - which is exactly the position a real replica is in.
        """
        if record is None:
            return False
        value = record.state.get(op.field)
        if op.kind == "measurement" and isinstance(value, MeasurementSeries):
            return op.dedup_key() in {
                (e.taken_at, e.recorded_by, e.value) for e in value.entries
            }
        if op.kind == "register" and isinstance(value, LWWRegister):
            return op.dedup_key() in {
                (o.hlc.encode(), o.author, o.value) for o in value.observations_
            }
        if op.kind == "tag" and isinstance(value, ORSet):
            return op.detail[0] in {t.element for t in value.adds}
        if op.kind == "status" and isinstance(value, StatusLattice):
            return True  # a status join is lossy by design; see phase-1-exit
        return False

    def _on_restart(self, event: Event) -> None:
        replica = self.replicas[event.payload]
        replica.restart()
        self._trace("restart", device=replica.replica_id)

    def _on_partition(self, event: Event) -> None:
        device_id, duration_ms, one_way = event.payload
        self.network.partition(
            device_id, SERVER_ID, duration_ms=duration_ms, one_way=one_way
        )
        # A one-way partition leaves the device able to send but unable to hear
        # the reply, which is the case that breaks resumable transfer and the
        # one symmetric partitions never produce.
        if not one_way:
            self.network.partition(
                SERVER_ID, device_id, duration_ms=duration_ms, one_way=False
            )
        self._trace("partition", device=device_id, one_way=one_way, ms=duration_ms)

    def _on_heal(self, event: Event) -> None:
        source, dest = event.payload
        self.network.heal(source, dest)

    def _trace(self, kind: str, **fields: Any) -> None:
        if self.trace_on:
            self.trace.append({"at": self.time.now, "kind": kind, **fields})

    # -- running -----------------------------------------------------------

    def run(self) -> SimResult:
        self.loop.run()
        self._settle()

        violations = check_all(list(self.replicas.values()), self.oplog)
        return SimResult(
            scenario=self.scenario,
            violations=violations,
            events=self.loop.processed,
            operations=len(self.oplog),
            bytes_sent=self.network.stats["bytes"],
            net_stats=dict(self.network.stats),
            trace=self.trace,
        )

    def _settle(self) -> None:
        """Heal everything, restart everyone, and let state finish propagating.

        Convergence is a property of replicas that have exchanged everything.
        Asserting it while a partition is still up would report a violation that
        is not one, and a harness that cries wolf gets ignored.

        Two full rounds: one to push every device's state to the server, one to
        push the merged result back out.
        """
        for device in self.devices:
            self.network.heal(device.replica_id, SERVER_ID)
            self.network.heal(SERVER_ID, device.replica_id)
            if device.down:
                device.restart()

        server = self.replicas[SERVER_ID]
        if server.down:
            server.restart()

        for device in self.devices:
            server.apply(device.snapshot())
        for device in self.devices:
            device.apply(server.snapshot())

    def scenario_json(self) -> str:
        return json.dumps(self.scenario.to_json(), sort_keys=True)
