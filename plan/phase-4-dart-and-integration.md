# Phase 4 — Dart client and CGMS integration

**Weeks 14–16 · ~42 hours · ~90 commits**

> Port core to Dart; same conformance vectors, same results. SQLite local store.
> Wire into the Flutter app and the FastAPI adapter. Switch from path dependencies
> to pinned git tags. Tag `v0.1.0-rc`. — roadmap §8, Phase 4

**Exit criteria (roadmap):** two physical phones in airplane mode, concurrent edits
to one child's record, correct merge on reconnect, verified against every scenario in
the Phase 0 catalogue.

---

## What this phase is actually proving

Roadmap §5.1 chose two implementations against one spec over a Rust core with FFI,
and the stated payoff was: *"It yields an interoperability story rather than a
'trust me, it's the same code' story."*

**This is the phase where that payoff is either collected or lost.** If the Dart port
is written by reading the Python source line by line, it is a transliteration, and a
shared misunderstanding of the spec will be reproduced faithfully in both. The
conformance vectors are the only thing standing between "two implementations" and
"one implementation typed twice."

**Working rule for this phase:** implement each Dart component from
`spec/merge-semantics.md` and its conformance vectors, and consult the Python source
only when a vector fails and the spec is genuinely ambiguous. **When that happens, the
spec is what gets fixed** — an ambiguity found this way is a real defect in the
specification, and it is the most valuable thing this phase produces after the
working client.

Log each one in `plan/decision-log.md`. A list of "places the spec was ambiguous
enough that two implementations diverged" is a genuinely strong artifact.

---

## Work items

### WI-4.0 — Dart package scaffold

**Touches** `dhara-dart/pubspec.yaml`, `dhara-dart/lib/dhara.dart`,
`.github/workflows/dart.yml`

**Commit ladder**
1. `build(dart): add pubspec with package metadata and dart 3 constraint`
2. `build(dart): add dev dependencies - test, lints, coverage`
3. `build(dart): configure analysis options with strict lint rules`
4. `feat(dart): add the empty public surface in dhara.dart`
5. `test(dart): add an import smoke test`
6. `ci: add the dart workflow running analyze, format check and test`
7. `ci: enable the dart leg of the conformance workflow`

Rung 7 flips the `SKIPPED (dart-not-yet-implemented)` line from
`ci-and-tooling.md` §2 into a real gate. From this commit onward, **divergence is a
build failure.**

---

### WI-4.1 — Conformance runner in Dart `[gate]`

**Why** Build the checker before the thing being checked. Every subsequent WI in
this phase is then test-first for free.

**Touches** `dhara-dart/test/conformance_test.dart`

**Done when** The runner loads every vector in `spec/conformance/` and reports each
as a distinct failing test.

**Commit ladder**
1. `feat(conformance): load vectors from the shared spec directory in dart`
2. `feat(conformance): validate vectors against the shared JSON Schema`
3. `feat(conformance): build replica states from a vector in dart`
4. `feat(conformance): apply joins in every permutation of replica order`
5. `feat(conformance): compare results using the canonical form`
6. `feat(conformance): assert expected review signals in dart`
7. `test(conformance): all vectors currently fail with a clear reason`
8. `feat(conformance): report field-wise diffs rather than blob mismatches`

⚠ Rung 4 must match Python exactly. If Python runs all n! orders and Dart runs one,
the two suites are not testing the same claim and the comparison is theatre.

---

### WI-4.2 — HLC in Dart

**Touches** `dhara-dart/lib/src/hlc.dart`

**Commit ladder**
1. `feat(hlc): add the immutable HLC value type in dart`
2. `feat(hlc): implement total ordering with the node id tiebreak`
3. `feat(hlc): implement the send path`
4. `feat(hlc): implement the receive path with all four branches`
5. `feat(hlc): inject physical time as a callable`
6. `test(hlc): all hlc conformance vectors pass`
7. `test(hlc): property - monotonicity under a backwards-moving clock`
8. `feat(hlc): match the python fixed-width encoding exactly`
9. `test(hlc): encodings are byte-identical to the python fixtures`

⚠ Rung 8/9: Dart `int` is 64-bit on native but **53-bit-safe on web**. This project
targets Android only, so it is fine — but write the constraint down, because the
failure mode if someone later builds for web is silent HLC corruption at large
physical-time values.

---

### WI-4.3 — Lattices in Dart

**Touches** `dhara-dart/lib/src/lattice/*.dart`

**Commit ladder**
1. `feat(lattice): add the Lattice interface with join, leq and codecs`
2. `feat(lattice): add reusable law checkers for dart property tests`
3. `feat(gset): implement the grow-only set`
4. `test(gset): laws hold over 10k randomised orders`
5. `feat(lww): implement the register with retained losers`
6. `test(lww): laws hold and no observed value is ever dropped`
7. `feat(series): implement the append-only measurement series`
8. `test(series): laws hold and join never removes an entry`
9. `feat(orset): implement the observed-remove set`
10. `test(orset): laws hold and concurrent add beats an unobserved remove`
11. `feat(status): implement the status lattice with a domain join`
12. `test(status): an invalid domain join is rejected at construction`
13. `feat(lattice): implement canonical serialisation matching python byte for byte`
14. `test(conformance): every merge vector passes in dart`

