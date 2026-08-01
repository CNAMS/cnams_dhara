# Phase 1 — Clocks and lattices

**Weeks 3–5 · ~42 hours · ~95 commits**

> HLC, then the five lattice types, then the first conformance vectors.
> — roadmap §8, Phase 1

**Exit criteria (roadmap):** property tests green over 10,000 randomised operation
orders per lattice. HLC ordering correct under ±3 days of simulated skew.
`merge-semantics.md` written with rationale for each choice, not just the choice.

---

## The shape of this phase

Everything here is pure, deterministic, and testable in isolation. No I/O, no
network, no persistence. That is deliberate — this is the layer where a bug is
cheapest to find and most expensive to ship, because Phase 2's simulator and
Phase 4's Dart port both assume it is right.

```
hlc.py ──▶ lattice/base.py ──▶ five lattice types ──▶ schema.py ──▶ conformance.py
   │                                   │                               │
   └──── property tests ───────────────┘                               │
                                                                       ▼
                                                     spec/conformance/{hlc,merge}/*.json
```

**Ordering rule for this phase:** for each lattice, the conformance vector is written
*before* the implementation, from the catalogue entry it comes from. The vector fails,
then the implementation makes it pass. This puts the specification of behaviour before
the behaviour in the history, which is the point of the ladder.

---

## Work items

### WI-1.0 — Enforce the dependency rule in CI `[gate]`

**Why** Roadmap §4: the repository boundary enforces a discipline a folder boundary
will not — but only if something checks it. This is that thing.

**Touches** `scripts/check_no_domain_imports.py`, `.github/workflows/py.yml`

**Done when** A test file containing `beneficiary` fails CI, and the failure message
names the file, line, and forbidden token.

**Commit ladder**
1. `feat(py): add domain-token checker script with the forbidden word list`
2. `test(py): assert the checker rejects a fixture containing a domain token`
3. `test(py): assert the checker allows an origin-note annotated comment`
4. `ci: run the domain-token checker on every push`
5. `docs: explain the dependency rule and the escape hatch in the checker`

The escape hatch (`# origin-note:`) exists so `docs/` prose can describe where the
project came from. It is deliberately ugly to type, because every use should be a
small decision.

---

### WI-1.1 — HLC type and ordering

**Why** Everything causally ordered depends on this. → roadmap §6.1

**Touches** `dhara/hlc.py`, `tests/unit/test_hlc.py`

**Done when** `HLC` is an immutable, totally ordered, round-trippable value.

**Design notes**
- Immutable frozen dataclass: `(pt: int, c: int, node_id: str)`. Milliseconds since
  epoch for `pt`; a 64-bit-safe integer, never a float.
- Total order: `(pt, c, node_id)` lexicographically. **Ties break on `node_id` so the
  total order is deterministic across replicas** (roadmap §6.1). Without that tiebreak
  two replicas can order the same pair differently and never converge.
- Wire encoding is fixed-width so lexicographic byte order matches value order —
  it makes the store's index usable for causal range scans in Phase 4.

**Commit ladder**
1. `feat(hlc): add immutable HLC value type with pt, c and node_id`
2. `feat(hlc): implement total ordering with node_id as the final tiebreak`
3. `test(hlc): assert ordering is total, irreflexive and transitive`
4. `feat(hlc): add fixed-width string encoding that sorts lexicographically`
5. `test(hlc): round-trip encode and decode preserves ordering`
6. `test(hlc): reject non-integer physical time at construction`

---

### WI-1.2 — HLC send path

**Why** Half the algorithm; the half that runs on every local write.

**Touches** `dhara/hlc.py`, `tests/unit/test_hlc.py`

**Depends on** WI-1.1

**Algorithm** (roadmap §6.1)

```
send(event):
    pt = max(local_physical_time, last.pt)
    if pt == last.pt: c = last.c + 1
    else:             c = 0
    last = (pt, c)
    return (pt, c, device_id)
```

**Done when** A clock that goes backwards produces monotonically increasing HLCs.

