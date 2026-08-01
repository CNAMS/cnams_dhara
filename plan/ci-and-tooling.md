# CI and tooling

CI exists here for one reason: **to make divergence and regression impossible to
miss.** Two implementations against one spec is only a real claim if something
mechanical checks it on every push.

---

## 1. Local toolchain

| Tool | Version | Why this one |
|---|---|---|
| Python | 3.11+ | `Self` typing, `tomllib`, and exception groups for the invariant checker |
| uv | latest | Fast, lockfile-native. `pip` fallback documented in the README. |
| pytest | 8.x | |
| Hypothesis | 6.x | Property tests for the lattice laws (roadmap §7.2) |
| ruff | latest | Lint + format, one tool |
| mypy | strict | The lattice `join` contract is a typing problem; strict mode earns its keep |
| Dart SDK | 3.x | |
| `test` / `checks` | latest | Dart test runner + lints |
| SQLite | 3.4x | Local store, Phase 4 |
| SQLCipher | 4.x | Phase 5 |

Pinned in `pyproject.toml` and `pubspec.yaml`. A `.tool-versions` file at the root
keeps the two runtimes reproducible.

---

## 2. Pipelines

### `py.yml` — every push (Phase 0)

```
ruff check → ruff format --check → mypy --strict → pytest -q → coverage gate
```

- Matrix: Python 3.11, 3.12.
- Coverage gate: **90% on `dhara/`**, no gate on `sim/`.
  Rationale: a coverage number on a simulator measures how much of the simulator
  ran, which is not the property of interest. The property of interest for `sim/` is
  the deliberate-bug experiment.
- Runtime budget: **under 3 minutes.** If it exceeds that, the slow tests move to
  the nightly workflow. A CI you wait for is a CI you start skipping.

### `conformance.yml` — every push (Phase 1)

```
python conformance runner  ─┐
                            ├─▶ same spec/conformance/** tree ─▶ diff must be empty
dart conformance runner    ─┘
```

Runs both implementations against the identical vector tree and compares results
structurally, not textually. **Divergence is a build failure** (roadmap §7.3). From
Phase 4 this is the gate that keeps the two implementations honest; before Phase 4
the Dart leg is skipped with a visible `SKIPPED (dart-not-yet-implemented)` line
rather than silently absent.

### `sim-nightly.yml` — scheduled (Phase 2)

```
seed sweep (N=100_000, sharded 8×) → invariants → on failure: shrink + upload trace
```

- Fixed seed base per night derived from the date, so a night is reproducible.
- On failure the job uploads the seed, the scenario JSON, and the event trace as
  artifacts, and opens an issue titled `sim: invariant <name> violated at seed <n>`.
- **The failing seed goes into `tests/sim/regressions/` as a permanent fast test.**
  Every bug the simulator finds becomes a test that runs in under 3 minutes forever
  after. That corpus is the most valuable file in the repository by month four.

### `dart.yml` — every push (Phase 4)

```
dart analyze → dart format --set-exit-if-changed → dart test
```

### `check_no_domain_imports` — every push (Phase 1)

Runs as a step in `py.yml`. Enforces the dependency rule from
[repo-layout.md](repo-layout.md) §3.

---

## 3. Pre-commit

```yaml
# .pre-commit-config.yaml  (WI-0.7)
- ruff (fix + format)
- mypy on changed files
- check_no_domain_imports
- conventional-commit message check
- forbid co-author / generated-by trailers
```

The last hook is not decoration. It is the mechanical version of the authorship rule
in [commit-conventions.md](commit-conventions.md) §6, and it is cheaper than a
history rewrite later.

Pre-commit must stay **under 5 seconds.** Anything slower gets skipped with `-n`,
and a hook that is routinely skipped is worse than no hook because it creates false
confidence.

---

## 4. The seed corpus

Three tiers, and the distinction matters:

| Tier | Where | Size | When it runs |
|---|---|---|---|
| **Regression seeds** | `tests/sim/regressions/seeds.txt` | grows by one per bug found | every push |
| **Smoke sweep** | `runner.py --seeds 2000` | fixed | every push, ~60s |
| **Full sweep** | `runner.py --seeds 100000` | fixed base per night | nightly |
| **Milestone sweep** | `runner.py --seeds 1000000` | phase exit only | Phase 2 and Phase 3 gates |

The 1,000,000-schedule figure in the roadmap's Phase 2 exit criteria is a **gate
measurement**, not a per-push cost. Running it on every push would make the loop
unusable and would not find anything the nightly sweep misses within a week.

---

## 5. Reproducibility rules

These are what make "replay seed 4471 exactly" true rather than aspirational.

1. **One PRNG, threaded explicitly.** No module-level `random`, no `time.time()`, no
   `uuid4()` anywhere reachable from a simulation. `sim/` passes a `Random` instance
   down; `dhara/` takes clock and ID generation as injected dependencies.
   Enforced by a lint rule added in WI-2.1.
2. **No wall-clock reads inside `dhara/`.** The HLC takes a `physical_time()`
   callable. In production it is `time.time`; in simulation it is the virtual clock.
   This is not testing sugar — it is the only way clock-skew scenarios are
   expressible at all.
3. **No set/dict iteration order dependence.** Merge results are compared
   structurally after canonical sorting. A `join` whose output depends on iteration
   order is a convergence bug, and CI runs with `PYTHONHASHSEED` randomised on one
   matrix leg specifically to surface it.
4. **Trace on demand, not by default.** `--trace` writes a JSONL event log. Off in
   sweeps (it dominates runtime), on in replay.

---

## 6. Versioning

- **Library version:** SemVer, but pre-1.0, so the wire protocol version is tracked
  separately and is the one that actually matters to the CGMS app.
- **Wire protocol version:** integer, in the session handshake, bumped on any
  incompatible change. `spec/versioning.md` (Phase 4) records what changed and the
  migration path for devices that have been offline across the bump.
- **⚠ The hard case:** a device offline for six months reconnects speaking protocol
  v1 to a v3 server. The server must either serve v1 or refuse in a way the client
  handles without losing its outbox. Designed in WI-4.10, and it is the reason
  protocol version negotiation is not deferred to "later".

---

## 7. What is deliberately not automated

| Not automated | Why |
|---|---|
| Release publishing to PyPI / pub.dev | No external consumers. Git tags are enough until there are. |
| Auto-merge / dependabot auto-updates | A dependency bump that changes float formatting is a conformance failure you want to read, not merge. |
| Coverage on `sim/` | Measures the wrong thing (see §2). |
| Benchmarks in the push pipeline | Shared runners are too noisy for bytes-per-record numbers. Benchmarks run locally on a fixed machine and the number goes in the commit body. |
