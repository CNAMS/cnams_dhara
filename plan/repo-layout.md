# Repository layout

The target tree, and which phase creates each part. Nothing appears before its
phase — an empty directory committed in week 1 for a Phase 5 feature is a promise
you may not keep.

---

## 1. Target tree

```
dhara/
├── README.md                          # P0  opens with the problem, not the tech
├── EXECUTION.md                       # P0  this plan's index
├── LICENSE                            # P0
├── CHANGELOG.md                       # P1  keep-a-changelog, one entry per phase
├── dhara-sync-engine-roadmap.md       # P0  the design document
│
├── plan/                              # P0  execution plan (this directory)
│
├── spec/
│   ├── protocol-v0.1.md               # P0 draft → P3 frozen
│   ├── merge-semantics.md             # P0 skeleton → P1 complete
│   ├── conflict-catalogue.md          # P0  the ~20 real scenarios
│   ├── review-signals.md              # P1  what "unresolved" means on the wire
│   ├── identity-resolution.md         # P5  accept-then-reconcile design
│   ├── security-model.md              # P5  keys, enrolment, revocation, threat model
│   ├── versioning.md                  # P4  protocol version negotiation + migrations
│   └── conformance/
│       ├── schema.json                # P0  JSON Schema the vectors validate against
│       ├── hlc/*.json                 # P1  clock ordering vectors
│       ├── merge/*.json               # P1  (replica states) -> expected join
│       └── sessions/*.json            # P3  full sync transcripts
│
├── dhara-py/
│   ├── pyproject.toml                 # P0
│   ├── dhara/
│   │   ├── __init__.py
│   │   ├── hlc.py                     # P1  hybrid logical clock
│   │   ├── lattice/
│   │   │   ├── base.py                # P1  Lattice protocol, join contract
│   │   │   ├── lww_register.py        # P1
│   │   │   ├── g_set.py               # P1
│   │   │   ├── or_set.py              # P1
│   │   │   ├── measurement_series.py  # P1
│   │   │   └── status.py              # P1  domain-supplied join function
│   │   ├── version_vector.py          # P3
│   │   ├── delta.py                   # P3  delta-state computation
│   │   ├── session.py                 # P3  resumable chunked sync session
│   │   ├── queue.py                   # P3  priority lanes
│   │   ├── schema.py                  # P1  descriptor API
│   │   ├── review.py                  # P1  unresolved-signal emission
│   │   ├── identity.py                # P5  tombstones + forwarding pointers
│   │   ├── crypto.py                  # P5  per-device keys, revocation
│   │   ├── metrics.py                 # P3  counters/timers, no I/O
│   │   └── conformance.py             # P1  runs the JSON vectors
│   ├── sim/
│   │   ├── network.py                 # P2  partition, loss, reorder, dup, bandwidth
│   │   ├── clock.py                   # P2  virtual time + per-device skew
│   │   ├── device.py                  # P2  virtual replica
│   │   ├── server.py                  # P2  virtual server replica
│   │   ├── scenario.py                # P2  seeded scenario generator
│   │   ├── invariants.py              # P2  convergence, no-loss, monotonicity
│   │   ├── runner.py                  # P2  seed sweep + shrinking + replay
│   │   └── faults.py                  # P2  crash injection, mutation harness
│   ├── tests/
│   │   ├── unit/                      # P1
│   │   ├── property/                  # P1  Hypothesis
│   │   ├── conformance/               # P1
│   │   └── sim/                       # P2
│   └── bench/                         # P3  bytes-per-record, drain-time harness
│
├── dhara-dart/
│   ├── pubspec.yaml                   # P4
│   ├── lib/
│   │   ├── dhara.dart                 # P4  public surface
│   │   └── src/
│   │       ├── hlc.dart               # P4
│   │       ├── lattice/*.dart         # P4
│   │       ├── version_vector.dart    # P4
│   │       ├── delta.dart             # P4
│   │       ├── session.dart           # P4
│   │       ├── schema.dart            # P4
│   │       ├── store.dart             # P4  SQLite → P5 SQLCipher
│   │       └── crypto.dart            # P5
│   └── test/
│       ├── conformance_test.dart      # P4  runs spec/conformance/**
│       └── property_test.dart         # P4
│
├── docs/
│   ├── architecture.md                # P3
│   ├── deliberate-bug-experiment.md   # P2  ⚠ the single most credible artifact
│   ├── simulation-report.md           # P2  updated each phase
│   ├── field-report.md                # P6
│   ├── honest-tradeoffs.md            # P6  what the simulator cannot model
│   └── adr/                           # P1+ architecture decision records
│
├── .github/workflows/
│   ├── py.yml                         # P0
│   ├── conformance.yml                # P1  both implementations, same vectors
│   ├── dart.yml                       # P4
│   └── sim-nightly.yml                # P2  long seed sweeps
│
└── scripts/
    ├── check_no_domain_imports.py     # P1  enforces the dependency rule
    └── replay_seed.sh                 # P2  one command from a failing seed to a trace
```

