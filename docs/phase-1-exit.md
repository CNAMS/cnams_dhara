# Phase 1 exit review — clocks and lattices

**Measured:** at commit 82, Python 3.12.4, macOS · **Result:** criteria met, tag withheld

---

## Exit criteria

From [plan/phase-1-clocks-and-lattices.md](../plan/phase-1-clocks-and-lattices.md).

| # | Criterion | Result |
|---|---|---|
| 1 | Property tests green over **10,000 randomised operation orders per lattice** — commutativity, associativity, idempotence — for all five types | ✅ 10,000 examples per type, 84 s, green |
| 2 | HLC ordering correct under **±3 days of simulated skew**, logical counter provably bounded | ✅ 6 properties, 400 examples each |
| 3 | `merge-semantics.md` complete, with rationale and alternatives per lattice | ✅ |
| 4 | Every catalogue entry expressible without session/identity/crypto machinery has a vector; the rest annotated with their phase | ✅ 12 merge + 6 HLC vectors; 8 entries annotated |
| 5 | The conformance runner applies **all permutations** of replica order | ✅ all `n!`, capped at 5 replicas |
| 6 | `join` never reduces the observable value set, asserted as a property | ✅ four of five lattices; `StatusLattice` exempt, see below |
| 7 | Canonical serialisation stable under insertion order | ✅ asserted per type |
| 8 | Domain-token checker green; no domain vocabulary in `dhara/` | ✅ |
| 9 | No wall-clock read anywhere in `dhara/` | ✅ physical time is injected |
| 10 | Review signals are part of the join return value, not a side channel | ✅ **derived from merged state** — see divergence below |

**138 tests green.** Push budget 12 s, gate budget 84 s.

---

## Two deliberate divergences from the plan

Both are improvements on what the plan specified, and both are recorded rather
than quietly absorbed.

### Signals are derived from state, not returned by `join`

The plan (WI-1.13 rung 6) said *"make signals part of the join result, not a side
channel"*, to stop them being a callback whose firing order differs between
implementations.

The implementation goes further: signals are computed **from the merged state**
by `dhara.review`, so `join` returns only the lattice value.

Same guarantee, stronger derivation. Signal determinism stops being a property
that needs its own proof and becomes a **corollary of convergence** — if replicas
converge on state, anything computed from that state is identical everywhere, in
every merge order. Phase 2's `review_signals_are_deterministic` invariant
(WI-2.12 rung 4) is then true by construction.

### `StatusLattice` is exempt from the no-loss property

Criterion 6 says `join` never reduces the observable value set. Four lattices
satisfy it. `StatusLattice` does not, and should not: its state is a **position
in a declared order**, not a set of observations. Joining `s0` and `s1` yields
`s1`, and `s0` is gone from the state.

That is not data loss — the transition history lives in the operation log, which
is where "who moved this and when" is answered from. Retaining prior positions
in the state would either break idempotence or make the state unbounded, and
would duplicate the oplog.

The exemption is written as its own passing test, not as an omission, so a future
reader finding no no-loss check there knows it was a decision.

---

## What the checking actually caught

Three methods, and they caught different things — which is the argument for
having three.

| Method | Caught |
|---|---|
| **Property tests** | `canonical()` crashed sorting mixed value types. A register legitimately holds `None`, a string and an integer across its history (C-12), and `None < str` raises in Python and would order differently in Dart. Fixed with a type-tagged scalar encoding. |
| **Conformance vectors** | C-03's expected block, written from the catalogue, disagreed with the implementation: the same-day signal counted every entry in a series, so a correction chain looked like three actors disagreeing. Fixed in the **implementation**, per `conformance/README.md` §2. |
| **Mutation calibration** | Signal evidence was built from frozenset iteration order, so two merge orders produced signals that compared unequal despite identical state. Normalised at construction. |

### The gap mutation calibration found that nothing else did

Mutation M4 — keying an OR-Set remove on the element instead of on observed tags
— **passed the entire property suite untouched.**

The law strategies build OR-Set values with the constructor and never call
`remove()`, so the mutated code path was never executed. **Laws over constructed
values prove the algebra and say nothing about whether the operations that
produce those values are right.**

`tests/unit/test_or_set_semantics.py` closes it; M4 is now caught by two tests.

⚠ This is the Phase 2 lesson arriving three weeks early, and it should shape
WI-2.9: a scenario generator that produces states directly rather than by
driving operations will have the same blind spot at a much larger scale.

### Mutation results

| Mutation | Caught by |
|---|---|
| HLC tie-break drops `node_id` (M3) | 3 tests |
| HLC receive remote-ahead branch wrong | 3 tests |
| HLC send drops `max`, clock can regress | 4 tests |
| Series join overwrites instead of appending (M1) | 3 tests |
| LWW register discards the loser (M2) | 2 tests |
| OR-Set remove keys on element (M4) | 2 tests *(0 before the semantics tests)* |
| Cross-field rule in `Record.join` | 3 tests |
| Signal evidence not normalised | 1 test |

---

## Why the tag is withheld

`phase-1-complete` is **not** tagged, for two reasons that are not about Phase 1.

1. **Phase 0 never exited.** WI-0.0 — the field-access conversation — has not
   happened. It is the mitigation for R1, the highest-severity risk, and it has
   a lead time nobody here controls. → [LEFTOVER.md](../LEFTOVER.md) §1
2. **CI has never run.** The workflows are committed and no runner has executed
   them. `uv`, ruff, mypy strict and the coverage gate are all unverified;
   everything above was measured through a plain venv and pytest.
   → [DOUBTS.md D-10](../DOUBTS.md#d-10)

Tagging a phase complete while its predecessor's checklist has unticked boxes
would make the tags mean nothing, which defeats the point of having them.

---

## Open doubts this phase rested on

| Doubt | Now |
|---|---|
| [D-02](../DOUBTS.md#d-02) `keep_losers` unconditional | **Committed to.** No flag exists; retention is set union. Reversing costs the register, the delta, the wire format and both implementations. |
| [D-03](../DOUBTS.md#d-03) `supersedes` chains | **Committed to.** Implemented because the catalogue specifies it. Still the one place the roadmap's data model was extended. |
| [D-04](../DOUBTS.md#d-04) integer minor units | **Committed to.** Twelve vectors now encode it. This was the cheap moment; it has passed. |
| [D-05](../DOUBTS.md#d-05) `recorded_by` is a worker id | **Committed to.** It is in the dedup key and in twelve vectors. |

⚠ All four moved from "assumed" to "committed to" during this phase. Reversing
any of them is now a spec change plus a vector rewrite, not an edit.
