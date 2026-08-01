# Phase 0 — Conflict catalogue and spec

**Weeks 1–2 · ~28 hours · ~60 commits**

> Before any code, enumerate every concurrent-edit scenario in the real CGMS schema
> and write down the correct outcome for each. Target: 20 scenarios minimum.
> — roadmap §8, Phase 0

**Exit criteria (roadmap):** for every scenario you can state the desired merged
state without hand-waving. This document becomes the conformance vectors in Phase 1.

---

## Why this phase is first, and why it is not "just documentation"

The catalogue is the specification of correctness. Every later phase is downstream
of it:

```
conflict-catalogue.md ──▶ conformance vectors ──▶ Python impl ──▶ Dart impl
        │                        │
        └────────────────────────┴──▶ simulator invariants
```

If a scenario is missing here, the simulator will never generate it, no vector will
cover it, and both implementations will be confidently wrong about it in the same
way. **Two implementations that agree on a scenario neither has considered is not
interoperability, it is a shared blind spot.**

The temptation in week 1 is to start writing `hlc.py` because it is more fun. Don't.
The HLC takes four hours in Phase 1 and is the least uncertain part of the project.

---

## Work items

### WI-0.0 — Open the field-access conversation `[gate]` `[research]`

**Why** Roadmap §10 rates "no field deployment access" as the highest-severity risk:
*"without it this is a well-tested library with no evidence it survives reality."*
Access has a lead time measured in weeks and is not under your control. Starting it
in week 20 is how the project ends up with a simulator and no field data.

**Touches** `plan/risk-register.md`, `plan/decision-log.md`

**Done when** A written request has been sent to the EPICS coordinator and the ICDS
contact, and the fallback (controlled trial, 5 phones, one week, real workers) has a
named person who could arrange it.

**Commit ladder**
1. `docs(plan): record field-access request as the week-1 blocking action`
2. `docs(plan): add fallback controlled-trial design for phase 6`
3. `docs(plan): log field-access contacts and expected response window`

⚠ This WI is `[gate]` for **Phase 6**, not Phase 0 — Phase 0 exits whether or not
there is a reply. But if there is no reply by week 6, escalate; if none by week 12,
commit to the fallback and stop waiting.

---

### WI-0.1 — Repository scaffold and licence

**Why** A repo with no licence cannot be cited, forked, or shown to an employer's
legal team.

**Touches** `LICENSE`, `.gitignore`, `.tool-versions`, `CHANGELOG.md`

**Done when** `git status` is clean on a fresh checkout with a Python venv present.

**Commit ladder**
1. `chore: add Apache-2.0 licence`
2. `chore: add gitignore for python, dart, editors and coverage output`
3. `chore: pin python and dart runtimes in tool-versions`
4. `docs: add changelog with keep-a-changelog structure`

**Licence note:** Apache-2.0 over MIT for the explicit patent grant. This project may
end up adjacent to a government programme; a patent grant removes one class of
question. Record the reasoning in the decision log — a licence choice with a stated
reason reads differently from a default.

---

### WI-0.2 — Python package scaffold

**Why** Everything in Phase 1 needs somewhere to land.

**Touches** `dhara-py/pyproject.toml`, `dhara-py/dhara/__init__.py`,
`dhara-py/tests/`

**Depends on** WI-0.1

**Done when** `uv run pytest` passes with zero tests collected and no warnings, and
`pip install -e ../dhara/dhara-py` works from a sibling venv.

**Commit ladder**
1. `build(py): add pyproject with package metadata and python 3.11 floor`
2. `build(py): add dev dependency group - pytest, hypothesis, ruff, mypy`
3. `build(py): configure ruff lint and format rules`
4. `build(py): configure mypy in strict mode`
5. `build(py): configure pytest markers for property, conformance and sim suites`
6. `feat(py): add empty dhara package with version constant`
7. `test(py): add import smoke test so the suite is non-empty`

---

### WI-0.3 — CI running an empty suite

**Why** Roadmap Phase 0 deliverable, verbatim: *"CI running an empty test suite."*
The value is that the pipeline is proven before there is anything at stake.

**Touches** `.github/workflows/py.yml`

