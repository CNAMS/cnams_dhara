# Phase 2 — The simulator

**Weeks 6–9 · ~56 hours · ~115 commits**

> **Build this before the network layer.** It will shape the design of everything
> after it. — roadmap §8, Phase 2

**Exit criteria (roadmap):**
- 1,000,000 randomised schedules converge with no measurement loss.
- The deliberate-bug experiment (§7.1) finds the injected fault within 1,000 seeds,
  and the experiment is written up.

---

## Why this is the phase that matters

Roadmap §7 states the honest weakness this project has to answer: *an LLM — or a
tired student at 2 AM — will happily write a sync layer that looks correct and loses
data under one specific interleaving.* Property tests do not find those. They test
one lattice at a time, with no network, no partitions, no crashes.

The simulator is the thing that turns "I believe this is correct" into "here is a
million-schedule search that failed to find a counterexample, and here is proof the
search would have found one."

**The second half of that sentence is the whole point.** A harness that never fails
is a harness that is not testing anything (roadmap §7.1). WI-2.17 is the most
credible artifact this repository will produce, and everything before it exists to
make it possible.

```
 seed ──▶ scenario generator ──▶ schedule of events
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
      virtual clocks          virtual network          virtual replicas
      (skew, jumps)      (partition/loss/dup/cap)     (devices + server)
              └───────────────────────┼───────────────────────┘
                                      ▼
                            invariant checkers
                                      │
                    pass ──────────────┴────────────── fail
                                                         │
                                            shrink ──▶ replay ──▶ trace
                                                         │
                                              regression corpus (forever)
```

⚠ **Timebox: 4 weeks.** Roadmap §10 flags "simulator becomes a project of its own"
as a medium risk. It only needs to inject the six fault classes listed in §7.1. A
discrete-event framework with a plugin architecture is not in scope.

---

## Work items

### WI-2.0 — Simulator architecture decision `[research]`

**Why** Getting the execution model wrong here costs the whole phase.

**Touches** `docs/adr/0007-simulator-execution-model.md`

**Decision to record:** single-threaded, single-process, **event-loop over a
priority queue of scheduled events**, virtual time only. No threads, no asyncio, no
real sleeping.

Rationale: threads make determinism a function of the OS scheduler, which is
precisely the thing that must be under the seed's control. FoundationDB and
TigerBeetle both run their simulations single-threaded for this reason.

**Commit ladder**
1. `docs: add ADR-0007 choosing a single-threaded virtual-time event loop`
2. `docs: record why threads and asyncio are excluded from the simulator`
3. `docs: define the six fault classes the simulator must inject`

---

### WI-2.1 — Determinism harness `[gate]`

**Why** Every later claim in this phase is void if a run is not reproducible from
its seed.

**Touches** `sim/rng.py`, `scripts/check_no_ambient_nondeterminism.py`

**Done when** The same seed produces byte-identical event traces across two runs,
two Python versions, and two values of `PYTHONHASHSEED`.

**Commit ladder**
1. `feat(sim): add a seeded RNG wrapper threaded explicitly through the simulation`
2. `feat(py): add a lint check rejecting module-level random, time and uuid use`
3. `ci: run the ambient-nondeterminism check on sim and dhara`
4. `test(sim): identical seeds produce identical event traces`
5. `test(sim): traces are stable across PYTHONHASHSEED values`
6. `feat(sim): derive all per-entity RNG streams from the root seed`
7. `test(sim): adding a device does not change another device's random stream`

⚠ Rung 6/7 are subtle and worth the effort. If all entities draw from one shared
stream, adding a device to a scenario reshuffles every other device's behaviour, and
shrinking becomes useless because removing one device changes everything else. Derive
a child stream per entity from `(root_seed, entity_id)`.

---

### WI-2.2 — Virtual clock with skew

**Why** Roadmap §7.1 fault class: per-device clock skew and clock jumps.

**Touches** `sim/clock.py`

**Depends on** WI-2.1

**Commit ladder**
1. `feat(clock): add virtual global time advanced only by the event loop`
2. `feat(clock): add per-device clock offset drawn from the seeded rng`
3. `feat(clock): support offsets up to plus or minus three days`
4. `feat(clock): add clock drift so device time diverges gradually`
5. `feat(clock): add discrete clock jumps forward and backward`
6. `test(clock): device time is a pure function of global time and device state`
7. `test(clock): a jump never rewinds an HLC issued by that device`
8. `feat(clock): wire the device clock into the dhara HLC physical_time callable`

Rung 8 is the payoff for WI-1.2's injected `physical_time`. If that rung had been
skipped, this phase would be blocked here.