**Commit ladder**
1. `feat(hlc): add clock state holding the last issued timestamp`
2. `feat(hlc): implement send using max of physical and last pt`
3. `feat(hlc): increment the logical counter when physical time has not advanced`
4. `test(hlc): send is strictly monotonic across 10k successive calls`
5. `test(hlc): send stays monotonic when the physical clock jumps backwards`
6. `feat(hlc): inject physical_time as a callable rather than reading the wall clock`
7. `test(hlc): send with a frozen clock advances only the logical counter`

⚠ Rung 6 is a reproducibility requirement, not a style preference. `dhara/` must
contain **no wall-clock reads** — the simulator's entire clock-skew capability
depends on injecting virtual time here. → `ci-and-tooling.md` §5.2

---

### WI-1.3 — HLC receive path

**Why** The other half, and the one with four branches that are easy to get subtly
wrong.

**Touches** `dhara/hlc.py`

**Depends on** WI-1.2

```
receive(remote):
    pt = max(local_physical_time, last.pt, remote.pt)
    if pt == last.pt == remote.pt: c = max(last.c, remote.c) + 1
    elif pt == last.pt:            c = last.c + 1
    elif pt == remote.pt:          c = remote.c + 1
    else:                          c = 0
    last = (pt, c)
```

**Done when** Each of the four branches has a test that fails if that branch alone
is broken.

**Commit ladder**
1. `feat(hlc): implement receive with the three-way max of physical times`
2. `feat(hlc): handle the branch where local and remote pt both equal the new pt`
3. `feat(hlc): handle the branches where only one side matches the new pt`
4. `feat(hlc): handle the branch where physical time exceeds both`
5. `test(hlc): cover each receive branch in isolation`
6. `test(hlc): receive advances past a remote timestamp from the future`
7. `test(hlc): causality survives a message received before its local successor`

---

### WI-1.4 — HLC under clock skew `[gate]`

**Why** Direct phase exit criterion: ordering correct under ±3 days of simulated
skew. Roadmap §6.1: *"This is where most homegrown sync layers quietly corrupt
themselves."*

**Touches** `tests/property/test_hlc_skew.py`

**Depends on** WI-1.3

**Done when** A Hypothesis run of 10,000 examples with per-device offsets drawn from
±3 days finds no violation of: *if A causally precedes B, then `hlc(A) < hlc(B)`.*

**Commit ladder**
1. `test(hlc): add a skewed-clock strategy generating offsets within three days`
2. `test(hlc): property - causal precedence implies hlc ordering under skew`
3. `test(hlc): property - concurrent events are ordered consistently on all replicas`
4. `test(hlc): property - the logical counter stays bounded under sustained skew`
5. `test(hlc): regression for a device three days behind not losing every edit`
6. `docs: add ADR-0004 on why wall-clock timestamps are not used for ordering`

⚠ Rung 4 catches the failure that looks like success: a device far in the past
whose counter increments on every message and eventually overflows or dominates the
sort. The property to assert is that `c` stays bounded by the number of messages
exchanged in one physical-time tick, not by total message count.

---

### WI-1.5 — HLC conformance vectors `[spec]`

**Touches** `spec/conformance/hlc/*.json`

**Commit ladder**
1. `spec: add hlc vector for monotonic send under a frozen clock`
2. `spec: add hlc vector for receive from a future timestamp`
3. `spec: add hlc vector for the three-day-behind device`
4. `spec: add hlc vector for a clock jumping forward then back`
5. `spec: add hlc vector for tie-breaking on node id`
6. `test(conformance): run the hlc vectors in the python suite`

These five vectors are what the Dart implementation must reproduce byte for byte in
Phase 4. Write them as transcripts — a sequence of `send`/`receive` operations and
the expected clock state after each — not as isolated assertions.

---

### WI-1.6 — Lattice base contract

**Why** Five types with one contract. The contract is what the property tests test
and what the schema descriptor depends on.

**Touches** `dhara/lattice/base.py`, `tests/property/laws.py`

**Contract**

```python
class Lattice(Protocol[T]):
    def join(self, other: Self) -> Self: ...   # commutative, associative, idempotent
    def leq(self, other: Self) -> bool: ...    # partial order induced by join
    def to_json(self) -> JSONValue: ...
    @classmethod
    def from_json(cls, v: JSONValue) -> Self: ...
```

