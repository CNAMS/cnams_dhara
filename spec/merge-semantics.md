# Merge semantics

**Status:** Phase 1 complete · **Implementations:** `dhara-py` ✅ · `dhara-dart` (Phase 4)

[conflict-catalogue.md](conflict-catalogue.md) says what should happen. This document
says which algebraic object makes it happen, and **why that one rather than the
obvious alternative.**

The rationale is the deliverable, not the choice. Phase 1's exit criterion is that
this document is *"written with rationale for each choice, not just the choice"*.

---

## 1. The one idea

> **A child's weight is not a mutable field. It is an event that happened at a time.**

Every design decision below follows from taking that literally.

A system that models a measurement as a column value has already lost. It has one
slot, so two readings cannot both exist in it, so one must be discarded, so the only
remaining question is which — and every answer to that question is wrong. Modelling
it as an event removes the question.

The same reframing applies unevenly across field kinds, which is why there are five
lattices and not one:

| A name spelling | *is* a mutable field. It has a current value; edits replace it. |
| An enrolment status | is a position in a domain-defined order. It moves in permitted directions only. |
| A risk flag set | is a set with membership operations, where "who observed what" decides the outcome. |
| A measurement | is an event. It happened. Nothing later un-happens it. |

---

## 2. The lattice contract

Every lattice type provides a `join` that is:

| Law | Statement | Why it is required |
|---|---|---|
| **Commutative** | `join(a, b) == join(b, a)` | Messages arrive in different orders on different replicas. Without this, delivery order changes the result. |
| **Associative** | `join(join(a, b), c) == join(a, join(b, c))` | Replicas batch differently. A device that syncs once with three operations must match one that syncs three times. |
| **Idempotent** | `join(a, a) == a` | On this network, duplicate delivery is routine (C-22). Without this, a retry corrupts state. |

Together these make the state a **join-semilattice**, and give the property the whole
system is built on: replicas that have seen the same set of operations, **in any
order, with any duplication and any batching**, reach the same state.

⚠ These laws are asserted by property tests over 10,000 randomised operation orders
per type (WI-1.7 through WI-1.11), not by inspection. A `join` whose result depends
on set iteration order satisfies all three laws in every hand-written test and
violates them in production — which is why one CI leg runs with a randomised
`PYTHONHASHSEED`.

---

## 3. Field kind → lattice

| Field kind | Lattice | Merge rule | Catalogue entries |
|---|---|---|---|
| Measurements | `MeasurementSeries` | Append-only set, deduplicated on a declared key. **Never overwrite.** | C-01…C-06 |
| Demographics | `LWWRegister` | HLC-ordered winner; **loser retained in history, never deleted** | C-07, C-08, C-12, C-19 |
| Enrolment / service status | `StatusLattice` | Domain-supplied join over a declared partial order. Not a timestamp comparison. | C-09, C-10 |
| Tag-like sets | `ORSet` | Observed-remove; concurrent add and remove resolves to add | C-14 |
| Immutable tag sets | `GSet` | Union | — |
| Genuinely ambiguous | — | **Surface to the review queue** | C-11, C-13 |

That last row is a feature, not a cop-out. **A sync engine that admits it does not
know is more trustworthy than one that silently guesses.**

---

## 4. `MeasurementSeries`

**State** A set of entries. Each entry: value, `taken_at`, `recorded_by`, HLC, and an
optional `supersedes` reference.

**Join** Union, deduplicated on the schema-declared key, default
`(taken_at, recorded_by, value)`.

**There is no overwrite path.** Not a discouraged one — none. Corrections are new
entries that supersede.

### Why the dedup key excludes the HLC

The same physical reading delivered by two sync paths gets a **fresh HLC on the second
path**, because it was re-issued at a different time (C-02). A key that includes the
HLC would treat the two deliveries as distinct and admit exactly the duplicate the key
exists to reject.

### What that costs

Two genuinely distinct readings that agree in every recorded attribute collapse to one
entry (C-06). One of the two weighings leaves no trace.

This is a real, permanent loss of information and it is the correct trade. Nothing in
the data distinguishes C-02 from C-06 — one physical event delivered twice, versus two
physical events that happen to be identical — and the alternative manufactures phantom
weighings on every retried sync. **Phantom data in a clinical record is worse than an
undercount of identical readings.**

