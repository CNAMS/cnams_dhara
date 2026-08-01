# Dhara — An Offline-First Sync Engine for Last-Mile Field Data

**Design document and implementation roadmap**

Status: Draft v0.1
Owner: Pranav Shukla
Context: spun out of the CGMS (child growth monitoring) EPICS project, VIT Bhopal

> `dhara` is a placeholder name. Requirement: the name must not contain "cgms" or
> "anganwadi", because generality is the entire pitch. Alternatives: `sindhu`,
> `lastmile-sync`, `pravah`.

---

## 1. Problem statement

Anganwadi workers record child growth data — weight, height, MUAC, immunisation,
service delivery — on Android phones, in villages, on networks that appear for
ninety seconds at a time or not at all.

The government app for this, Poshan Tracker, allows offline entry for **up to three
days** before data must sync, and daily upload is **mandatory**: a worker whose
upload fails can be recorded as non-operational, which affects her efficiency
report. So the failure mode is not "data arrives late." The failure mode is that a
worker who did her job is marked as if she did not, because of infrastructure she
does not control.

The reported failures are constant and well documented: failed logins, blank
dashboards, "No Data Found" after a successful entry, sync stalls, app crashes.
Field interviews in tribal Andhra Pradesh found that digital systems intended to
modernise welfare delivery instead shift the cost, labour, and risk of poor
infrastructure onto the frontline workers. The hardware compounds it — Anganwadi
workers in Maharashtra returned over 80,000 government-issued 2GB-RAM smartphones
because they could not run the app.

### The engineering problem, stated precisely

> Build a data synchronisation layer for longitudinal child health records that is
> correct under arbitrary offline duration, arbitrary clock skew, hostile networks,
> shared devices, and 2GB-RAM hardware — and that can prove it is correct.

Three properties matter more than anything else:

1. **No silent data loss.** A measurement that a worker recorded must never
   disappear because of a merge.
2. **Convergence.** Any two replicas that have seen the same set of operations,
   in any order, must reach the same state.
3. **Bounded bandwidth.** A sync must make forward progress inside a 90-second,
   20 kbps window and resume from where it stopped.

---

## 2. Non-goals

Scope discipline is the difference between a shipped v0.1 with field data and a
fourth 70%-complete repository. Explicitly out of scope:

| Not doing | Why |
|---|---|
| General-purpose PowerSync/ElectricSQL alternative | Solved by well-funded teams. Competing is a losing framing. |
| Arbitrary user-defined schemas | Fixed catalogue of lattice types only. Generality here buys nothing and costs months. |
| Text CRDTs / collaborative editing | Nobody co-edits prose in an Anganwadi centre. Yjs and Automerge own this. |
| Peer-to-peer device↔device sync | Star topology (devices ↔ server) covers the real workflow. P2P triples the state space. |
| Real-time / live subscriptions | The premise is that there is no network. |
| Building the CGMS app itself | CGMS is the demo, not the deliverable. |

---

## 3. Prior art, and what is actually mine to build

By 2026 the local-first ecosystem is mature. Automerge 3.0, Yjs, cr-sqlite,
PowerSync, ElectricSQL, Zero, RxDB, and WatermelonDB are all production-ready.
PowerSync watches the backend change stream, filters through sync rules, and
pushes to clients running local SQLite. ElectricSQL pivoted away from its original
CRDT design toward a simpler sync-engine model.

**Do not pitch this as "I built a sync engine."** That reads as naive to anyone who
knows the space.

The real gap is downstream of those tools:

- **ElectricSQL defaults to last-write-wins.** PowerSync makes conflict resolution
  your server API's problem. Both hand you the hard question and walk away.
- All of them assume broadband-ish reconnection windows, single-user devices, and
  a developer who will write domain-correct merge logic. In this deployment,
  none of those hold.
- Nobody has written that resolution layer for longitudinal child health records
  under Indian last-mile constraints, nor tested one to the standard below.

**The honest positioning line:**