**Done when** A reusable law-checking helper exists that any lattice type can be
handed to, so adding a lattice costs three lines of test, not thirty.

**Commit ladder**
1. `feat(lattice): add the Lattice protocol with join, leq and json codecs`
2. `feat(lattice): document the join contract - commutative, associative, idempotent`
3. `test(lattice): add reusable law checkers parameterised by a strategy`
4. `test(lattice): assert leq agrees with join - a leq b iff join(a,b) == b`
5. `feat(lattice): add canonical serialisation so equal states compare equal`
6. `test(lattice): canonical form is stable under insertion order`

⚠ Rung 5/6 are the guard against the convergence bug that hides in set iteration
order. Two replicas with the same logical state must produce **identical bytes**, or
Phase 3's delta computation will see spurious differences and resend forever.

---

### WI-1.7 — GSet

**Why** The simplest lattice. Build it first to validate the base contract and the
law harness on something with no subtlety.

**Touches** `dhara/lattice/g_set.py`

**Commit ladder**
1. `feat(gset): add grow-only set with join as union`
2. `test(gset): property - commutativity, associativity, idempotence over 10k orders`
3. `feat(gset): add canonical json codec with sorted elements`
4. `test(gset): round-trip through json preserves equality`

---

### WI-1.8 — LWWRegister with retained losers `[gate]`

**Why** Roadmap §5.4: *"A last-write-wins register that discards the loser is a
data-loss bug wearing a design-decision costume."* This is the WI where that
sentence becomes code.

**Touches** `dhara/lattice/lww_register.py`

**Depends on** WI-1.1, WI-1.6

**Design notes**
- State is `(current: (value, hlc, author), history: frozenset[(value, hlc, author)])`.
- `join` picks the HLC-max as `current` and puts **every** other observed value into
  `history`. Nothing is ever dropped.
- `keep_losers` is **not a constructor flag.** Retention is the semantics. There is
  no code path that discards. → EXECUTION.md non-negotiable #2
- History is a set, not a list, so joins stay idempotent.

**Commit ladder**
1. `feat(lww): add register holding a current value and an author`
2. `feat(lww): implement join selecting the hlc-maximal value`
3. `feat(lww): retain every non-winning observed value in history`
4. `test(lww): property - the three lattice laws over 10k orders`
5. `test(lww): join never reduces the size of the observed value set`
6. `test(lww): concurrent edits keep the loser reachable - catalogue C-08`
7. `feat(lww): emit a concurrent_demographic_edit review signal on a real tie`
8. `test(lww): clearing a field is a value, not an absence - catalogue C-12`
9. `feat(lww): add canonical json codec with history sorted by hlc`
10. `docs: add ADR-0005 on retaining losers as semantics rather than an option`

⚠ Rung 5 is the invariant that makes rung 3 provable rather than asserted: *for any
`a`, `b`, the set of values observable in `join(a, b)` is exactly the union of those
observable in `a` and `b`.* That is the no-silent-data-loss property for this lattice,
and Phase 2's `no_measurement_lost` invariant is its generalisation.

---

### WI-1.9 — ORSet

**Why** Risk flags and referrals. The `add` must win a concurrent `remove` that never
observed it (catalogue C-14).

**Touches** `dhara/lattice/or_set.py`

**Design notes**
- Each add carries a unique tag `(hlc, node_id)`. A remove carries **the set of tags
  it observed**, not the element.
- Concurrent add + remove ⇒ the add's tag was not observed ⇒ it survives.
- Tombstones are the tag set. Retention policy is open question Q2 and is **not**
  resolved in this phase; the code keeps everything and a `TODO(Q2)` marks the site.

**Commit ladder**
1. `feat(orset): add observed-remove set with per-add unique tags`
2. `feat(orset): implement join as union of adds minus union of observed removes`
3. `test(orset): property - the three lattice laws over 10k orders`
4. `test(orset): concurrent add and remove resolves to add - catalogue C-14`
5. `test(orset): sequential add then remove resolves to remove`
6. `test(orset): re-add after remove is observable`
7. `feat(orset): add canonical json codec with tags sorted by hlc`
8. `chore(orset): mark tombstone retention as open question Q2 at the gc site`