**Depends on** WI-0.2

**Done when** A green check appears on a pushed commit and the whole run is under 3
minutes.

**Commit ladder**
1. `ci: add python workflow running ruff, mypy and pytest`
2. `ci: add 3.11 and 3.12 matrix legs`
3. `ci: cache uv downloads between runs`
4. `ci: add coverage reporting with a 90 percent gate on dhara`
5. `ci: randomise PYTHONHASHSEED on one matrix leg`

The last rung matters more than it looks: it is the mechanical guard against a
`join` whose result depends on dict iteration order, which is a convergence bug that
passes every test on your machine. → `ci-and-tooling.md` §5.3

---

### WI-0.4 — Catalogue format and entry template `[spec]`

**Why** Twenty scenarios written in twenty shapes cannot be mechanically turned into
vectors. Fix the shape first.

**Touches** `spec/conflict-catalogue.md`

**Done when** The template has been used to write one entry end to end, and that
entry contains no sentence of the form "and then it resolves sensibly."

**Entry template**

```markdown
### C-NN — <short name>

**Setup**        Which replicas, what each did, in what causal relationship.
**Concurrency**  Which operations are concurrent (neither happens-before the other).
**Naive outcome** What LWW does. Usually: what is silently lost.
**Desired outcome** The exact merged state. Field by field. No prose hedging.
**Lattice**      Which lattice type produces that outcome.
**Review signal** Emitted or not, and which one.
**Vector**       Path under spec/conformance/ once Phase 1 writes it.
**Open**         Anything genuinely undecided, linked to open-questions.md.
```

**Commit ladder**
1. `spec: add conflict catalogue skeleton with entry template`
2. `spec: state the catalogue's role as the source of conformance vectors`
3. `spec: add C-01 two workers weigh the same child within an hour`
4. `spec: document the naive-outcome field as mandatory, not optional`

The **naive outcome** field is mandatory and it is the most useful line in each
entry. Writing down what LWW loses, per scenario, is the entire argument of the
project in concrete form — and it is what §11's positioning line is built from.

---

### WI-0.5 — Catalogue entries: measurements `[spec]` `[gate]`

**Why** The measurement scenarios are where LWW does the most damage and where the
`MeasurementSeries` design is justified.

**Touches** `spec/conflict-catalogue.md`

**Depends on** WI-0.4

**Done when** Entries C-01 through C-06 are written and each states a merged state
field by field.

| ID | Scenario | Sketch of desired outcome |
|---|---|---|
| C-01 | Two workers weigh the same child within an hour | Both readings retained, causally ordered. Review signal `multiple_weights_same_day`. |
| C-02 | Same reading delivered twice by two sync paths | One entry. Dedup on `(taken_at, recorded_by, value)`, **not** on HLC — the second delivery has a fresh HLC. |
| C-03 | Measurement entered, corrected, correction corrected | All three retained as a causal chain; the latest is `current`, the earlier two are `superseded`, none deleted. |
| C-04 | Weight recorded on device A while device B records height | Independent fields, clean union, no review signal. The boring case must be boring. |
| C-05 | Measurement recorded with a `taken_at` in the future (worker set the clock wrong) | Accepted, retained, flagged `implausible_taken_at`. Never silently rewritten. |
| C-06 | Same child, same field, same value, same second, two devices | Deduped to one entry. Two workers doing the same job is not a conflict. |

**Commit ladder**
1. `spec: add C-02 duplicate delivery of one physical reading`
2. `spec: add C-03 correction of a correction retains the causal chain`
3. `spec: add C-04 independent fields on two devices union cleanly`
4. `spec: add C-05 implausible taken_at is flagged, never rewritten`
5. `spec: add C-06 identical concurrent reading dedups to one entry`
6. `spec: record the dedup key rationale for measurement series`

⚠ C-02 vs C-06 look identical and are not. C-02 is one physical event delivered
twice; C-06 is two physical events that happen to be identical. **The engine cannot
distinguish them and must not try** — both dedup to one entry, and that is the
correct, defensible loss of information. Write this down, because it will be asked.

---

### WI-0.6 — Catalogue entries: demographics and status `[spec]` `[gate]`