> Open: `supersedes` chains are an extension of the roadmap's definition, not part of
> it. → [DOUBTS.md D-03](../DOUBTS.md#d-03)

---

## 5. `LWWRegister`

**State** A current `(value, hlc, author)` plus a **history** set of every other
observed value.

**Join** The HLC-maximal value becomes current; **every** other observed value goes
into history. Nothing is ever dropped.

**Order** `(pt, c, node_id)` lexicographically. The `node_id` tiebreak is what makes
the order total and identical on every replica — without it, two replicas can order
the same pair differently and never converge.

### Why the loser is retained

> A last-write-wins register that discards the loser is a data-loss bug wearing a
> design-decision costume. — roadmap §5.4

Concurrent edits to a name spelling (C-08) are not noise. In a transliterated-name
context, a contested spelling is signal — it is one of the ways a duplicate
registration surfaces. Discarding it destroys evidence and produces the reported field
symptom of *"I fixed it and it went back"*, with nothing in the record explaining why.

**Retention is the semantics, not an option.** There is no `keep_losers` parameter.

> Open: the roadmap's own API sketch passes `keep_losers=True` per field.
> → [DOUBTS.md D-02](../DOUBTS.md#d-02)

### Cleared is a value

The register's value type is `Optional[T]`, and `None` participates in ordering like
any other value (C-12). A wire format that omits null fields to save bytes makes
"the guardian asked for this number to be removed" unrepresentable, and the bytes are
not worth it.

### Cost

History grows with the number of concurrent edits to a field, unbounded in principle.
For the field kinds in scope — names, phone numbers, addresses — concurrent edits are
rare and values are small. This would not be an acceptable design for a large text
field, and `dhara` does not offer one.

---

## 6. `StatusLattice`

**State** A single value from a declared, finite value set.

**Join** A **domain-supplied function** over a declared partial order.

### Why not a timestamp comparison

Under LWW, a child marked `graduated` on one device and `enrolled` on another resolves
by whichever clock ran later (C-09). **The outcome depends on clock skew rather than
on domain meaning** — the same two operations in the other order give the opposite
answer, and a child's programme status is decided by which phone had the better clock.

A domain join gives the same answer on every replica regardless of timing, and gives
an answer that means something: `graduated` is terminal because graduation is
terminal, and re-enrolment is an explicit new record.

### Where the order lives

**In the consumer's `schema_binding.py`, not here and not in `dhara`.** `dhara`
provides the machinery and validates the supplied function; the domain provides the
order. The `prospective < enrolled < transferred < graduated` example in roadmap §5.4
is an illustration of the API, not a value shipped in this repository.

### Validation

The supplied join is checked at **schema-construction time** for commutativity,
associativity and idempotence, exhaustively over the declared value set. For a value
set of realistic size, all triples is affordable.

⚠ This check is not optional and not deferrable. An invalid domain join is a
configuration error that should fail at startup — the alternative is discovering in
month four that nothing ever converged, via a simulator failure whose root cause is
three layers away.

---

## 7. `ORSet`

**State** A set of `(element, tag)` adds and a set of observed tags removed. Each add
carries a unique tag `(hlc, node_id)`.

**Join** Union of adds, minus union of observed removes.

### Why observed-remove

A remove carries **the set of tags it observed**, not the element. So a concurrent add
whose tag the remove never saw survives (C-14).

The alternative — keying removes on the element — means a worker clearing stale flags
erases a referral another worker added concurrently. A child referred for acute
malnutrition silently loses the referral. That is the failure this lattice exists to
prevent.

Three cases, all distinct, all tested:

| Sequence | Result |
|---|---|
| Add, then remove (remove observed the add) | Removed |
| Add and remove concurrently (remove did not observe) | **Present** |
| Add, remove, add again | Present |

### Cost

Tombstones. Observed tags cannot be discarded while any replica may still hold an
unsynced operation referencing them, so the tag set grows monotonically until a
retention policy collects it — and collecting too early resurrects removed flags on a
six-month-offline device (C-20).

> Open: the retention period is unresolved and must not be guessed.
> → [plan/open-questions.md](../plan/open-questions.md) Q2

---

## 8. `GSet`

**State** A set. **Join** Union.

Prefer it over `ORSet` whenever elements are **never removed** — an append-only audit
list, a set of immutable identifiers. It has no tombstones and therefore no retention
question, which is worth a great deal on a 2GB device.

⚠ Choosing `GSet` is a claim that removal will never be needed. Migrating `GSet` to
`ORSet` later is a schema and wire-format change, so the claim should be made
deliberately rather than because `GSet` was simpler on the day.

---

## 9. What the engine refuses to decide

Two situations produce no merged answer, by design:

| Situation | Why deciding would be worse |
|---|---|
| **Delete versus concurrent update** (C-11) | "Delete wins" discards a measurement a worker took. "Update wins" resurrects a record a supervisor deliberately removed. Both are defensible; both are wrong. |
| **Duplicate registration candidates** (C-13) | Auto-merging two children who are not the same child corrupts the longitudinal record of two real people, and the worker who notices cannot undo it. |

In both, state is **retained in full** and a review signal is emitted. A human
decides, and the decision propagates as an ordinary operation.

This is not the engine failing to have an opinion. It is the engine declining to
manufacture one, which is a different and better thing.

---

## 10. Review signals

Signals are **part of the join's return value**, not a callback and not a side
channel.

That matters for Phase 4: a signal delivered out-of-band would be produced at a
different moment by the Dart implementation, and the conformance comparison would fail
for reasons unrelated to merge semantics.

Eleven signals are declared by the catalogue. The registry with wire codes and payload
shapes is [review-signals.md](review-signals.md), written in WI-1.13.

---

## 11. Alternatives considered

| Choice | Alternative | Why not |
|---|---|---|
| Five fixed lattices | Arbitrary user-defined lattices | Non-goal §2. Generality here buys nothing and costs months. |
| Two implementations + vectors | One Rust core with FFI | FFI debugging on Android eats the timeline (§5.1). Revisit at v0.2. |
| Domain join for status | Timestamp comparison | Makes the outcome a function of clock skew (C-09). |
| Observed-remove sets | Element-keyed remove sets | Erases concurrent unobserved adds (C-14). |
| Retained losers | Discard on merge | The project's headline claim, inverted. |
| Dedup excluding HLC | Dedup including HLC | Admits a duplicate on every retried sync (C-02). |
| Dedup keeping the **earliest** delivery | Keeping the latest | `max` over HLC makes the kept entry depend on arrival order, so the join is not commutative. `min` is. The earliest HLC is also the causally correct one: a redelivery's fresh HLC is a transport artefact. |
| Signals derived from merged state | Signals accumulated during the join | Accumulating makes them a function of the merge *path* rather than the destination, so two replicas reaching identical state emit different signals — and the Phase 4 comparison fails for reasons unrelated to merge semantics. |
| Integer minor units | Decimal strings, or floats with a fixed precision | Floats format differently in Python and Dart, which breaks byte-identical canonical form and therefore delta computation. Integers remove the class of problem rather than encoding around it. → [DOUBTS.md D-04](../DOUBTS.md#d-04) |
| Status has no history | Retaining prior positions | Its state is a position in an order, not a set of observations; the transition history lives in the operation log. Retaining prior positions would either break idempotence or make the state unbounded, and would duplicate the oplog. |

---

## 12. What is implemented, and how it was checked

| Lattice | Module | Laws | Catalogue |
|---|---|---|---|
| `GSet` | `dhara/lattice/g_set.py` | ✅ | — |
| `LWWRegister` | `dhara/lattice/lww_register.py` | ✅ | C-07, C-08, C-12, C-19 |
| `ORSet` | `dhara/lattice/or_set.py` | ✅ | C-14 |
| `MeasurementSeries` | `dhara/lattice/measurement_series.py` | ✅ | C-01…C-06 |
| `StatusLattice` | `dhara/lattice/status.py` | ✅ | C-09, C-10 |

**Checked three ways, and the three catch different things:**

1. **Property tests** over 1,000 Hypothesis examples per type — commutativity,
   associativity, idempotence, `leq`/`join` agreement, canonical stability,
   JSON round-trip, and the no-loss property.
2. **Conformance vectors** — twelve merge vectors joined in every permutation of
   replica order, with expected states written from the catalogue rather than
   from the code.
3. **Mutation calibration** — deliberately breaking the implementation and
   confirming something fails.

⚠ The third found a gap the first two missed. Keying an OR-Set remove on the
element instead of on observed tags — mutation M4 of the Phase 2 experiment —
passed the entire property suite, because the strategies built OR-Set values
with the constructor and never called `remove()`. **Laws over constructed values
prove the algebra and say nothing about whether the operations producing those
values are right.** `tests/unit/test_or_set_semantics.py` closes it.

### One defect this document caught

C-03's vector was written from the catalogue, which states that a correction
chain emits **no** signal. The implementation emitted `multiple_weights_same_day`,
because it counted every entry in a series rather than only the current ones —
so three corrections on one day looked identical to three actors disagreeing.

The fix was in the implementation, not the vector. That ordering is the rule
(`spec/conformance/README.md` §2), and this is the case that proves it earns its
keep: writing the vector to match the code would have shipped a signal that
fires on every correction a careful worker makes.