---

### WI-1.10 — MeasurementSeries `[gate]`

**Why** The conceptual centre of the project. Roadmap §6.2: *a child's weight is not
a mutable field.*

**Touches** `dhara/lattice/measurement_series.py`

**Depends on** WI-1.7

**Design notes**
- Append-only set of entries, deduplicated on a **schema-declared key**, default
  `(taken_at, recorded_by, value)`.
- The dedup key **excludes the HLC by design.** The same physical reading delivered
  by two paths gets a fresh HLC on the second, so keying on it would admit exactly
  the duplicate the key exists to reject (catalogue C-02).
- The consequence is that two genuinely distinct identical readings dedup to one
  (catalogue C-06). This is a real, accepted loss of information. Document it; do
  not fix it.
- **No overwrite path exists.** Corrections are new entries that supersede, linked by
  a `supersedes` reference (catalogue C-03).

**Commit ladder**
1. `feat(series): add append-only measurement entry with taken_at and recorded_by`
2. `feat(series): implement join as deduplicated union`
3. `feat(series): make the dedup key schema-declared with a documented default`
4. `test(series): property - the three lattice laws over 10k orders`
5. `test(series): duplicate delivery of one reading dedups - catalogue C-02`
6. `test(series): two distinct identical readings also dedup - catalogue C-06`
7. `feat(series): add supersedes links for corrections`
8. `test(series): correction of a correction retains the chain - catalogue C-03`
9. `test(series): join never removes an entry, ever`
10. `feat(series): emit multiple_weights_same_day on same-day duplicates - C-01`
11. `feat(series): emit implausible_taken_at without rewriting the value - C-05`
12. `test(series): entries are ordered by hlc for display, not by taken_at`
13. `feat(series): add canonical json codec`
14. `docs: add ADR-0006 on excluding the hlc from the dedup key`

⚠ Rung 9 is the test that Phase 2's deliberate-bug experiment will disable. Write it
so it is obviously the load-bearing one — the experiment's credibility depends on
the injected bug being one a reasonable person could have written, and "someone
replaced the append with an assignment" is exactly that.

---

### WI-1.11 — StatusLattice

**Why** Enrolment status is a domain partial order, not a timestamp comparison
(catalogue C-09, C-10).

**Touches** `dhara/lattice/status.py`

**Design notes**
- The join function is **supplied by the schema descriptor**, not defined here.
  `dhara` provides the machinery and validates the supplied function's algebraic
  properties; the domain provides the order.
- Validation at schema-construction time: the supplied join must be commutative,
  associative and idempotent over the declared value set. An invalid domain join is
  a configuration error caught at startup, not a convergence bug found in month four.
- `graduated` being terminal is a **CGMS** fact and lives in the consumer's
  `schema_binding.py`. `dhara` must not know it. The example in roadmap §5.4 is an
  illustration of the API, not a value shipped in this repo.

**Commit ladder**
1. `feat(status): add status lattice parameterised by a domain join`
2. `feat(status): validate the domain join over the declared value set at construction`
3. `test(status): reject a non-commutative domain join with a useful message`
4. `test(status): reject a non-idempotent domain join`
5. `test(status): reject a join over values outside the declared set`
6. `test(status): property - the three laws hold for a valid domain join`
7. `test(status): terminal-state ordering resolves as declared - catalogue C-09`
8. `test(status): concurrent transitions resolve by the domain order - C-10`
9. `feat(status): emit a review signal when the join is defined but ambiguous`
10. `feat(status): add canonical json codec`

⚠ Rung 2 is where an exhaustive check is affordable and worth it: for a value set of
realistic size, check all triples. The alternative is discovering in Phase 3 that the
domain join was never associative and nothing ever converged.

---

### WI-1.12 — Schema descriptor API

**Why** The runtime interface between `dhara` and any domain. → roadmap §5.4

**Touches** `dhara/schema.py`

