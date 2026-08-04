# dhara

**An offline-first sync engine for last-mile field data — and specifically, the
conflict-resolution layer that generic sync engines leave to you.**

---

## The problem

An Anganwadi worker records a child's weight on an Android phone, in a village,
on a network that appears for ninety seconds at a time or not at all.

The government system she is required to use allows offline entry for up to three
days. Daily upload is mandatory. A worker whose upload fails can be recorded as
non-operational, which affects her efficiency report.

So the failure mode is not "data arrives late." The failure mode is that a worker
who did her job is marked as if she did not, because of infrastructure she does
not control.

## The engineering problem, stated precisely

> Build a data synchronisation layer for longitudinal child health records that is
> correct under arbitrary offline duration, arbitrary clock skew, hostile networks,
> shared devices, and 2GB-RAM hardware — and that can prove it is correct.

Three properties matter more than anything else:

1. **No silent data loss.** A measurement a worker recorded must never disappear
   because of a merge.
2. **Convergence.** Any two replicas that have seen the same set of operations, in
   any order, reach the same state.
3. **Bounded bandwidth.** A sync makes forward progress inside a 90-second,
   20 kbps window and resumes from where it stopped.

## What is actually being built here

By 2026 the local-first ecosystem is mature — Automerge, Yjs, cr-sqlite,
PowerSync, ElectricSQL, RxDB, WatermelonDB. This project does not compete with
them.

The gap is downstream. ElectricSQL defaults to last-write-wins. PowerSync makes
conflict resolution your server API's problem. Both hand you the hard question and
walk away. Nobody has written that resolution layer for longitudinal child health
records under Indian last-mile constraints, nor tested one to the standard this
project sets.

**A child's weight is not a mutable field. It is an event that happened at a
time.** Two different weights recorded on the same morning is clinically
meaningful information — bad scale, wrong child, transcription error — that
last-write-wins destroys.

`dhara` never imports a domain model, never knows what a child is, and never has a
table name hardcoded. It receives a schema descriptor at runtime.

## Repository contents

| Path | What it is |
|---|---|
| [dhara-sync-engine-roadmap.md](dhara-sync-engine-roadmap.md) | The design document. Problem, architecture, correctness strategy, risks. **Read this first.** |
| [EXECUTION.md](EXECUTION.md) | The execution plan index — 24 weeks, 7 phases, week-by-week. |
| [plan/](plan/) | Per-phase work breakdowns, down to individual commits. |
| [DOUBTS.md](DOUBTS.md) | Every assumption execution is resting on, and what it costs if wrong. |
| [LEFTOVER.md](LEFTOVER.md) | What remains, what is blocked, and what cannot be done from a keyboard. |
| `spec/` | Wire protocol, merge semantics, conflict catalogue, conformance vectors. *(Phase 0+)* |
| `dhara-py/` | Python implementation + deterministic simulator. *(Phase 1+)* |
| `dhara-dart/` | Dart implementation for the Flutter client. *(Phase 4+)* |

## Status

**Phase 1 — clock layer done, lattice layer in progress.**

| | |
|---|---|
| `spec/` | 24-entry conflict catalogue, merge semantics, protocol v0.1 **draft**, conformance vector schema, 6 HLC vectors |
| `dhara-py/` | Hybrid logical clock, conformance runner, dependency-rule checker. 65 tests green. |
| `dhara-dart/` | Not started — Phase 4 |

Phase 0 is **not** tagged complete: the field-access conversation has not happened
and CI has never been executed by a runner. See [LEFTOVER.md](LEFTOVER.md).

Progress: [plan/tracking-board.md](plan/tracking-board.md).

## How correctness is established

Not by "it works on my phone."

- **Deterministic simulation testing.** N virtual devices and a virtual server in a
  single process, with a seeded PRNG driving partitions, packet loss, reordering,
  duplication, clock skew, mid-write crashes, and bandwidth caps. Invariants
  asserted after every schedule. Seed 4471 fails, seed 4471 replays exactly.
- **The deliberate-bug experiment.** A known-bad merge is injected on purpose and
  the simulator must find it within 1,000 seeds. A harness that never fails is a
  harness that is not testing anything.
- **Property-based tests.** Commutativity, associativity, idempotence for every
  lattice type, 10,000 randomised operation orders each.
- **Conformance vectors.** Language-agnostic JSON fixtures that the Python and Dart
  implementations both run. Divergence is a build failure.

## Licence

[Apache-2.0](LICENSE) — chosen over MIT for the explicit patent grant, since this work
may end up adjacent to a government programme. See
[ADR-0003](docs/adr/0003-apache-2-licence.md).
