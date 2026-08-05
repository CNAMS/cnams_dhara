# Simulation report

**Phase 2 · measured at commit 103, Python 3.12.4, single core (Apple Silicon)**

Companion to [deliberate-bug-experiment.md](deliberate-bug-experiment.md), which
is the evidence that these numbers mean anything.

---

## Status against the Phase 2 exit criteria

| Criterion | Target | Measured | |
|---|---|---|---|
| Randomised schedules converge, no measurement loss | 1,000,000 | **5,000** | ⛔ gate not run |
| Deliberate-bug experiment detects the injected fault | < 1,000 seeds | **seed 1** (M1) | ✅ |
| Experiment written up, including what it cannot catch | — | done | ✅ |
| Six fault classes injectable | 6 | 6 | ✅ |
| Every invariant has a test proving it can fail | — | 8 invariants, 11 tests | ✅ |
| `replay_seed.sh <n>` → rendered timeline in one command | — | works | ✅ |
| Identical seeds produce identical traces | — | verified | ✅ |
| Throughput | ≥ 500 schedules/s/core | **43/s/core, 206/s across 8** | ⚠ see below |
| Nightly sweep + regression corpus in the push pipeline | — | committed, never run | ⚠ |

**Phase 2 is not complete.** Two criteria are outstanding and both are recorded
here rather than rounded off.

---

## What was measured

```
5,000 schedules in 207.5s (24/s), 243,522 operations - all invariants held
```

Fault activity across a representative 20-seed sample:

| | |
|---|---|
| Messages sent | 6,880 |
| Delivered | 2,542 (37%) |
| Dropped — window closed | 3,953 |
| Dropped — partition | 258 |
| Dropped — loss | 225 |
| Duplicated | 98 |
| Reordered | 249 |

The delivery rate matters as a calibration figure. An earlier version scheduled
syncs at uniformly random times and delivered **4 messages out of 1,034** — the
network model was fully present and almost never exercised, and every invariant
passed for that reason. Devices now sync when a connectivity window opens, which
is both what real devices do and what makes the model bite.

---

## The two outstanding criteria

### Throughput: 43/s/core against a target of 500/s

**Still 12× short per core**, and reported as short rather than reframed.

Profiling — rather than guessing — found three fixable costs, worth 24/s → 43/s:

| Finding | |
|---|---|
| `snapshot_bytes()` re-serialised the entire state purely to measure it | Every sync serialised twice |
| `commit()` serialised to JSON | A commit models an fsync, not a wire crossing, and `Record`s are immutable — a reference is as durable as a copy |
| `Schema.field_names` rebuilt a tuple on every access | 135,000 constructions per 120-seed sample, for a value that cannot change |

Plus **absorption short-circuits** on every lattice: `join(a, b) == a` whenever
`b <= a`, which is exact by the lattice laws and is the common case here,
because a re-delivered snapshot is usually a subset of what the receiver holds.

What remains is **full-state serialisation**, which is inherent to Phase 2's
sync model — the simulator is currently paying the exact cost the delta design
exists to eliminate. Optimising it further would be optimising code that
WI-3.1 deletes.

**Sharding is the cheaper lever:** 206 schedules/s across 8 cores turns the
million-schedule gate from ~11.5 hours into ~80 minutes. Seeds are independent
worlds, so this changes nothing about determinism — seed 4471 produces the same
run whichever worker executes it.

**Re-measure per-core throughput after WI-3.1**, when the dominant cost is gone
and the number means something about the design rather than about a placeholder.

### The million-schedule sweep has not been run

5,000 is 0.5% of the gate. It is enough to have found two real defects
(seeds 1041 and 1424) and enough to establish that the harness is sensitive, but
it is not the exit criterion and is not reported as one.

---

## What the sweep found

Two defects, both in the **harness** rather than the engine — which is what a
harness that has never been run against real scale should be expected to
produce first.

| Seed | Defect |
|---|---|
| 49 | `removals_are_honoured` was written at element level and fired on a legitimate concurrent unobserved add (C-14). An invariant that reports correct behaviour trains you to ignore it. |
| 1041, 1424 | Crash-loss accounting covered writes but not removals. Fixing that exposed a worse defect: the survived-elsewhere check was *vacuously true* for a replica that never saw the add, so a real removal could be counted as surviving on the strength of another replica's ignorance — which would have excused a genuine resurrection. |

All three are in the regression corpus and run on every push.

⚠ **No defect has yet been found in `dhara` itself by the simulator.** That is
not a claim of correctness — it is a statement about how far the search has run.
The deliberate-bug experiment is what makes it meaningful: the harness is known
to catch five of seven injected faults, four within two seeds.

