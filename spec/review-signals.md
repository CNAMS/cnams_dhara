# Review signals

**Status:** Phase 1 · **Signals:** 11 · **Source:** [conflict-catalogue.md](conflict-catalogue.md)

The registry of every signal `dhara` can emit, with what it means and what a
consumer is expected to do about it.

---

## What a signal is, and is not

A signal says: **"I merged this deterministically, and a human should look."**

It does *not* say the merge failed, and it never blocks a sync. Roadmap §6.2's
last row — *genuinely ambiguous → surface to supervisor review queue* — is a
designed outcome. **A sync engine that admits it does not know is more
trustworthy than one that silently guesses.**

Open question Q1 is settled: **`dhara` emits the signal, the consumer owns the
UI.** Whether a merge is ambiguous is a property of the merge, so the engine is
the only thing that can know it. Who reviews, what the screen shows, and what
counts as a resolution are domain policy, and putting any of that here would
violate the dependency rule.

### Signals are derived from merged state

Not accumulated during the join. This is the load-bearing decision in the
design, and it buys two things:

1. `join` stays pure algebra, so the lattice laws are about state and nothing
   else.
2. **Determinism becomes a corollary of convergence.** If replicas converge on
   state — which the laws guarantee — anything computed from that state is
   identical on every replica, in every merge order. Phase 2's
   `review_signals_are_deterministic` invariant is then true by construction
   rather than by a separate argument.

⚠ The alternative makes signals a function of the *path* rather than the
destination: two replicas reaching the same state by different merge orders
would emit different signals, and the Phase 4 conformance comparison would fail
for reasons that have nothing to do with merge semantics.

### The set is closed

Adding a code requires a catalogue entry that needs it. A signal with no defined
meaning is worse than no signal, because a supervisor cannot act on it. The
enum is enforced in three places: `SIGNAL_CODES` in `dhara/review.py`, the
`reviewSignal` definition in `conformance/schema.json`, and a test that the two
agree with this document.

---

## Registry

| Code | Catalogue | Emitted when | Consumer should |
|---|---|---|---|
| `multiple_weights_same_day` | C-01 | Two or more entries in one measurement field share a calendar day | Show both with their authors and times. Two readings on one day is clinically meaningful, not an error. |
| `superseded_fork` | C-03 | Two entries both claim to supersede the same entry | Show the fork. "Current" is ambiguous until a human picks. |
| `implausible_taken_at` | C-05 | An entry's `taken_at` exceeds a schema-declared bound relative to causal receive time | Offer a correction **as a new operation**. Never rewrite the original. |
| `concurrent_demographic_edit` | C-08, C-12, C-19 | A register holds observations from more than one author, neither causally after the other | Show every value with its author. The loser is retained; a human picks. |
| `reenrolment_after_graduation` | C-09 | A status transition was attempted away from a terminal state | Tell the worker what to do instead — the model requires an explicit new record. |
| `concurrent_status_transition` | C-10 | Two status operands are on incomparable branches | Show both. The join is deterministic; the disagreement is the finding. |
| `delete_update_conflict` | C-11 | A record is tombstoned and carries a concurrent field update | **High priority.** Confirm the deletion or restore. Most likely to be a real mistake by a real person. |
| `duplicate_candidate` | C-13 | Two records collide on the schema-declared match key | **Never auto-merged.** A human confirms. Merging two records that are not the same subject corrupts both, unrecoverably. |
| `stale_replica_beyond_retention` | C-20 | A replica arrives with state older than the tombstone retention window | Operational alert. Fail loudly rather than silently resurrect deleted data. |
| `replica_state_regressed` | C-23 | A device's version vector is strictly dominated by the server's record of it | Operational alert — usually a backup restore. Genuinely unsynced work is still applied. |
| `duplicate_device_id` | C-24 | Enrolment requests an id already bound to a live device key | **Refuse enrolment.** Quarantine both histories if detected after the fact. |

---

## Phase availability

Six signals are emitted by the Phase 1 merge layer. The rest need machinery that
does not exist yet, and the registry records that rather than leaving a consumer
to discover it.

| Phase | Signals |
|---|---|
| **1** (merge) | `multiple_weights_same_day`, `superseded_fork`, `concurrent_demographic_edit`, `concurrent_status_transition` |
| **1** (declared, not yet emitted) | `implausible_taken_at` — needs the schema-declared plausibility bound; `reenrolment_after_graduation` — needs the consumer's terminal-state declaration |
| **3** (session) | `stale_replica_beyond_retention`, `replica_state_regressed` |
| **5** (identity) | `delete_update_conflict`, `duplicate_candidate`, `duplicate_device_id` |

---

## Wire format

```json
{ "code": "concurrent_demographic_edit", "fields": ["d_a"] }
```

| Key | |
|---|---|
| `code` | From the closed set above |
| `fields` | Field names the signal concerns. Neutral ids, never domain vocabulary. |

Evidence — the competing values and their authors — is carried in memory for a
consumer to render, and is **normalised (sorted) at construction**. It is built
from sets whose iteration order is not part of their value, and unsorted
evidence would make two replicas with identical state emit signals that compare
unequal.

In conformance vectors, signals are compared **as a set**: signal *order* is not
part of the contract, signal *content* is. An empty `expected_signals` array is
a real assertion — a clean merge emitting a spurious signal is a defect (C-04,
C-07).

---

## Volume is a metric, not just an output

Roadmap §9: *"Review-queue volume per 100 records. Too high = merge rules too
timid. Too low = suspicious."*

It is the only metric that is diagnostic in **both** directions, which makes it
a measurement of the merge design rather than of the system's performance.
Interpretation bands are fixed in advance, in
[plan/metrics-instrumentation.md](../plan/metrics-instrumentation.md) §M5, so
the Phase 6 result cannot be rationalised after the fact.

⚠ This is why `Field.review_when_contested` exists. A field where concurrent
edits are routine and harmless should set it false. A queue supervisors stop
reading is worse than no queue at all.