---

## 2. What lands when

| Phase | New top-level artifacts |
|---|---|
| **P0** | `LICENSE`, `spec/conflict-catalogue.md`, `spec/protocol-v0.1.md` (draft), `dhara-py/` scaffold, CI running an empty suite |
| **P1** | `dhara/hlc.py`, `dhara/lattice/*`, `dhara/schema.py`, `spec/merge-semantics.md`, first conformance vectors, `docs/adr/` |
| **P2** | `sim/*`, `docs/deliberate-bug-experiment.md`, nightly sweep workflow |
| **P3** | `version_vector.py`, `delta.py`, `session.py`, `queue.py`, `bench/`, `spec/conformance/sessions/`, frozen `protocol-v0.1.md` |
| **P4** | all of `dhara-dart/`, `spec/versioning.md`, tag `v0.1.0-rc` |
| **P5** | `identity.py`, `crypto.py`, SQLCipher store, `spec/security-model.md`, `spec/identity-resolution.md` |
| **P6** | `docs/field-report.md`, `docs/honest-tradeoffs.md`, tag `v0.1.0` |

---

## 3. The boundary that must not be crossed

```
cgms monorepo  ────depends on───▶  dhara
     (never the reverse)
```

Domain knowledge lives in exactly two files, and both are in the **CGMS** repo, not
this one:

```
cgms/backend/app/sync/schema_binding.py     # CGMS fields -> lattice types
cgms/mobile/lib/data/sync/schema_binding.dart
```

Enforcement, added in WI-1.0 and run in CI from that point:

- `scripts/check_no_domain_imports.py` fails the build if any file under `dhara-py/`
  or `dhara-dart/` contains the tokens `child`, `beneficiary`, `anganwadi`, `cgms`,
  `mother`, `immunis`, or `poshan` outside of `docs/` and comments explicitly marked
  `# origin-note:`.
- The word list lives in the script, not in a config file, so changing it requires a
  commit that says why.

⚠ **The trap this exists to catch:** you, at 2 AM during exams, writing
`from app.models import Child` inside a merge function because it is faster than
extending the schema descriptor. The merge logic then knows about children and is no
longer a sync engine — it is a feature of one backend (roadmap §4).

---

## 4. Naming

The roadmap flags `dhara` as a placeholder with one hard requirement: the name must
not contain "cgms" or "anganwadi", because generality is the entire pitch.

**Resolved:** the repository is `CNAMS/cnams_dhara`; the Python package and Dart
package are both `dhara`. The org prefix is a hosting artifact and does not appear
in any import path, module name, wire field, or spec document.

If the package is ever published, `dhara` on PyPI/pub.dev may be taken — fall back to
`dhara-sync`. Do not fall back to anything containing the domain.

---

## 5. Two-repo friction, and the mitigation

Two repos means version pinning, two CI configs, and friction when one logical change
spans both.

| Weeks | Mechanism |
|---|---|
| 1–13 | Local path dependencies. `pip install -e ../dhara/dhara-py`; `dhara: {path: ../../dhara/dhara-dart}` in `pubspec.yaml`. |
| 14+ | Pinned git tags. Every protocol change ships a migration note in `spec/versioning.md`. |

When a change spans both repos during weeks 1–13, land it in `dhara` first, then the
CGMS side, and put the `dhara` commit SHA in the CGMS commit body. That is the cheap
substitute for atomic cross-repo commits, and it is enough.