> "I built the conflict-resolution layer that generic sync engines leave to you,
> for longitudinal child health records, and verified it with deterministic
> simulation testing."

That is a claim that survives questioning.

---

## 4. Repository decision

### Verdict: separate repository, not part of `cgms_backend`

**The test:** can the artifact be described without mentioning CGMS? Yes. Therefore
coupling it to the backend costs the property that makes it interesting.

**The engineering reason (stronger than the positioning reason):** the moment sync
code sits next to the SQLAlchemy models, somebody — you, at 2 AM, during exams —
will write `from app.models import Child` inside a merge function. The merge logic
then knows about children and is no longer a sync engine. It is a feature of one
backend. A repository boundary enforces a discipline that a folder boundary will
not.

### Dependency rule

```
cgms monorepo  ────depends on───▶  dhara
     (never the reverse)
```

`dhara` receives a **schema descriptor** at runtime. It never imports a domain
model, never knows what a child is, never has a table name hardcoded.

### Where to host

| Option | When |
|---|---|
| `PranavShukla2/dhara` (personal) | **Default.** Sole author; reads unambiguously as individual work in outreach. |
| `cgms-anganwadi/dhara` (org) | Only if EPICS teammates will genuinely co-author. |

Org-hosted repos invite "which parts were yours?" in an interview. Personal-account
hosting avoids that conversation entirely.

### Cost of the split, and mitigation

Two repos means version pinning, two CI configs, and friction when one logical
change spans both.

- **Weeks 1–13:** local path dependencies.
  `pip install -e ../dhara/dhara-py`, and in `pubspec.yaml`:
  ```yaml
  dependencies:
    dhara:
      path: ../../dhara/dhara-dart
  ```
- **Week 14 onward:** pin to git tags once the wire protocol stabilises.

---

## 5. Architecture

### 5.1 Language decision

A single Rust core with FFI bindings to Dart and Python is the maximalist path. It
is also the entire timeline, and FFI debugging on Android will eat weeks.

**Chosen path: two implementations against one spec, validated by shared
conformance vectors.**

- **Python** — server-side implementation plus the simulator.
- **Dart** — client-side implementation inside the Flutter app.
- **`spec/conformance/`** — language-agnostic JSON fixtures both must pass.

This is how real protocol implementations are verified. It yields an
interoperability story rather than a "trust me, it's the same code" story. A Rust
core is a legitimate v0.2 upgrade if systems credibility becomes the goal.

### 5.2 Repository layout

```
dhara/
├── README.md                      # opens with the problem, not the tech
├── spec/
│   ├── protocol-v0.1.md           # wire format, session state machine
│   ├── merge-semantics.md         # field kind -> lattice type, with rationale
│   ├── conflict-catalogue.md      # the ~20 real scenarios + desired outcomes
│   └── conformance/
│       ├── hlc/*.json             # clock ordering vectors
│       ├── merge/*.json           # (replica states) -> expected join
│       └── sessions/*.json        # full sync transcripts
├── dhara-py/
│   ├── dhara/
│   │   ├── hlc.py                 # hybrid logical clock
│   │   ├── lattice/
│   │   │   ├── lww_register.py
│   │   │   ├── g_set.py
│   │   │   ├── or_set.py
│   │   │   ├── measurement_series.py
│   │   │   └── status.py          # domain-supplied join function
│   │   ├── version_vector.py
│   │   ├── delta.py               # delta-state computation
│   │   ├── session.py             # resumable chunked sync session
│   │   ├── schema.py              # descriptor API
│   │   └── conformance.py         # runs the JSON vectors
│   ├── sim/
│   │   ├── network.py             # partition, loss, reorder, dup, bandwidth cap
│   │   ├── clock.py               # virtual time + per-device skew
│   │   ├── scenario.py            # seeded scenario generator
│   │   └── invariants.py          # convergence, no-loss, monotonicity
│   └── tests/
├── dhara-dart/
│   ├── lib/src/{hlc,lattice,session,store}.dart
│   └── test/conformance_test.dart
└── docs/
```