Rung 13 is where divergence hides. Dart's `double` formatting differs from Python's
`repr` for some values — `9.2` is not the same string in both languages in every
path. Canonical form must fix a numeric encoding explicitly rather than relying on
either language's default. Expect to spend a session here; it is not wasted.

---

### WI-4.4 — Schema descriptor in Dart

**Touches** `dhara-dart/lib/src/schema.dart`

**Commit ladder**
1. `feat(schema): add Field and Schema descriptors in dart`
2. `feat(schema): validate declared status joins at construction`
3. `feat(schema): implement field-wise record join`
4. `test(schema): record join is field-wise and independent`
5. `feat(schema): implement the schema json codec`
6. `test(schema): a schema round-trips identically to the python codec`

---

### WI-4.5 — Local store on SQLite

**Why** The device needs durable state that survives the crash scenarios Phase 2
modelled.

**Touches** `dhara-dart/lib/src/store.dart`

**Commit ladder**
1. `feat(store): add the store interface - records, oplog, vectors, watermarks`
2. `feat(store): implement the sqlite schema with indexes on hlc and record id`
3. `feat(store): persist records with canonical serialisation`
4. `feat(store): persist the outbox of unsynced operations`
5. `feat(store): persist version vectors and per-lane ack watermarks`
6. `feat(store): make writes durable before returning to the caller`
7. `test(store): a simulated crash before commit loses only the uncommitted write`
8. `test(store): a simulated crash after commit recovers the write`
9. `feat(store): add the seen-set with the version vector as its frontier`
10. `test(store): the seen-set stays bounded across 5000 operations`
11. `perf(store): keep a full six-month backlog query under 100ms on a 2GB device`
12. `test(store): schema migration from an empty database is idempotent`

⚠ Rung 11 is the hardware constraint from roadmap §1 becoming a number. Anganwadi
workers in Maharashtra returned over 80,000 government-issued 2GB-RAM smartphones
because they could not run the app. **Measure this on the actual cheap device, not
the emulator on a laptop.** An emulator on an M-series Mac will report a number that
means nothing.

---

### WI-4.6 — Session protocol in Dart

**Touches** `dhara-dart/lib/src/session.dart`, `delta.dart`, `version_vector.dart`

**Commit ladder**
1. `feat(vv): implement version vectors in dart`
2. `test(vv): the compact encoding matches python byte for byte`
3. `feat(delta): implement delta_since for every lattice in dart`
4. `test(delta): joining a delta equals joining the full state`
5. `feat(session): implement the state machine and transition table`
6. `feat(session): implement chunk framing and checksums`
7. `feat(session): implement acked offsets and resumption`
8. `feat(session): persist the ack watermark before acknowledging`
9. `feat(session): implement priority lanes`
10. `feat(session): implement version negotiation`
11. `feat(session): implement retry with jittered backoff`
12. `test(conformance): every session transcript vector passes in dart`
13. `test(session): resumption after an interrupted transfer restarts at the watermark`

---

### WI-4.7 — FastAPI adapter (CGMS side)

**Why** The server end of the wire. Lives in the **CGMS** repo, not here — but the
work is planned here because it is on this phase's critical path.

**Touches** `cgms/backend/app/sync/routes.py`, `schema_binding.py`

**Commit ladder** *(these commits land in the CGMS repository)*
1. `feat(sync): add the schema binding mapping CGMS fields to lattice types`
2. `feat(sync): declare the enrolment status partial order`
3. `feat(sync): add sync routes delegating to dhara.session`
4. `feat(sync): authenticate and scope sessions to a tenant`
5. `feat(sync): persist replica state through the existing ORM`
6. `feat(sync): route review signals into the supervisor queue`
7. `test(sync): the adapter passes the session transcript vectors`
8. `docs(sync): record the dhara commit sha this adapter targets`

⚠ **This is the WI where the dependency rule is most at risk.** The schema binding
is the *only* place domain knowledge lives (roadmap §5.3). If something in `dhara`
needs to change to make this work, the correct move is to extend the **schema
descriptor**, not to add a domain concept to the engine. If a change to `dhara`
cannot be expressed without naming a domain concept, that is the signal to stop and
reconsider the design, not to make an exception.

---

### WI-4.8 — Flutter integration (CGMS side)

**Touches** `cgms/mobile/lib/data/sync/sync_service.dart`, `schema_binding.dart`

**Commit ladder** *(these commits land in the CGMS repository)*
1. `feat(sync): add the dart schema binding mirroring the server binding`
2. `test(sync): both bindings produce identical schema json`
3. `feat(sync): wire the local store into the app's data layer`
4. `feat(sync): trigger sync on a connectivity change`
5. `feat(sync): trigger sync on a background schedule`
6. `feat(sync): surface sync state in the UI without blocking data entry`
7. `feat(sync): render review signals for supervisor accounts`
8. `test(sync): data entry works with sync fully disabled`