---

### WI-2.3 — Virtual network: delivery

**Why** The substrate every fault is a perturbation of.

**Touches** `sim/network.py`

**Commit ladder**
1. `feat(net): add a message type with source, destination, size and payload`
2. `feat(net): deliver messages through the event queue with a latency model`
3. `feat(net): draw latency from a seeded distribution per link`
4. `test(net): a message sent is a message delivered on a healthy link`
5. `test(net): delivery order matches send order on a healthy link`
6. `feat(net): expose per-link statistics for the metrics layer`

---

### WI-2.4 — Fault: partitions

**Touches** `sim/network.py`, `sim/faults.py`

**Commit ladder**
1. `feat(net): add link state - up, down, and one-way`
2. `feat(net): schedule partitions with a start time and duration`
3. `feat(net): support asymmetric partitions where only one direction fails`
4. `test(net): messages sent during a partition are not delivered`
5. `test(net): a partition healing does not deliver messages sent while down`
6. `feat(net): add partition topologies - single device, subset, and total`
7. `test(net): a device partitioned for six virtual months still converges after`

⚠ Rung 3 is the one that finds real bugs. Symmetric partitions are the easy case;
a device that can send but not receive acks is the case that breaks resumable
transfer, and it is common on real cellular links.

---

### WI-2.5 — Fault: loss, reordering, duplication

**Touches** `sim/network.py`

**Commit ladder**
1. `feat(net): drop messages at a seeded per-link loss rate`
2. `feat(net): reorder in-flight messages within a bounded window`
3. `feat(net): duplicate messages at a seeded rate`
4. `feat(net): support duplicate delivery separated by an arbitrary delay`
5. `test(net): loss rate over a long run matches the configured rate`
6. `test(net): reordering never delivers a message before it was sent`
7. `test(net): duplication produces byte-identical copies`

Rung 4 is deliberate: an immediate duplicate is caught by any dedup cache. A
duplicate that arrives four hours later, after the cache has been evicted, is the
one that tests catalogue C-22 honestly.

---

### WI-2.6 — Fault: bandwidth caps and window closure

**Why** The defining constraint: a 90-second window at 20 kbps that dies
mid-transfer. → roadmap §6.3

**Touches** `sim/network.py`

**Commit ladder**
1. `feat(net): add a per-link bandwidth cap in bits per second`
2. `feat(net): model transfer time as a function of message size and cap`
3. `feat(net): add connectivity windows with a start, duration and jitter`
4. `feat(net): close a window abruptly mid-transfer, discarding the partial frame`
5. `feat(net): add a 2G profile - 20 kbps, 90 second windows, high jitter`
6. `test(net): a message larger than the window cannot complete in one window`
7. `test(net): partial transfer at window close loses exactly the untransferred part`
8. `feat(net): add a profile registry so scenarios name a network rather than tune it`

⚠ Rung 4 is where "resume from the last ack, never from zero" gets tested for real.
The simulator must be able to close the window at an arbitrary byte offset, not just
between messages — otherwise Phase 3's chunking is being tested against a friendlier
network than the one it will meet.

---

### WI-2.7 — Virtual device replica

**Touches** `sim/device.py`

**Depends on** WI-2.2, Phase 1

**Commit ladder**
1. `feat(sim): add a virtual device holding a dhara record store`
2. `feat(sim): give each device an identity, a clock and an rng stream`
3. `feat(sim): add local write operations driven by the scenario`
4. `feat(sim): maintain a per-device outbox of unsynced operations`
5. `feat(sim): apply received operations through the schema join`
6. `test(sim): a device's local state reflects its own writes immediately`
7. `feat(sim): record every operation a device originates into the oplog`
8. `feat(sim): support multiple workers per device for catalogue C-17`

Rung 7 is what makes the no-loss invariant checkable at all: the ground truth is the
oplog of everything anyone ever wrote, held by the simulation harness, never by a
replica.

---

### WI-2.8 — Virtual server replica

**Touches** `sim/server.py`

**Design note:** the server is a **full replica** applying the same joins, not a
special authority. That resolves open question Q3, and the reason is that it halves
the state space — there is one merge implementation under test, not two.

**Commit ladder**
1. `feat(sim): add a virtual server as a full replica applying the same joins`
2. `feat(sim): accept operations from any device and merge them`
3. `feat(sim): track per-device delivery state on the server`
4. `test(sim): the server converges with a single device with no faults`
5. `docs: resolve open question Q3 - the server is a full replica`

---

### WI-2.9 — Scenario generator

**Why** The seed's job is to pick a whole world, not just a coin flip.

**Touches** `sim/scenario.py`