### 5.3 Monorepo touchpoints (thin)

```
cgms/
├── backend/app/sync/
│   ├── schema_binding.py          # CGMS fields -> lattice types
│   ├── routes.py                  # auth, tenancy, delegates to dhara.session
│   └── review_queue.py            # unresolvable merges -> supervisor
└── mobile/lib/data/sync/
    ├── schema_binding.dart
    └── sync_service.dart
```

The two `schema_binding` files are the **only** place domain knowledge lives.

### 5.4 Schema descriptor API (sketch)

```python
from dhara.schema import Schema, Field
from dhara.lattice import LWWRegister, MeasurementSeries, StatusLattice, ORSet

def enrolment_join(a: str, b: str) -> str:
    """Domain rule, not a timestamp comparison.
    Graduated is terminal; re-enrolment must be an explicit new record."""
    order = {"prospective": 0, "enrolled": 1, "transferred": 2, "graduated": 3}
    return a if order[a] >= order[b] else b

BENEFICIARY = Schema(
    name="beneficiary",
    fields=[
        Field("display_name",   LWWRegister,        keep_losers=True),
        Field("guardian_phone", LWWRegister,        keep_losers=True),
        Field("weight_kg",      MeasurementSeries,  dedup_on=("taken_at", "recorded_by", "value")),
        Field("height_cm",      MeasurementSeries,  dedup_on=("taken_at", "recorded_by", "value")),
        Field("muac_cm",        MeasurementSeries,  dedup_on=("taken_at", "recorded_by", "value")),
        Field("enrolment",      StatusLattice,      join=enrolment_join),
        Field("flags",          ORSet),
    ],
)
```

Note `keep_losers=True`. A last-write-wins register that *discards* the loser is
a data-loss bug wearing a design-decision costume. The loser goes into history and
is visible to a supervisor.

---

## 6. Technical core

### 6.1 Time without a trustworthy clock

Two devices, both offline for a week, both with wall clocks the worker set by hand.
Wall-clock timestamps are worthless for ordering.

**Hybrid logical clocks (HLC):** a Lamport counter fused with physical time.
Causal ordering survives clock skew; the value still sorts roughly chronologically
for human display.

```
send(event):
    pt = max(local_physical_time, last.pt)
    if pt == last.pt: c = last.c + 1
    else:             c = 0
    last = (pt, c)
    return (pt, c, device_id)

receive(remote):
    pt = max(local_physical_time, last.pt, remote.pt)
    if pt == last.pt == remote.pt: c = max(last.c, remote.c) + 1
    elif pt == last.pt:            c = last.c + 1
    elif pt == remote.pt:          c = remote.c + 1
    else:                          c = 0
    last = (pt, c)
```

Ties break on `device_id` so the total order is deterministic across replicas.

**Requirement:** ordering must remain correct under ±3 days of simulated skew.
This is where most homegrown sync layers quietly corrupt themselves.

### 6.2 Merge semantics

The conceptual centre of the project. **A child's weight is not a mutable field.**
It is an event that happened at a time. Two different weights recorded the same
morning is clinically meaningful information — bad scale, wrong child, transcription
error — that last-write-wins destroys.

| Field kind | Lattice | Merge rule |
|---|---|---|
| Measurements (weight, height, MUAC) | `MeasurementSeries` | Append-only set, deduplicated by `(taken_at, recorded_by, value)`. **Never overwrite.** |
| Demographics (name spelling, address) | `LWWRegister` | HLC-ordered winner; loser retained in history, never deleted. |
| Enrolment / service-delivery status | `StatusLattice` | Domain-supplied join over a defined partial order. Not a timestamp comparison. |
| Tag-like sets (risk flags, referrals) | `ORSet` | Observed-remove; concurrent add+remove resolves to add. |
| Genuinely ambiguous | — | **Surface to supervisor review queue.** |

That last row is a feature, not a cop-out. A sync engine that admits it does not
know is more trustworthy than one that silently guesses.

#### Worked example