---

## Fault model

All six classes from roadmap §7.1 are injectable.

| Class | Where | Notes |
|---|---|---|
| Partitions | `sim/network.py` | Symmetric and **one-way**. The asymmetric case is what breaks resumable transfer and is common on real cellular links. |
| Loss, reordering, duplication | `sim/network.py` | Duplicates are **delayed by up to four hours**, outliving any dedup cache — an immediate duplicate tests almost nothing. |
| Bandwidth caps, abrupt window closure | `sim/network.py` | The window is re-checked at arrival, so a transfer in flight when it closes is lost **mid-byte**. |
| Clock skew and jumps | `sim/clock.py` | ±3 days offset, drift, discrete jumps. Plus **synchronised** devices — see below. |
| Crashes mid-write and mid-sync | `sim/replica.py` | Volatile state is lost; committed state survives. |
| — | | |

### One finding worth carrying forward

**Aggressive fault injection can suppress a bug class.** With every device's
clock offset randomly within ±3 days, two devices essentially never issue
timestamps in the same millisecond — so the `node_id` tiebreak almost never
breaks an actual tie, and a mutation removing it survives indefinitely.

A fraction of devices now run correct clocks, which is both more realistic and
the only way ties occur often enough to test. It did not make M3 detectable —
that turned out to be structural — but the reasoning generalises: **a fault that
is always on is a fault that hides whatever the healthy path would have
tested.**

---

## Invariants

| Invariant | Catches |
|---|---|
| `all_converged` | Replicas holding different state after quiescence |
| `derived_views_agree` | Same state, different value shown to a user |
| `no_measurement_lost` | A written measurement absent from a replica |
| `no_phantom_measurements` | A measurement present that nobody wrote, or a failed dedup |
| `no_observation_lost` | A register that discarded an observed value |
| `removals_are_honoured` | A removed tag resurrecting |
| `hlc_causality_respected` | A replica reissuing or regressing a timestamp |
| `no_duplicate_operation_ids` | `(replica_id, hlc)` collisions |
| `review_signals_deterministic` | Converged replicas emitting different signals |

Two rules govern them, and both exist because an invariant is easy to write in a
way that can never fail:

- **Every invariant has a test that injects a violation of it.** One never
  observed to fail is indistinguishable from `assert True`, and worse than
  nothing because it looks like coverage.
- **No invariant computes its expectation by calling the code under test.**
  `no_measurement_lost` derives what should be present from the harness's own
  oplog. Asking a `MeasurementSeries` what it deduplicated to would be asserting
  that the code agrees with itself.

---

## Determinism

Everything non-deterministic derives from the root seed:

- one seeded RNG, threaded explicitly, with **per-entity derived streams** so
  adding or removing a device leaves every other device's stream untouched —
  without which shrinking wanders sideways instead of narrowing;
- derivation via BLAKE2b rather than `hash()`, which is salted per process
  unless `PYTHONHASHSEED` is fixed, and one CI leg deliberately randomises it;
- events ordered by `(virtual_time, sequence)`, the sequence assigned
  monotonically at scheduling time — without it, two events in the same
  millisecond order by heap internals;
- no wall-clock reads anywhere reachable from a simulation.

```bash
./scripts/replay_seed.sh 1041          # full timeline
./scripts/replay_seed.sh 1041 r0       # one record
./scripts/replay_seed.sh 1041 r0 quiet # on a healthy network
```

That last form is the first diagnostic question: if a failure still reproduces
under `quiet`, it is a merge bug rather than a network one, which halves the
search space before any code is read.

---

## What this harness cannot see

Recorded here and in
[deliberate-bug-experiment.md](deliberate-bug-experiment.md#blind-spots); feeds
`docs/honest-tradeoffs.md` in Phase 6.

- **Tie-breaking bugs that depend on per-process state.** Both replicas share
  one interpreter, so they resolve ties identically. Real in production, where
  two devices are two processes.
- **Duplicate device ids (C-24).** The generator assigns unique ids by
  construction, so the catalogue's quietest failure cannot be generated at all.
  Handled at enrolment in Phase 5 instead.
- **Data races inside one device.** Single-threaded by design.
- **Android process death, doze, OEM battery killers, filesystem corruption on
  cheap flash.** Phase 6 field measurement.
- **Real 2G behaviour.** The profile is a guess made in week 7. WI-6.4 replaces
  it with measured window durations and throughput, and reports the delta.