**Commit ladder**
1. `feat(sim): generate a scenario from a seed - devices, records, duration`
2. `feat(sim): generate write operations weighted by field kind`
3. `feat(sim): generate sync attempts at seeded intervals`
4. `feat(sim): generate the fault schedule from the network profile`
5. `feat(sim): support scenario serialisation to json for replay and reporting`
6. `test(sim): a serialised scenario replays to an identical trace`
7. `feat(sim): add scenario presets - quiet, hostile, six-months-offline`
8. `feat(sim): bias generation toward concurrent edits on the same record`

⚠ Rung 8 is the difference between a simulator that runs a million schedules and one
that tests anything. Uniform random writes across a large record space almost never
produce two concurrent edits to the same field, which is the only interesting case.
Bias hard: small record space, high write rate, long partitions.

---

### WI-2.10 — Invariant: convergence `[gate]`

**Touches** `sim/invariants.py`

**Commit ladder**
1. `feat(sim): add invariant framework reporting the violating entity and state`
2. `feat(sim): add all_converged comparing canonical replica states`
3. `feat(sim): drive replicas to quiescence before checking convergence`
4. `test(sim): a healthy run converges`
5. `test(sim): an injected divergence is detected by all_converged`
6. `feat(sim): report convergence failures as a field-wise diff between replicas`

Rung 3 is a correctness requirement of the *check*, not the system: replicas that
have not exchanged everything are legitimately different. Convergence is asserted
after the network is healed and all queues have drained.

---

### WI-2.11 — Invariant: no measurement lost `[gate]`

**Why** The headline property. Roadmap: *a measurement that a worker recorded must
never disappear because of a merge.*

**Touches** `sim/invariants.py`

**Commit ladder**
1. `feat(sim): add no_measurement_lost comparing the oplog to final server state`
2. `feat(sim): account for legitimate dedup when counting expected entries`
3. `test(sim): a dropped append is detected`
4. `test(sim): a legitimate duplicate delivery is not reported as a loss`
5. `feat(sim): report the exact missing entries with their originating device`
6. `feat(sim): extend the check to every replica, not just the server`

⚠ Rung 2 is where this invariant is easiest to get wrong in the *lenient* direction.
If the expected count is computed by running the same dedup logic under test, the
invariant is circular and will never fail. Compute expected entries from the oplog
using the **declared dedup key applied independently**, in the harness, not by
calling into `dhara`.

---

### WI-2.12 — Invariants: monotonicity and idempotence

**Touches** `sim/invariants.py`

**Commit ladder**
1. `feat(sim): add version_vectors_monotonic over the oplog`
2. `feat(sim): add no_duplicate_application keyed on operation id`
3. `feat(sim): add hlc_causality_respected across all delivered messages`
4. `feat(sim): add review_signals_are_deterministic across replica orderings`
5. `test(sim): each invariant detects its own injected violation`
6. `feat(sim): run all invariants after every schedule and report all failures`

Rung 5 is a standing rule for this file: **every invariant ships with a test that
proves it can fail.** An invariant that has never been observed to fail is
indistinguishable from `assert True`.

Rung 4 is easy to miss and matters for Phase 4: if replica order changes which review
signals are emitted, then the Dart implementation will disagree with Python for
reasons that are not merge bugs.

---

### WI-2.13 — Crash injection

**Why** Roadmap §7.1 fault class: crashes mid-write and mid-sync.

**Touches** `sim/faults.py`

**Commit ladder**
1. `feat(sim): add a crash event that discards a device's volatile state`
2. `feat(sim): model durable state so a restart recovers what was committed`
3. `feat(sim): crash between the write and the durable commit`
4. `feat(sim): crash mid-sync with a partially applied batch`
5. `test(sim): a crash before commit loses only the uncommitted operation`
6. `test(sim): a crash mid-sync does not double-apply on resume`
7. `feat(sim): add a restart delay so a crashed device rejoins mid-partition`

⚠ Rung 3 is a real design constraint surfacing early: it forces the question of what
"committed" means locally, which Phase 4's SQLite store has to answer. Getting the
question in week 8 rather than week 15 is exactly why the simulator comes first.

---

### WI-2.14 — Seed sweep runner

**Touches** `sim/runner.py`, `scripts/replay_seed.sh`

**Commit ladder**
1. `feat(sim): add a runner executing a seed range and collecting failures`
2. `feat(sim): shard a seed range across processes`
3. `feat(sim): report throughput in schedules per second`
4. `feat(sim): write failures to a machine-readable report`
5. `perf(sim): profile and remove the top hot spot in the event loop`
6. `perf(sim): disable tracing by default in sweeps`
7. `feat(sim): add a progress line so a long sweep is observable`