```
Worker device (offline)              Supervisor device (offline)
  10:15  weight 9.2 kg                 11:40  weight 9.4 kg
  10:20  height 74 cm                  11:45  MUAC 12.1 cm

── both sync at 18:00 ──

LWW outcome (wrong):     9.4 kg wins the row; 9.2 kg is silently lost.
Series outcome (right):  both readings retained, ordered by causal clock,
                         and flagged for review because two weights for one
                         child on one day is clinically suspicious.
```

### 6.3 Delta sync under a bandwidth budget

On 2G, the connection is a 90-second window at 20 kbps that dies mid-transfer.
"POST the whole changeset" is not an option.

- **Version vectors** per (replica, record) so the server can compute exactly what
  the client is missing.
- **Delta-state transmission** — send the delta, not the full state.
- **Chunked transfer with acknowledged offsets.** Resume from the last ack, never
  from zero.
- **Priority queues.** Growth data must never queue behind a photograph.
  Photos go to a separate low-priority queue with aggressive compression. A 400 KB
  image blocking 2 KB of growth data is the single most common real-world failure.
- **Idempotent application.** Every chunk carries an operation ID; replay is a no-op.

### 6.4 Offline identity resolution

The most interesting sub-problem. A worker registers a child in a hamlet with no
signal. Was that child already registered by the neighbouring centre last month?
You cannot query the server. Poshan Tracker leans on Aadhaar-based verification to
eliminate duplicates — which requires connectivity, and is exactly the part that
fails.

Two approaches, both real engineering:

**(a) Accept-then-reconcile.** Locally generated UUIDs. Duplicates are accepted,
detected server-side, and a merge decision is propagated back to devices. The hard
part: devices hold local references to the losing UUID and must not break when it
is superseded. Requires a tombstone-with-forwarding-pointer design.

**(b) Pre-pushed probabilistic filters.** A bloom filter over fuzzy hashes of
`(name, DOB, mother's name)` for the surrounding block, pushed to devices during
the last successful sync. Gives an offline "this may already exist" warning without
shipping a plaintext beneficiary list to every phone.

Recommended: implement (a) as the correctness backbone and (b) as a UX improvement
on top. (a) alone is sufficient for v0.1.

### 6.5 Security on shared and lost devices

Multiple workers on one phone. Phones that get returned, resold, or stolen.
Children's health data at rest.

- **SQLCipher** for the local store.
- **Per-device keys**, issued at enrolment, never derived from a user password.
- **Server-side revocation** that renders a lost device's data unreadable *without
  requiring that device to come back online*. This constraint rules out
  "send a wipe command" designs.
- **Per-worker sessions** on shared devices, with each operation attributed to the
  worker, not the device.

---

## 7. Correctness strategy

This is the part that makes the project stand out, and it directly addresses the
honest weakness of AI-assisted development: an LLM will happily write a sync layer
that looks correct and loses data under one specific interleaving.

### 7.1 Deterministic simulation testing

Run N virtual devices and a virtual server **inside a single process**, with a
seeded PRNG controlling everything non-deterministic:

- network partitions (duration, topology)
- packet loss, reordering, duplication
- per-device clock skew and clock jumps
- crashes mid-write and mid-sync
- bandwidth caps and abrupt window closure

Then assert invariants after every schedule:

```python
def check_invariants(replicas, server, oplog):
    assert all_converged(replicas + [server])
    assert no_measurement_lost(oplog, server.state)
    assert version_vectors_monotonic(oplog)
    assert no_duplicate_application(oplog)
```

Seed 4471 fails? Replay seed 4471 exactly and debug it. This is how FoundationDB
and TigerBeetle test their storage layers, and it is rare in student projects.

**Critical validation of the harness itself:** deliberately introduce a known-bad
merge — swap a series append for an overwrite — and confirm the simulator finds it
within 1,000 seeds. A harness that never fails is a harness that is not testing
anything. Document this experiment; it is the single most credible artifact in the
repo.

### 7.2 Property-based tests

