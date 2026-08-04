# Tracking board

Live state of every work item. **105 work items across 7 phases.**

Tick a box when the WI's "Done when" condition is met — not when the code is written.
Update this file in the same commit as the last rung of the ladder.

Markers: `[gate]` phase exit depends on it · `[stretch]` cut first when slipping ·
`[spec]` produces a spec document · `[research]` written artifact, not code

---

## Progress

| Phase | Weeks | Items | Done | Status |
|---|---|---|---|---|
| 0 — Conflict catalogue and spec | 1–2 | 15 | 13 | **exit blocked** — WI-0.0 and WI-0.14 |
| 1 — Clocks and lattices | 3–5 | 18 | 18 | **criteria met, tag withheld** — see [exit review](../docs/phase-1-exit.md) |
| 2 — The simulator | 6–9 | 22 | 19 | in progress — million-schedule gate outstanding |
| 3 — Delta sync and session protocol | 10–13 | 16 | 0 | not started |
| 4 — Dart client and CGMS integration | 14–16 | 12 | 0 | not started |
| 5 — Security and identity | 17–20 | 11 | 0 | not started |
| 6 — Field deployment and write-up | 21–24 | 11 | 0 | not started |
| **Total** | **24** | **105** | **50** | |

---

## Phase 0 — Conflict catalogue and spec `weeks 1–2`