**Throughput target: ≥ 500 schedules/second/core.** A million schedules must be an
overnight job, not a week. If it is slower, the scenarios are too large — shrink the
record space, not the fault variety.

---

### WI-2.15 — Shrinking

**Why** A failure at seed 4471 with 12 devices, 400 operations and 30 faults is a
failure you cannot debug. Shrinking turns it into three operations.

**Touches** `sim/runner.py`

**Commit ladder**
1. `feat(sim): shrink by reducing device count while the failure persists`
2. `feat(sim): shrink by removing operations while the failure persists`
3. `feat(sim): shrink by removing faults while the failure persists`
4. `feat(sim): shrink by shortening the simulated duration`
5. `test(sim): shrinking a known failure yields a minimal reproducer`
6. `feat(sim): emit the shrunk scenario as a standalone json test case`
7. `feat(sim): bound shrinking time so it never dominates a sweep`

---

### WI-2.16 — Replay and tracing

**Touches** `sim/runner.py`, `scripts/replay_seed.sh`

**Commit ladder**
1. `feat(sim): add a trace mode writing every event as jsonl`
2. `feat(sim): include causal context - device, clock, hlc - on every trace event`
3. `feat(sim): replay a seed and assert the trace matches a stored one`
4. `feat(sim): add a human-readable timeline renderer for a single record`
5. `chore: add replay_seed.sh going from a seed to a rendered timeline`
6. `docs: document the failure-to-diagnosis workflow`

**The workflow this WI exists to produce:** `./scripts/replay_seed.sh 4471` prints a
timeline of everything that happened to the record that broke. One command. If it
takes more than one command, it will not be used at 11 PM, and the simulator's value
drops by half.

---

### WI-2.17 — The deliberate-bug experiment `[gate]`

**Why** Roadmap §7.1, verbatim: *"deliberately introduce a known-bad merge — swap a
series append for an overwrite — and confirm the simulator finds it within 1,000
seeds. A harness that never fails is a harness that is not testing anything. Document
this experiment; it is the single most credible artifact in the repo."*

**Touches** `sim/faults.py`, `docs/deliberate-bug-experiment.md`

**Depends on** everything above

**Done when** Each injected bug is caught, the seed count to first detection is
recorded, and the write-up exists.

**Mutations to inject** — more than one, because one is an anecdote:

| # | Mutation | Should be caught by | Expected |
|---|---|---|---|
| M1 | `MeasurementSeries.join` overwrites instead of appending | `no_measurement_lost` | < 50 seeds |
| M2 | `LWWRegister.join` discards the loser | `no_measurement_lost` (history) | < 200 seeds |
| M3 | HLC tie-break drops `node_id` | `all_converged` | < 500 seeds |
| M4 | `ORSet` remove keys on element, not observed tags | `all_converged` | < 500 seeds |
| M5 | Dedup key includes the HLC | `no_duplicate_application` | < 1,000 seeds |
| M6 | Operation IDs reused across a device restart | `no_duplicate_application` | < 1,000 seeds |

**Commit ladder**
1. `feat(sim): add a mutation harness that patches a merge function for one run`
2. `feat(sim): add mutation M1 - series append replaced by overwrite`
3. `test(sim): M1 is detected by no_measurement_lost within 1000 seeds`
4. `feat(sim): add mutation M2 - lww register discards the loser`
5. `test(sim): M2 is detected within 1000 seeds`
6. `feat(sim): add mutation M3 - hlc tie-break drops the node id`
7. `test(sim): M3 is detected by all_converged within 1000 seeds`
8. `feat(sim): add mutation M4 - orset remove keys on element not tags`
9. `test(sim): M4 is detected within 1000 seeds`
10. `feat(sim): add mutation M5 - dedup key includes the hlc`
11. `test(sim): M5 is detected within 1000 seeds`
12. `feat(sim): add mutation M6 - operation ids reused after restart`
13. `test(sim): M6 is detected within 1000 seeds`
14. `feat(sim): record seeds-to-detection for every mutation`
15. `docs: write up the deliberate-bug experiment with per-mutation results`
16. `docs: record which mutations the harness does NOT catch, and why`
17. `ci: run the mutation suite nightly so harness sensitivity cannot regress`

⚠ **Rung 16 is the most valuable rung in the phase.** Every mutation harness has
blind spots. Catalogue C-24 (duplicate device IDs) is one already known — the
generator assigns unique IDs by construction, so no mutation can produce it. Writing
down what the harness cannot see is what separates an honest correctness claim from a
marketing one, and it feeds directly into `docs/honest-tradeoffs.md` in Phase 6.