For every lattice type, assert the algebraic laws with Hypothesis (Python) and
`fast_check`-style generators (Dart):

- **Commutativity:** `join(a, b) == join(b, a)`
- **Associativity:** `join(join(a, b), c) == join(a, join(b, c))`
- **Idempotence:** `join(a, a) == a`

Target: 10,000 randomised operation orders per type, green.

### 7.3 Conformance vectors

```json
{
  "name": "concurrent_weight_same_morning",
  "schema": "beneficiary",
  "replicas": {
    "A": { "weight_kg": [{"value": 9.2, "taken_at": "T10:15", "by": "w1", "hlc": [.., ..]}] },
    "B": { "weight_kg": [{"value": 9.4, "taken_at": "T11:40", "by": "s1", "hlc": [.., ..]}] }
  },
  "expected": {
    "weight_kg": [ {"value": 9.2, "..": ".."}, {"value": 9.4, "..": ".."} ],
    "review_flags": ["multiple_weights_same_day"]
  }
}
```

Both the Python and Dart implementations run the same file. Divergence is a build
failure.

---

## 8. Roadmap

Assumes ~12–15 hours/week alongside coursework. 24 weeks.

### Phase 0 — Conflict catalogue and spec (weeks 1–2)

Before any code, enumerate every concurrent-edit scenario in the real CGMS schema
and write down the correct outcome for each. Target: **20 scenarios minimum.**

Starter list:
1. Two workers weigh the same child within an hour.
2. Supervisor corrects a name while the worker edits the address.
3. Child marked graduated on one device, re-enrolled on another.
4. Record deleted on one device, updated on another.
5. Same child registered independently at two centres.
6. A measurement is entered, then corrected, then the correction is corrected.
7. Device clock is 3 days behind; its edits must not all lose.
8. Photo uploaded from device A, metadata edited on device B.
9. Worker's session expires mid-sync; another worker logs in on the same phone.
10. Server-side bulk correction lands while a device is offline.

**Deliverables:** `conflict-catalogue.md`, `protocol-v0.1.md` draft, repo scaffold,
CI running an empty test suite.

**Exit criteria:** for every scenario you can state the desired merged state without
hand-waving. This document becomes the conformance vectors in Phase 1.

### Phase 1 — Clocks and lattices (weeks 3–5)

HLC, then the five lattice types, then the first conformance vectors.

**Exit criteria:** property tests green over 10,000 randomised operation orders per
lattice. HLC ordering correct under ±3 days of simulated skew. `merge-semantics.md`
written with rationale for each choice, not just the choice.

### Phase 2 — The simulator (weeks 6–9)

**Build this before the network layer.** It will shape the design of everything
after it.

**Exit criteria:**
- 1,000,000 randomised schedules converge with no measurement loss.
- The deliberate-bug experiment (§7.1) finds the injected fault within 1,000 seeds,
  and the experiment is written up.

### Phase 3 — Delta sync and session protocol (weeks 10–13)

Version vectors, delta computation, chunked resumable transfer, priority queues,
idempotent application.

**Exit criteria:** in simulation, a device carrying **six months** of accumulated
offline data fully converges across a sequence of 90-second / 20 kbps windows with
random disconnection — zero duplication, zero loss, bounded retransmission. Record
bytes-per-record as a headline metric.

### Phase 4 — Dart client and CGMS integration (weeks 14–16)

Port core to Dart; same conformance vectors, same results. SQLite local store.
Wire into the Flutter app and the FastAPI adapter. Switch from path dependencies to
pinned git tags. Tag `v0.1.0-rc`.

**Exit criteria:** two physical phones in airplane mode, concurrent edits to one
child's record, correct merge on reconnect, verified against every scenario in the
Phase 0 catalogue.

### Phase 5 — Security and identity (weeks 17–20)

SQLCipher, per-device keys, enrolment and revocation. Accept-then-reconcile
duplicate detection. Supervisor review queue.

**Exit criteria:**
- A revoked device's local store is unreadable without that device coming online.
- A duplicate registration created at two centres is detected and reconciled, and
  both devices update local references without breaking.