- [ ] **WI-0.0** Open the field-access conversation `[gate]` `[research]` ⚠ **BLOCKING — not started, see [DOUBTS.md D-12](../DOUBTS.md#d-12)**
- [x] **WI-0.1** Repository scaffold and licence
- [x] **WI-0.2** Python package scaffold
- [x] **WI-0.3** CI running an empty suite
- [x] **WI-0.4** Catalogue format and entry template `[spec]`
- [x] **WI-0.5** Catalogue entries: measurements (C-01…C-06) `[spec]` `[gate]`
- [x] **WI-0.6** Catalogue entries: demographics and status (C-07…C-12) `[spec]` `[gate]`
- [x] **WI-0.7** Catalogue entries: identity, sessions, clocks (C-13…C-20) `[spec]` `[gate]`
- [x] **WI-0.8** Catalogue entries: adversarial and operational (C-21…C-24) `[spec]`
- [x] **WI-0.9** Merge semantics skeleton `[spec]`
- [x] **WI-0.10** Protocol v0.1 draft `[spec]`
- [x] **WI-0.11** Conformance vector schema `[spec]`
- [x] **WI-0.12** Decision records and living documents
- [x] **WI-0.13** Pre-commit hooks
- [ ] **WI-0.14** Phase 0 exit review `[gate]` — blocked on WI-0.0 and unverified CI ([D-10](../DOUBTS.md#d-10))

**Exit gate:** ≥20 catalogue entries with field-by-field outcomes · CI green ·
protocol draft with every failure edge · [full checklist](phase-0-catalogue-and-spec.md#exit-checklist)

---

## Phase 1 — Clocks and lattices `weeks 3–5`

- [x] **WI-1.0** Enforce the dependency rule in CI `[gate]`
- [x] **WI-1.1** HLC type and ordering
- [x] **WI-1.2** HLC send path
- [x] **WI-1.3** HLC receive path
- [x] **WI-1.4** HLC under clock skew `[gate]`
- [x] **WI-1.5** HLC conformance vectors `[spec]`
- [x] **WI-1.6** Lattice base contract
- [x] **WI-1.7** GSet
- [x] **WI-1.8** LWWRegister with retained losers `[gate]`
- [x] **WI-1.9** ORSet
- [x] **WI-1.10** MeasurementSeries `[gate]`
- [x] **WI-1.11** StatusLattice
- [x] **WI-1.12** Schema descriptor API
- [x] **WI-1.13** Review signal emission
- [x] **WI-1.14** Conformance runner
- [x] **WI-1.15** Merge vectors from the catalogue `[spec]` `[gate]`
- [x] **WI-1.16** Complete merge-semantics.md `[spec]` `[gate]`
- [x] **WI-1.17** Phase 1 exit review `[gate]`

**Exit gate:** laws green over 10,000 orders per lattice · HLC correct under ±3 days
skew · rationale written, not just the choice ·
[full checklist](phase-1-clocks-and-lattices.md#exit-checklist)

---

## Phase 2 — The simulator `weeks 6–9`

- [x] **WI-2.0** Simulator architecture decision `[research]`
- [x] **WI-2.1** Determinism harness `[gate]`
- [x] **WI-2.2** Virtual clock with skew
- [x] **WI-2.3** Virtual network: delivery
- [x] **WI-2.4** Fault: partitions
- [x] **WI-2.5** Fault: loss, reordering, duplication
- [x] **WI-2.6** Fault: bandwidth caps and window closure
- [x] **WI-2.7** Virtual device replica
- [x] **WI-2.8** Virtual server replica
- [x] **WI-2.9** Scenario generator
- [x] **WI-2.10** Invariant: convergence `[gate]`
- [x] **WI-2.11** Invariant: no measurement lost `[gate]`
- [x] **WI-2.12** Invariants: monotonicity and idempotence
- [x] **WI-2.13** Crash injection
- [x] **WI-2.14** Seed sweep runner
- [ ] **WI-2.15** Shrinking — implemented, never exercised on a real failure
- [x] **WI-2.16** Replay and tracing
- [x] **WI-2.17** The deliberate-bug experiment `[gate]` ⚠ the phase's whole point
- [x] **WI-2.18** Nightly CI and the regression corpus
- [ ] **WI-2.19** The million-schedule sweep `[gate]` — **5,000 run; ~11.5h single-core for the gate**
- [x] **WI-2.20** Simulation report
- [ ] **WI-2.21** Phase 2 exit review `[gate]`

**Exit gate:** 1,000,000 schedules green · all six mutations caught within 1,000
seeds · the experiment written up including what the harness *cannot* catch ·
[full checklist](phase-2-simulator.md#exit-checklist)

⏱ **Timebox: 4 weeks.** Six fault classes, four invariants, one runner. Nothing else.

---

## Phase 3 — Delta sync and session protocol `weeks 10–13`

- [ ] **WI-3.0** Version vectors
- [ ] **WI-3.1** Delta-state computation `[gate]`
- [ ] **WI-3.2** Operation identity and idempotence
- [ ] **WI-3.3** Chunk framing
- [ ] **WI-3.4** Acknowledged offsets and resumption `[gate]`
- [ ] **WI-3.5** Session state machine
- [ ] **WI-3.6** Version negotiation
- [ ] **WI-3.7** Priority lanes `[gate]`
- [ ] **WI-3.8** Photo handling
- [ ] **WI-3.9** Backpressure and retry
- [ ] **WI-3.10** Session conformance vectors `[spec]`
- [ ] **WI-3.11** Simulator integration
- [ ] **WI-3.12** Metrics instrumentation
- [ ] **WI-3.13** The six-month backlog scenario `[gate]`
- [ ] **WI-3.14** Freeze protocol v0.1 `[spec]` `[gate]`
- [ ] **WI-3.15** Phase 3 exit review `[gate]`

**Exit gate:** six months of backlog drains over 90s/20kbps windows · zero
duplication, zero loss, bounded retransmission · bytes-per-record recorded against a
full-state baseline · [full checklist](phase-3-delta-sync.md#exit-checklist)

---

## Phase 4 — Dart client and CGMS integration `weeks 14–16`

- [ ] **WI-4.0** Dart package scaffold
- [ ] **WI-4.1** Conformance runner in Dart `[gate]`
- [ ] **WI-4.2** HLC in Dart
- [ ] **WI-4.3** Lattices in Dart
- [ ] **WI-4.4** Schema descriptor in Dart
- [ ] **WI-4.5** Local store on SQLite
- [ ] **WI-4.6** Session protocol in Dart
- [ ] **WI-4.7** FastAPI adapter *(CGMS repo)*
- [ ] **WI-4.8** Flutter integration *(CGMS repo)*
- [ ] **WI-4.9** Switch to pinned tags
- [ ] **WI-4.10** Two-phone field test `[gate]`
- [ ] **WI-4.11** Phase 4 exit review `[gate]`

**Exit gate:** two physical phones in airplane mode, correct merge on reconnect,
verified against every catalogue scenario · conformance green in both languages ·
`v0.1.0-rc` tagged · [full checklist](phase-4-dart-and-integration.md#exit-checklist)

---

## Phase 5 — Security and identity `weeks 17–20`

- [ ] **WI-5.0** Threat model `[spec]` `[research]`
- [ ] **WI-5.1** Per-device keys and enrolment
- [ ] **WI-5.2** SQLCipher at rest `[gate]`
- [ ] **WI-5.3** Revocation without device cooperation `[gate]`
- [ ] **WI-5.4** Per-worker sessions on shared devices
- [ ] **WI-5.5** Tombstones with forwarding pointers `[gate]`
- [ ] **WI-5.6** Duplicate detection: accept-then-reconcile `[gate]`
- [ ] **WI-5.7** Review queue integration
- [ ] **WI-5.8** Bloom filter pre-push `[stretch]`
- [ ] **WI-5.9** Key rotation `[stretch]`
- [ ] **WI-5.10** Security review and phase exit `[gate]`

**Exit gate:** a revoked device's store unreadable without it coming online · the
outbox survives read-key expiry · duplicate registration reconciled without breaking
local references · [full checklist](phase-5-security-and-identity.md#exit-checklist)

---

## Phase 6 — Field deployment and write-up `weeks 21–24`

- [ ] **WI-6.0** Telemetry that works offline `[gate]`
- [ ] **WI-6.1** Battery and device instrumentation
- [ ] **WI-6.2** Deployment preparation
- [ ] **WI-6.3** Deployment week 1
- [ ] **WI-6.4** Deployment weeks 2–3
- [ ] **WI-6.5** Metrics analysis `[gate]`
- [ ] **WI-6.6** Honest tradeoffs `[gate]`
- [ ] **WI-6.7** Publish the protocol spec `[gate]`
- [ ] **WI-6.8** Write-up `[gate]`
- [ ] **WI-6.9** Release `v0.1.0` `[gate]`
- [ ] **WI-6.10** v0.2 candidates `[research]`

**Exit gate:** real numbers from real devices on real networks, each with a
provenance tag · simulated-versus-measured comparison including where the simulation
was optimistic · `v0.1.0` tagged ·
[full checklist](phase-6-field-and-writeup.md#exit-checklist)

---

## Tags

- [ ] `phase-0-complete`
- [ ] `phase-1-complete` — criteria met; withheld until phase 0 exits and CI runs
- [ ] `phase-2-complete`
- [ ] `phase-3-complete`
- [ ] `v0.1.0-rc` — wire protocol frozen, CGMS switches to pinned tags
- [ ] `phase-4-complete`
- [ ] `phase-5-complete`
- [ ] `v0.1.0` — field data collected, spec published

---

## Standing items

Not phase-scoped. Check at every phase exit.

- [ ] Field-access conversation has a current status *(R1 — review weeks 6, 12, 18, 21)*
- [ ] Mutation detection times unchanged from the Phase 2 baseline *(R8)*
- [ ] Domain-token checker green *(R2)*
- [ ] Every simulator-found bug has a seed in the regression corpus
- [ ] Every field or two-phone defect has a simulator regression scenario
- [ ] Every number in every document carries a `[sim]` / `[lab]` / `[field]` tag *(R11)*
- [ ] No co-author or generated-by trailer anywhere in the history