⚠ Rung 17 exists because harness sensitivity **decays**. A refactor in Phase 3 that
accidentally makes the scenario generator less adversarial will not fail any test —
except this one.

---

### WI-2.18 — Nightly CI and the regression corpus

**Touches** `.github/workflows/sim-nightly.yml`, `tests/sim/regressions/`

**Commit ladder**
1. `ci: add a nightly sharded seed sweep`
2. `ci: upload the seed, scenario and trace as artifacts on failure`
3. `ci: open an issue automatically when an invariant is violated`
4. `test(sim): add the regression corpus runner reading seeds.txt`
5. `ci: run the regression corpus on every push`
6. `docs: document the rule - every simulator-found bug becomes a permanent seed`
7. `ci: add a fast smoke sweep of 2000 seeds to the push pipeline`

**The rule, stated once so it is never negotiable:** every bug the simulator finds
gets its shrunk seed appended to `seeds.txt` in the same commit as the fix, with the
`Seed:` footer. That corpus is the most valuable file in the repository by month
four, and it costs nothing to maintain.

---

### WI-2.19 — The million-schedule sweep `[gate]`

**Why** Direct exit criterion.

**Commit ladder**
1. `feat(sim): add a milestone sweep mode with checkpointing and resume`
2. `docs: record the phase 2 million-schedule sweep configuration`
3. `docs: record the million-schedule sweep results with throughput and coverage`
4. `docs: record the scenario-space coverage this sweep does and does not reach`

⚠ Rung 4 keeps the headline honest. "One million schedules converged" is only
meaningful alongside what was varied: how many devices, how long offline, which fault
combinations, and — importantly — which combinations were *never* generated. Report
both numbers.

---

### WI-2.20 — Simulation report

**Touches** `docs/simulation-report.md`

**Commit ladder**
1. `docs: add the simulation report with the fault model and invariant list`
2. `docs: add the seeds-to-detection table for every mutation`
3. `docs: add the sweep results and throughput figures`
4. `docs: add the known blind spots of the harness`
5. `docs: link the simulation report from the README`

---

### WI-2.21 — Phase 2 exit review `[gate]`

**Commit ladder**
1. `docs(plan): record phase 2 exit checklist results`
2. `docs: add changelog entry for the deterministic simulator`
3. `chore: tag phase-2-complete`

---

## Exit checklist

- [ ] **1,000,000 randomised schedules** run with all invariants green, and the
      configuration is recorded.
- [ ] **The deliberate-bug experiment**: all six mutations detected, each within
      1,000 seeds, seeds-to-detection recorded per mutation.
- [ ] The experiment is written up in `docs/deliberate-bug-experiment.md`, including
      what the harness **cannot** catch.
- [ ] All six roadmap §7.1 fault classes injectable: partitions, loss/reorder/dup,
      clock skew and jumps, crashes mid-write and mid-sync, bandwidth caps, abrupt
      window closure.
- [ ] Every invariant has a test proving it can fail.
- [ ] `./scripts/replay_seed.sh <n>` goes from a seed to a rendered timeline in one
      command.
- [ ] Shrinking reduces a known failure to a minimal reproducer.
- [ ] Identical seeds produce identical traces across Python versions and hash seeds.
- [ ] Throughput ≥ 500 schedules/second/core.
- [ ] Nightly sweep running; regression corpus runner in the push pipeline.
- [ ] `phase-2-complete` tag pushed.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| **The simulator becomes the project** | Week 9 arrives, sweep not run, but there is a plugin system | Timebox is binding. Six fault classes, four invariants, one runner. Delete the rest. |
| Scenarios are too gentle to find anything | A million schedules pass on the first attempt, and mutations take >1,000 seeds to catch | The mutation detection times are the calibration signal. If M1 is not caught in <50 seeds, the generator is not producing concurrent edits. Fix the generator, not the invariant. |
| Invariants are circular | `no_measurement_lost` calls into `dhara`'s dedup | Compute expected state independently in the harness. WI-2.11 rung 2. |
| Non-determinism creeps back | Same seed, different trace | The lint rule in WI-2.1 covers the common causes; the residual is usually a `set` iteration somewhere in `dhara`. |
| Sweep too slow to be useful | <100 schedules/sec | Shrink the record space, not the fault variety. Concurrency density is what finds bugs, not scale. |
| Starting Phase 3 before the gate | Any `session` scope commit before `phase-2-complete` | Stop. The roadmap is explicit: the simulator shapes the design of everything after it. Writing the session layer first wastes the phase. |
