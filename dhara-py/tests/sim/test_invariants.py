"""Every invariant ships with a test that proves it can fail.

An invariant never observed to fail is indistinguishable from `assert True`,
and it is worse than nothing because it looks like coverage. Each test here
injects a violation of exactly one invariant and requires that invariant - and
ideally only that one - to report it.

The Phase 2 experiment makes the same argument at the level of the whole
harness. This file makes it at the level of each check, which is where a broken
invariant is cheapest to notice.
"""

from __future__ import annotations

import pytest

from dhara.hlc import HLC
from dhara.lattice import Entry, MeasurementSeries
from dhara.schema import Record
from sim import invariants
from sim.scenario import BENCH_SCHEMA, Simulation, generate

pytestmark = pytest.mark.sim


def _two_replica_sim() -> Simulation:
    sim = Simulation(generate(11, "quiet"))
    sim.run()
    return sim


def _entry(value: int, node: str = "dev_0", pt: int = 5_000) -> Entry:
    return Entry(
        value=value,
        taken_at="2026-05-01T10:00",
        recorded_by="w1",
        hlc=HLC(pt, 0, node),
    )


def _put(sim: Simulation, replica_id: str, record_id: str, field: str, value: object) -> None:
    replica = sim.replicas[replica_id]
    record = replica.records.get(record_id) or BENCH_SCHEMA.empty_record()
    replica.records[record_id] = Record(
        BENCH_SCHEMA, {**record.state, field: value}
    )


def test_a_clean_run_reports_nothing() -> None:
    """The baseline. If this fails, every test below is meaningless."""
    sim = _two_replica_sim()
    assert invariants.check_all(list(sim.replicas.values()), sim.oplog) == []


def test_all_converged_detects_divergence() -> None:
    sim = _two_replica_sim()
    target = next(iter(sim.oplog.record_ids()))
    _put(sim, "dev_0", target, "m_a", MeasurementSeries.of(_entry(999)))

    found = invariants.all_converged(list(sim.replicas.values()))
    assert found, "a replica holding different state was not detected"
    assert "m_a" in str(found[0])


def test_no_measurement_lost_detects_a_dropped_entry() -> None:
    sim = _two_replica_sim()
    target = next(
        op.record_id for op in sim.oplog.entries if op.kind == "measurement"
    )
    _put(sim, "server", target, "m_a", MeasurementSeries())

    found = invariants.no_measurement_lost(sim.oplog, list(sim.replicas.values()))
    assert found, "an emptied series was not reported as loss"
    assert "missing" in str(found[0])


def test_no_phantom_measurements_detects_an_invented_entry() -> None:
    """The direction that was missing until the experiment found it.

    A phantom reading is one a supervisor will act on, and it never happened.
    """
    sim = _two_replica_sim()
    target = next(iter(sim.oplog.record_ids()))
    series = sim.replicas["server"].records[target].state["m_a"]
    assert isinstance(series, MeasurementSeries)
    _put(sim, "server", target, "m_a", series.append(_entry(77, pt=9_999)))

    found = invariants.no_phantom_measurements(sim.oplog, list(sim.replicas.values()))
    assert found, "an invented measurement was not detected"
    assert "nobody wrote" in str(found[0])


def test_no_phantom_measurements_detects_a_failed_dedup() -> None:
    """Two entries sharing a dedup key, both legitimately written.

    Distinct from the invented-entry case: every key is expected, but the
    collapse did not happen. This is the shape mutation M5 produces.
    """
    sim = _two_replica_sim()
    op = next(o for o in sim.oplog.entries if o.kind == "measurement")
    taken_at, actor, value = op.detail
    duplicated = MeasurementSeries(
        frozenset(
            {
                Entry(value=value, taken_at=taken_at, recorded_by=actor,
                      hlc=HLC(1_000, 0, "dev_0")),
                Entry(value=value, taken_at=taken_at, recorded_by=actor,
                      hlc=HLC(2_000, 0, "dev_1")),
            }
        )
    )
    _put(sim, "server", op.record_id, op.field, duplicated)

    found = invariants.no_phantom_measurements(sim.oplog, list(sim.replicas.values()))
    assert found, "two entries sharing a dedup key were not detected"
    assert "dedup did not collapse" in str(found[-1])


def test_no_observation_lost_detects_a_discarded_loser() -> None:
    from dhara.lattice import LWWRegister

    sim = _two_replica_sim()
    op = next((o for o in sim.oplog.entries if o.kind == "register"), None)
    if op is None:
        pytest.skip("this seed wrote no registers")
    _put(sim, "server", op.record_id, op.field, LWWRegister())

    found = invariants.no_observation_lost(sim.oplog, list(sim.replicas.values()))
    assert found, "an emptied register was not reported as loss"