**Why** These are where `keep_losers=True` and the domain join earn their place.

**Touches** `spec/conflict-catalogue.md`

| ID | Scenario | Sketch of desired outcome |
|---|---|---|
| C-07 | Supervisor corrects a name while the worker edits the address | Both apply; different fields. No conflict. |
| C-08 | Two devices edit the same name spelling concurrently | HLC winner is current; **loser retained in history and visible to a supervisor.** Review signal `concurrent_demographic_edit`. |
| C-09 | Child marked graduated on one device, re-enrolled on another | `graduated` wins the join — it is terminal. Re-enrolment must be an explicit new record. Review signal `reenrolment_after_graduation`. |
| C-10 | Status moves prospective → enrolled on A, prospective → transferred on B | Domain join over the defined partial order, not a timestamp comparison. Outcome stated explicitly in the entry. |
| C-11 | Record deleted on one device, updated on another | Tombstone plus the update, surfaced for review. **The engine declines to decide.** |
| C-12 | Guardian phone changed on A, cleared on B | Clear is a value, not an absence. LWW with the loser retained. |

**Commit ladder**
1. `spec: add C-07 disjoint demographic edits apply cleanly`
2. `spec: add C-08 concurrent name edit keeps the loser in history`
3. `spec: add C-09 graduated is terminal in the enrolment lattice`
4. `spec: add C-10 concurrent status transitions resolve by domain join`
5. `spec: add C-11 delete versus update declines to decide`
6. `spec: add C-12 clearing a field is a value, not an absence`
7. `spec: state the partial order for the enrolment status lattice`

⚠ C-11 is the entry that most tempts a shortcut. "Delete wins" and "update wins" are
both defensible and both wrong — one loses a measurement, the other resurrects a
record a supervisor deliberately removed. Surfacing it is the answer, and roadmap
§6.2 already says so: *a sync engine that admits it does not know is more trustworthy
than one that silently guesses.*

---

### WI-0.7 — Catalogue entries: identity, sessions, clocks `[spec]` `[gate]`

**Why** These are the scenarios that are specific to this deployment and that
generic sync engines do not model at all.

**Touches** `spec/conflict-catalogue.md`

| ID | Scenario | Sketch of desired outcome |
|---|---|---|
| C-13 | Same child registered independently at two centres | Both accepted. Server detects, merges, propagates a forwarding pointer. Devices holding the losing UUID resolve through it. → §6.4(a) |
| C-14 | Concurrent add and remove of a risk flag | OR-Set: add wins when the remove did not observe it. |
| C-15 | Device clock 3 days behind; its edits must not all lose | HLC causal ordering holds. **No edit loses solely because of skew.** |
| C-16 | Device clock jumps forward 2 days, then back | HLC physical component is monotonic; no regression, no counter explosion. |
| C-17 | Worker's session expires mid-sync; another worker logs in on the same phone | Partial sync is durable. Operations attributed to the worker who made them, not the device or the current session. |
| C-18 | Photo uploaded from device A, metadata edited on device B | Blob and metadata are separate lanes; metadata merge does not wait on the blob. |
| C-19 | Server-side bulk correction lands while a device is offline | Bulk correction is ordinary operations with server provenance. Device edits after reconnect do not silently revert it. |
| C-20 | Two devices append to the same OR-Set, one then goes offline six months | Convergence on reconnect. Tombstone retention must not have GC'd the removes. → open-questions.md Q2 |

**Commit ladder**
1. `spec: add C-13 independent registration at two centres`
2. `spec: add C-14 concurrent add and remove on a risk flag`
3. `spec: add C-15 three-day clock lag must not cost a device its edits`
4. `spec: add C-16 clock jump forward then back stays monotonic`
5. `spec: add C-17 session expiry mid-sync attributes ops to the worker`
6. `spec: add C-18 photo blob and metadata travel in separate lanes`
7. `spec: add C-19 server bulk correction versus offline device edits`
8. `spec: add C-20 six-month offline replica versus tombstone GC`
9. `spec: link C-20 to the open question on tombstone retention`

---

### WI-0.8 — Catalogue entries: adversarial and operational `[spec]`