**Depends on** WI-1.7 … WI-1.11

**Done when** The roadmap §5.4 `BENEFICIARY` sketch can be constructed — **in a test
fixture using neutral field names**, not with the domain vocabulary — and validated.

**Commit ladder**
1. `feat(schema): add Field descriptor binding a name to a lattice type`
2. `feat(schema): add Schema holding an ordered field list`
3. `feat(schema): pass lattice-specific options through to the constructor`
4. `test(schema): reject a duplicate field name`
5. `test(schema): reject an unknown lattice type with a useful message`
6. `feat(schema): validate every declared status join at schema construction`
7. `feat(schema): add a record type that applies field-wise join across a schema`
8. `test(schema): record join is field-wise and independent - catalogue C-04, C-07`
9. `test(schema): property - record join satisfies the three laws`
10. `feat(schema): add schema json codec for wire transmission`
11. `test(schema): a schema round-trips through json unchanged`

⚠ Rung 8 is the one people skip. Field-wise independence is what makes "supervisor
corrects the name while the worker edits the address" a non-event. It is also the
property most easily broken later by a well-meaning cross-field validation rule.

---

### WI-1.13 — Review signal emission

**Why** Roadmap §6.2's last row — *genuinely ambiguous → surface to supervisor review
queue* — and open question Q1. Leaning is settled here: **`dhara` emits the signal,
the consumer owns the UI.**

**Touches** `dhara/review.py`, `spec/review-signals.md`

**Commit ladder**
1. `spec: add review-signals catalogue with the signal-name registry`
2. `feat(review): add ReviewSignal value type with code, fields and evidence`
3. `feat(review): collect signals emitted during a record join`
4. `test(review): a clean join emits no signals`
5. `test(review): each catalogue-declared signal is emitted by its scenario`
6. `feat(review): make signals part of the join result, not a side channel`
7. `docs: resolve open question Q1 - dhara emits, the consumer renders`

⚠ Rung 6 matters for Phase 4: a signal delivered via a callback or a global list is
a signal the Dart implementation will produce at a different time, and the
conformance comparison will fail for reasons unrelated to merge semantics. Signals
are part of the return value.

---

### WI-1.14 — Conformance runner

**Why** Roadmap §7.3. The runner is the executable form of the spec.

**Touches** `dhara/conformance.py`, `tests/conformance/`

**Commit ladder**
1. `feat(conformance): load and validate vectors against the JSON Schema`
2. `feat(conformance): build replica states from a vector's replicas block`
3. `feat(conformance): apply joins in every permutation of replica order`
4. `feat(conformance): compare against expected using canonical form`
5. `feat(conformance): assert the expected review signals were emitted`
6. `test(conformance): a deliberately wrong expected block fails the runner`
7. `feat(conformance): report diffs field-wise rather than as a whole-blob mismatch`
8. `ci: fail the build on any conformance vector mismatch`

⚠ Rung 3 is not optional. Running only one replica order tests a fraction of the
claim; the claim is order-independence. For n ≤ 4 replicas, run all n! orders.

---

### WI-1.15 — Merge vectors from the catalogue `[spec]` `[gate]`

**Why** This is where Phase 0's catalogue becomes executable. One vector per
catalogue entry that Phase 1 can express.

**Touches** `spec/conformance/merge/*.json`

**Depends on** WI-1.14

**Done when** Every catalogue entry from C-01 to C-16 has a vector, or an explicit
note saying which phase can first express it (C-13, C-17 … C-24 need session,
identity, or crypto machinery that does not exist yet).