def test_hlc_causality_detects_a_reissued_timestamp() -> None:
    sim = _two_replica_sim()
    first = sim.oplog.entries[0]
    sim.oplog.entries.append(
        type(first)(
            replica_id=first.replica_id,
            record_id=first.record_id,
            field=first.field,
            kind=first.kind,
            hlc=HLC(0, 0, first.hlc.node_id),  # strictly below anything issued
            detail=first.detail,
            at=first.at,
        )
    )
    found = invariants.hlc_causality_respected(sim.oplog)
    assert found, "a regressed timestamp was not detected"


def test_no_duplicate_operation_ids_detects_a_collision() -> None:
    sim = _two_replica_sim()
    sim.oplog.entries.append(sim.oplog.entries[0])
    found = invariants.no_duplicate_operation_ids(sim.oplog)
    assert found, "a reused operation id was not detected"


def test_derived_views_agree_detects_a_disagreement() -> None:
    """The invariant added because M3 escaped.

    Canonical state can match while the value a worker actually sees differs.
    """
    from dhara.lattice import LWWRegister, Observation

    sim = _two_replica_sim()
    target = next(iter(sim.oplog.record_ids()))
    shared = frozenset(
        {
            Observation("alpha", HLC(1_000, 0, "dev_0"), "w1"),
            Observation("beta", HLC(1_000, 0, "dev_1"), "w2"),
        }
    )
    # Every replica, not just two: this seed has more than two devices, and a
    # replica left holding its original value is a genuine disagreement that
    # the invariant is right to report.
    for replica_id in sim.replicas:
        _put(sim, replica_id, target, "d_a", LWWRegister(shared))

    # Same state on both, so all_converged is quiet for this field.
    assert not invariants.derived_views_agree(list(sim.replicas.values())), (
        "identical state should produce identical derived views"
    )

    _put(
        sim,
        "server",
        target,
        "d_a",
        LWWRegister(frozenset({Observation("gamma", HLC(9_000, 0, "dev_9"), "w3")})),
    )
    assert invariants.derived_views_agree(list(sim.replicas.values())), (
        "a differing current value was not detected"
    )


def test_removals_are_honoured_detects_a_resurrection() -> None:
    from dhara.lattice import ORSet

    sim = Simulation(generate(11, "quiet"))
    sim.run()

    device = sim.replicas["dev_0"]
    target = "r0"
    device.write_tag(target, "set_a", "t9", sim.time.now)
    tag = next(t for t in device.records[target].state["set_a"].adds if t.element == "t9")
    device.remove_tag(target, "set_a", "t9", sim.time.now)

    # Resurrect it: the add is back and its tag is no longer marked removed,
    # which is exactly what an element-keyed remove produces on the next merge.
    _put(sim, "dev_0", target, "set_a", ORSet(frozenset({tag}), frozenset()))

    found = invariants.removals_are_honoured(sim.oplog, list(sim.replicas.values()))
    assert found, "a resurrected tag was not detected"
    assert "resurrected" in str(found[0])


def test_removals_are_honoured_allows_a_concurrent_unobserved_add() -> None:
    """C-14 is correct behaviour and must not be reported.

    The element-level version of this invariant fired here, on seed 49. An
    invariant that reports correct behaviour trains you to ignore its output,
    which is as damaging as one that misses a bug.
    """
    from dhara.lattice import ORSet, Tagged

    sim = Simulation(generate(11, "quiet"))
    sim.run()

    device = sim.replicas["dev_0"]
    device.write_tag("r0", "set_a", "t9", sim.time.now)
    device.remove_tag("r0", "set_a", "t9", sim.time.now)

    unobserved = Tagged("t9", HLC(9_999, 0, "dev_other"))
    for replica_id in sim.replicas:
        current = sim.replicas[replica_id].records.get("r0")
        if current is None:
            continue
        existing = current.state["set_a"]
        _put(
            sim,
            replica_id,
            "r0",
            "set_a",
            ORSet(existing.adds | {unobserved}, existing.removed_tags),
        )

    assert "t9" in sim.replicas["dev_0"].records["r0"].state["set_a"].elements
    assert not invariants.removals_are_honoured(sim.oplog, list(sim.replicas.values())), (
        "a concurrent add the remove never observed was wrongly reported"
    )