**Why** Twenty is the floor, not the target. These four are the ones that come from
thinking about the deployment rather than the data model.

**Touches** `spec/conflict-catalogue.md`

| ID | Scenario | Sketch of desired outcome |
|---|---|---|
| C-21 | Sync interrupted after chunk 7 of 20, resumed from a different network | Resumes at chunk 8. Zero re-transmission of 1–7, zero duplicate application. |
| C-22 | Same operation delivered through two sessions concurrently | Idempotent by operation ID. Second application is a no-op, not an error. |
| C-23 | Device restored from a backup, replaying already-synced operations | Version vector rejects them as already-seen. No duplicate measurements. |
| C-24 | Two devices assigned the same device ID by an ops mistake | Detected — HLC ties break on device ID, so identical IDs break total order. Must fail loudly at enrolment, not corrupt silently. |

**Commit ladder**
1. `spec: add C-21 resumption after mid-transfer interruption`
2. `spec: add C-22 concurrent delivery of one operation is idempotent`
3. `spec: add C-23 backup restore must not replay synced operations`
4. `spec: add C-24 duplicate device id must fail loudly at enrolment`
5. `spec: add catalogue index table with lattice and review-signal columns`

⚠ C-24 is the one that will not be found by the simulator unless it is explicitly
modelled, because the simulator generates unique device IDs by construction. Note
that in the entry — it is an honest limit of the harness and belongs in
`docs/honest-tradeoffs.md` in Phase 6.

---

### WI-0.9 — Merge semantics skeleton `[spec]`

**Why** The catalogue says what should happen. This says which algebraic object makes
it happen, and why that one.

**Touches** `spec/merge-semantics.md`

**Depends on** WI-0.5 … WI-0.8

**Done when** Every catalogue entry's `**Lattice**` line points at a section here,
and every section lists the catalogue entries it is responsible for. The mapping is
total in both directions.

**Commit ladder**
1. `spec: add merge-semantics skeleton with the field-kind to lattice table`
2. `spec: specify LWWRegister with keep_losers as the default, not an option`
3. `spec: specify MeasurementSeries as append-only with an explicit dedup key`
4. `spec: specify StatusLattice as a domain join over a declared partial order`
5. `spec: specify ORSet observed-remove semantics`
6. `spec: specify GSet and where it is preferred over ORSet`
7. `spec: add the unresolvable case and its review-queue contract`
8. `spec: cross-link every catalogue entry to its lattice section`

The rationale is the deliverable, not the choice. Roadmap Phase 1 exit criteria:
*"written with rationale for each choice, not just the choice."* Start that habit
here, while the reasoning is fresh from writing the catalogue.

---

### WI-0.10 — Protocol v0.1 draft `[spec]`

**Why** Phase 3 implements this. A draft now means Phase 3 is implementation rather
than design-while-implementing.

**Touches** `spec/protocol-v0.1.md`

**Done when** The session state machine has every state, every transition, and every
transition's failure edge drawn. A transition with no failure edge is a transition
you have not thought about — on this network, every one of them has one.

**Contents**
- Session lifecycle: `handshake → negotiate → push → pull → commit → close`
- What happens on abrupt close in each state (this is the normal case, not the
  exception)
- Chunk framing, offsets, acknowledgement
- Operation ID format and the idempotence contract
- Priority lanes and their scheduling rule
- Version negotiation
- Error taxonomy: retryable, fatal, needs-review

**Commit ladder**
1. `spec: add protocol v0.1 draft with session lifecycle states`
2. `spec: define the chunk frame and acknowledged-offset scheme`
3. `spec: define operation ids and the idempotence contract`
4. `spec: define priority lanes and the growth-before-photos rule`
5. `spec: define version negotiation and the unsupported-version path`
6. `spec: add the error taxonomy - retryable, fatal, needs-review`
7. `spec: add failure edges for every state transition`
8. `spec: mark protocol v0.1 as draft and list what phase 3 may change`

⚠ Mark it **draft** loudly. Roadmap §10 lists "protocol churn breaks CGMS
repeatedly" as a medium risk; a document that looks frozen but is not is how that
risk materialises.

---

### WI-0.11 — Conformance vector schema `[spec]`