⚠ Rung 8 is the most important test in this WI and the easiest to skip. **A worker
must be able to do her entire day's work with no network and no awareness that sync
exists.** If data entry ever blocks on a sync operation, the project has reproduced
the failure it was built to fix.

Rung 2 catches the drift that will otherwise happen: two schema bindings, edited at
different times, disagreeing about a field's lattice type. Compare their emitted
schema JSON in CI on both sides.

---

### WI-4.9 — Switch to pinned tags

**Why** Roadmap §4: path dependencies for weeks 1–13, pinned git tags from week 14.

**Commit ladder**
1. `chore: tag v0.1.0-rc with the frozen wire protocol`
2. `docs: add release notes for v0.1.0-rc`
3. `build(sync): pin the cgms backend to the dhara v0.1.0-rc tag` *(CGMS repo)*
4. `build(sync): pin the cgms mobile app to the dhara v0.1.0-rc tag` *(CGMS repo)*
5. `docs: document the tag-bump procedure and the migration-note requirement`
6. `ci: verify the pinned tag resolves in the cgms build` *(CGMS repo)*

---

### WI-4.10 — Two-phone field test `[gate]`

**Why** Direct exit criterion, and the first contact with reality.

**Setup:** two Android phones, ideally the actual 2GB-RAM hardware. Both in airplane
mode. Concurrent edits to one record. Reconnect. Verify against every catalogue
entry that two devices can produce.

**Commit ladder**
1. `docs: add the two-phone test protocol with a step per catalogue entry`
2. `docs: record two-phone results for the measurement scenarios C-01 to C-06`
3. `docs: record two-phone results for the demographic scenarios C-07 to C-12`
4. `docs: record two-phone results for the clock and session scenarios C-15 to C-17`
5. `docs: record two-phone results for the resumption scenarios C-21 to C-23`
6. `docs: record any scenario a two-phone test cannot reproduce, and why`
7. `fix: address each defect the two-phone test found` *(one commit per defect)*
8. `sim: add a regression scenario for every two-phone defect found`

⚠ Rung 8 is the discipline that keeps the simulator honest over time. **Every bug
found on a real phone that the simulator did not find is a gap in the simulator.**
Close it in the same session, or the harness slowly stops representing reality — and
the Phase 6 write-up loses the right to claim it does.

Set the expectation now: **the two-phone test will find something.** Real Android
introduces process death, doze, filesystem behaviour, and clock management that the
simulator does not model. Finding nothing would mean the test was too gentle.

---

### WI-4.11 — Phase 4 exit review `[gate]`

**Commit ladder**
1. `docs(plan): record phase 4 exit checklist results`
2. `docs: record every spec ambiguity the dart port exposed`
3. `docs: add changelog entry for the dart client and integration`
4. `chore: tag phase-4-complete`

Rung 2 is the interoperability story in concrete form. It is the answer to "how do
you know the two implementations agree?" that is better than "they pass the same
tests."

---

## Exit checklist

- [ ] **Two physical phones in airplane mode**, concurrent edits to one record,
      correct merge on reconnect.
- [ ] Verified against **every Phase 0 catalogue scenario** two devices can produce;
      scenarios that cannot be reproduced this way are listed with the reason.
- [ ] Every conformance vector passes in **both** Python and Dart, with all
      permutations of replica order in both.
- [ ] Canonical serialisation is byte-identical across the two languages, including
      numeric formatting.
- [ ] The conformance CI leg is a hard gate — no `SKIPPED`.
- [ ] SQLite store survives crash-before-commit and crash-after-commit.
- [ ] Six-month backlog query under 100 ms **on real 2GB hardware**, not an emulator.
- [ ] Data entry works with sync fully disabled.
- [ ] Both schema bindings emit identical schema JSON, checked in CI.
- [ ] CGMS pinned to `v0.1.0-rc`; tag-bump procedure documented.
- [ ] Every two-phone defect has a simulator regression scenario.
- [ ] Spec ambiguities exposed by the port are logged.
- [ ] `v0.1.0-rc` and `phase-4-complete` tags pushed.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| **Dart port is a transliteration** | Written with the Python file open beside it | Implement from the spec and vectors. Consult Python only on a failing vector, and fix the spec when you do. |
| Numeric formatting divergence | Vectors pass in one language, fail in the other, on float fields only | Fix a canonical numeric encoding in the spec. Do not special-case either language's default. |
| Domain knowledge leaks into `dhara` | The domain-token checker fails during WI-4.7 | Extend the schema descriptor instead. If that is impossible, stop and reconsider — this is the failure the repo split exists to prevent. |
| Performance collapses on real hardware | Store queries fine on emulator, seconds on device | Measure on the 2GB device from WI-4.5, not at the end of the phase. |
| Sync blocks data entry | Any UI path awaiting a sync future | WI-4.8 rung 8. This reproduces the failure the project exists to fix. |
| Two-phone test finds nothing | All green on the first attempt | The test is too gentle. Add process kills, longer offline periods, and manual clock changes. |
| Protocol churn breaks CGMS | Repeated tag bumps in one week | Post-freeze changes require the WI-3.14 process and a migration note. |