### Phase 6 — Field deployment and write-up (weeks 21–24)

Two or three real Anganwadi centres. Instrument everything.

**Exit criteria:** real numbers from real devices on real networks; tagged
`v0.1.0`; published protocol spec; blog post.

---

## 9. Metrics to instrument

Collect from week 21 onward. These are what make the write-up credible.

| Metric | Why it matters |
|---|---|
| Sync success rate (attempts → convergence) | The headline number. Compare against baseline. |
| Median / p95 bytes per synced record | Proves the delta design earned its complexity. |
| Time-to-converge after N days offline | The three-day limit is the thing being beaten. |
| Windows required to drain a backlog | Directly measures resumability. |
| Review-queue volume per 100 records | Too high = merge rules too timid. Too low = suspicious. |
| Battery cost per sync session | Field workers will not adopt something that kills the phone. |
| Crash-free session rate on 2GB devices | The hardware constraint is real. |

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| No field deployment access | **High** — without it this is a well-tested library with no evidence it survives reality | Start the EPICS/ICDS conversation in week 1, not week 20. Fallback: instrument a controlled trial with 5 phones and real workers for one week. |
| Scope creep into building the whole app | High | Non-goals list in §2 is binding. CGMS is the demo. |
| Rust rewrite temptation | Medium | Defer to v0.2. Two implementations + conformance vectors is already a strong story. |
| Simulator becomes a project of its own | Medium | Timebox Phase 2 to 4 weeks. It only needs to inject the six fault classes listed. |
| Protocol churn breaks CGMS repeatedly | Medium | Path dependencies until week 14, then pinned tags and a documented migration note per version. |
| Exams / semester load | High | Phases 0–2 are the irreducible core. Phases 5–6 can slip a semester without invalidating the work. |

---

## 11. How to talk about it

**Do not say:** "I built a sync engine."

**Do say:** "Generic sync engines default to last-write-wins or hand conflict
resolution to your API. That is wrong for longitudinal health records — a child's
weight is an event, not a mutable field. I built the resolution layer for that
domain and verified it with deterministic simulation testing: a million randomised
schedules of partitions, clock skew, and mid-write crashes, all asserting
convergence and no measurement loss."

Then the honest-tradeoffs section, which is the strongest credibility asset:

- What the simulator cannot model (real radio behaviour, Android doze, OEM
  battery killers, filesystem corruption on cheap flash).
- Where a Rust core would be genuinely better and why it was not attempted.
- Scenarios where the engine still declines to decide, and why that is correct.
- The gap between simulated bandwidth caps and actual 2G behaviour.

---

## 12. Open questions

- [ ] Does the review queue belong in `dhara` (as a first-class "unresolved" state)
      or entirely in the consumer application? Leaning: `dhara` emits the signal,
      the consumer owns the UI.
- [ ] Tombstone retention policy — how long before a deleted record's tombstone can
      be garbage-collected without risking resurrection from a device that has been
      offline for six months?
- [ ] Does the server need to be a full replica, or can it be an authority that
      applies the same joins? Leaning: full replica, simpler to reason about.
- [ ] Photo handling: separate content-addressed blob store, or in-band chunks?
- [ ] Is an Aadhaar-adjacent identity path required for real ICDS deployment, and
      does that constrain the dedup design?

---

## 13. References

- Kleppmann et al., *Local-First Software: You Own Your Data, in Spite of the Cloud*
  (Ink & Switch, 2019)
- Shapiro et al., *Conflict-Free Replicated Data Types* (INRIA, 2011)
- Almeida, Shoker, Baquero, *Delta State Replicated Data Types*
- Kulkarni et al., *Logical Physical Clocks and Consistent Snapshots* (HLC paper)
- FoundationDB — deterministic simulation testing talks
- TigerBeetle — simulation testing and VOPR writeups
- PowerSync / ElectricSQL architecture documentation (for the boundary of prior art)
- Ministry of Women and Child Development — Poshan Tracker programme documentation