**Commit ladder** — one commit per vector, in catalogue order:
1. `spec: add merge vector for C-01 concurrent weights same morning`
2. `spec: add merge vector for C-02 duplicate delivery of one reading`
3. `spec: add merge vector for C-03 correction of a correction`
4. `spec: add merge vector for C-04 independent fields union cleanly`
5. `spec: add merge vector for C-05 implausible taken_at`
6. `spec: add merge vector for C-06 identical concurrent readings`
7. `spec: add merge vector for C-07 disjoint demographic edits`
8. `spec: add merge vector for C-08 concurrent name edit keeps the loser`
9. `spec: add merge vector for C-09 terminal enrolment state`
10. `spec: add merge vector for C-10 concurrent status transitions`
11. `spec: add merge vector for C-11 delete versus update declines to decide`
12. `spec: add merge vector for C-12 clearing a field`
13. `spec: add merge vector for C-14 concurrent add and remove on a flag`
14. `spec: add merge vector for C-15 three-day-behind device`
15. `spec: add merge vector for C-16 clock jump forward then back`
16. `spec: annotate catalogue entries deferred to phases 3 and 5 with their phase`
17. `spec: add the vector index table mapping catalogue ids to files`

The vectors use **neutral field names** (`m_a`, `d_a`, `st_a`, `set_a`), never domain
vocabulary. The domain mapping lives in the CGMS repo. A vector named
`concurrent_weight_same_morning` is fine as a *filename* describing the shape; a
vector containing a field literally called `child_weight` is a dependency-rule
violation.

---

### WI-1.16 — Complete merge-semantics.md `[spec]` `[gate]`

**Why** Direct exit criterion, and the "with rationale" clause is the part that
matters.

**Touches** `spec/merge-semantics.md`

**Done when** Each lattice section answers: what it is, why this one and not the
obvious alternative, what it costs, and what it refuses to decide.

**Commit ladder**
1. `spec: expand the LWWRegister section with the retained-loser rationale`
2. `spec: expand MeasurementSeries with the dedup-key rationale and its cost`
3. `spec: expand StatusLattice with why a domain join beats a timestamp comparison`
4. `spec: expand ORSet with the observed-remove rationale and tombstone cost`
5. `spec: expand GSet with when to prefer it over ORSet`
6. `spec: add the worked example from roadmap 6.2 with both outcomes`
7. `spec: add the section on what the engine refuses to decide, and why`
8. `spec: add the alternatives-considered table per lattice`

---

### WI-1.17 — Phase 1 exit review `[gate]`

**Commit ladder**
1. `test(lattice): raise the property-test example budget to 10k for every type`
2. `docs: record the phase 1 property-test and skew results`
3. `docs(plan): record phase 1 exit checklist results`
4. `docs: add changelog entry for the lattice and clock layer`
5. `chore: tag phase-1-complete`

---

## Exit checklist

- [ ] Property tests green over **10,000 randomised operation orders per lattice
      type** — commutativity, associativity, idempotence — for GSet, LWWRegister,
      ORSet, MeasurementSeries, StatusLattice.
- [ ] HLC ordering correct under **±3 days of simulated skew**, with the logical
      counter provably bounded.
- [ ] `merge-semantics.md` complete, with rationale and alternatives per lattice.
- [ ] Every catalogue entry expressible without session/identity/crypto machinery
      has a conformance vector; the rest are annotated with the phase that will
      express them.
- [ ] The conformance runner applies **all permutations** of replica order.
- [ ] `join` never reduces the observable value set, for every lattice, asserted as
      a property.
- [ ] Canonical serialisation is stable under insertion order (hash-seed CI leg
      green).
- [ ] Domain-token checker green; `dhara/` contains no domain vocabulary.
- [ ] No wall-clock read anywhere in `dhara/`.
- [ ] Review signals are part of the join return value, not a side channel.
- [ ] `phase-1-complete` tag pushed.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| Property tests pass because the strategy is too narrow | 10k examples run in under a second | Widen the strategy — more replicas, longer op sequences, adversarial HLC values. A fast property test is usually a weak one. |
| The HLC counter grows without bound | Skew test's `c` in the thousands | Rung WI-1.4.4 catches it. The bound is messages-per-physical-tick, not total. |
| Domain vocabulary leaks into vectors | Checker fails on `spec/` | Rename to neutral field names. The mapping belongs in the CGMS repo. |
| StatusLattice's domain join is not associative | Discovered in Phase 3 as non-convergence | WI-1.11 rung 2 validates exhaustively at construction. Do not skip it. |
| Lattices grow toward a general CRDT library | New lattice types nobody asked for | Non-goal §2: fixed catalogue of lattice types only. Five is the number. |