**Why** Two implementations read these files. A vector that Python parses and Dart
rejects is a build failure with a confusing message unless the format is validated
independently of both.

**Touches** `spec/conformance/schema.json`, `spec/conformance/README.md`

**Done when** A deliberately malformed vector is rejected by the validator with a
useful message.

**Commit ladder**
1. `spec: add JSON Schema for conformance vectors`
2. `spec: define the hlc vector shape`
3. `spec: define the merge vector shape - replicas plus expected join`
4. `spec: define the session transcript vector shape as a phase 3 placeholder`
5. `spec: add conformance README explaining the runner contract`
6. `test(conformance): validate every vector against the schema in CI`

---

### WI-0.12 — Decision records and living documents

**Why** In month five you will not remember why the dedup key excludes the HLC. The
decision log is cheaper than rediscovering it.

**Touches** `docs/adr/`, `plan/decision-log.md`, `plan/open-questions.md`,
`plan/tracking-board.md`

**Commit ladder**
1. `docs: add ADR directory with the template and ADR-0001 on the repo split`
2. `docs: add ADR-0002 on two implementations against one spec`
3. `docs: add ADR-0003 on Apache-2.0 over MIT`
4. `docs(plan): seed the decision log with phase 0 decisions`
5. `docs(plan): seed open questions from roadmap section 12`
6. `docs(plan): seed the tracking board with all phase 0 work items`

---

### WI-0.13 — Pre-commit hooks

**Why** Cheaper than CI round-trips, and the authorship hook is cheaper than a
history rewrite. → `ci-and-tooling.md` §3

**Touches** `.pre-commit-config.yaml`

**Done when** Total hook runtime is under 5 seconds on a warm cache.

**Commit ladder**
1. `chore: add pre-commit with ruff lint and format`
2. `chore: add mypy pre-commit hook scoped to changed files`
3. `chore: add conventional-commit message validation`
4. `chore: reject co-author and generated-by trailers in commit messages`
5. `docs: document pre-commit setup in the contributing notes`

---

### WI-0.14 — Phase 0 exit review `[gate]`

**Touches** `plan/tracking-board.md`, `CHANGELOG.md`

**Commit ladder**
1. `docs(plan): record phase 0 exit checklist results`
2. `docs: add changelog entry for the phase 0 spec baseline`
3. `chore: tag phase-0-complete`

---

## Exit checklist

Tick every box. Do not start Phase 1 with an unticked box.

- [ ] **≥ 20 catalogue entries** (target here is 24), each with a desired outcome
      stated field by field, with no sentence containing "sensibly", "appropriately",
      or "as expected".
- [ ] Every entry names its lattice and whether it emits a review signal.
- [ ] Every entry's naive-LWW outcome is written down. This is the argument of the
      project in concrete form.
- [ ] `merge-semantics.md` maps every field kind to a lattice, and the mapping is
      total in both directions against the catalogue.
- [ ] `protocol-v0.1.md` draft exists, every state transition has a failure edge,
      and the document is clearly marked draft.
- [ ] Conformance vector JSON Schema exists and rejects a malformed vector with a
      useful message.
- [ ] `dhara-py/` scaffold installs into a sibling venv via path dependency.
- [ ] CI is green on an empty suite, under 3 minutes, with the hash-seed leg.
- [ ] Pre-commit runs under 5 seconds and rejects a co-author trailer.
- [ ] Field-access request sent, response window recorded, fallback named.
- [ ] `phase-0-complete` tag pushed, annotated with these results.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| Catalogue entries drift into prose | Entries contain "and then it merges correctly" | Rewrite that entry as a field-by-field table. If you cannot, it is an open question, not an entry — move it. |
| Two weeks becomes four | Week 3 starts with 12 entries | Ship 20 entries and a thinner protocol draft. Phase 1 can absorb protocol work; it cannot absorb missing scenarios. |
| Starting `hlc.py` early | Any commit with scope `hlc` before the exit checklist | Stop. The HLC is four hours in Phase 1 and is not the risk. |
| Designing the whole protocol | Protocol draft exceeds ~1,500 words in week 2 | It is a draft. Phase 3 is where it earns detail. |
