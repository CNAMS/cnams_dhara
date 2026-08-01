# Open questions

Roadmap §12's questions, tracked to resolution, plus the ones that surfaced during
planning. Each has the phase where it must be answered — a question that stays open
past its phase blocks that phase's exit.

**Rule:** when a question is resolved, the answer and its reasoning go into
[decision-log.md](decision-log.md) and an ADR under `docs/adr/`. This file records
only the status, so it stays readable.

| Status | Meaning |
|---|---|
| ❓ open | No answer yet |
| 💭 leaning | A working answer, not yet committed to code |
| ✅ resolved | Answered, implemented, recorded in an ADR |

---

## Q1 — Where does the review queue live? ✅ resolved

> Does the review queue belong in `dhara` (as a first-class "unresolved" state) or
> entirely in the consumer application? — roadmap §12

**Resolved in Phase 1 (WI-1.13):** **`dhara` emits the signal, the consumer owns the
UI.**

Reasoning: "this merge is ambiguous" is a property of the merge, so the engine is the
only thing that can know it. What to *do* about it — who reviews, what the screen
looks like, what an acceptable resolution is — is entirely domain policy, and putting
any of it in `dhara` would violate the dependency rule.

The signal is **part of the join's return value**, not a callback or a side channel.
That matters for Phase 4: a signal delivered out-of-band will be produced at a
different moment by the Dart implementation, and the conformance comparison would
fail for reasons unrelated to merge semantics.

**ADR:** to be written as part of WI-1.13 rung 7.

---

## Q2 — Tombstone retention policy ❓ open

> How long before a deleted record's tombstone can be garbage-collected without
> risking resurrection from a device that has been offline for six months?
> — roadmap §12

**Must be answered by:** Phase 5 (WI-5.5) for the design; the *value* not until
Phase 6.

**The tension:** GC too early and a six-month-offline device resurrects a deleted
record on reconnect (catalogue C-20). GC never, and the tombstone set grows without
bound on a 2GB device — which is a different way of failing the same user.

**Working position, not yet a decision:**
- Retain tombstones for **at least** the revocation validity period (90 days,
  WI-5.3), because a device cannot usefully be offline longer than that anyway — its
  read key has expired and it must sync to continue.
- That coupling is convenient and possibly too convenient. It needs checking against
  real "time since last successful sync" data (secondary metric, §3 of
  [metrics-instrumentation.md](metrics-instrumentation.md)) before it is committed to.

**Instrumentation needed:** store size growth and time-since-last-sync distribution.
Both are already in the Phase 6 secondary metrics list, specifically for this.

**⚠ Do not resolve this from first principles.** The right retention period is an
empirical question about how long devices actually stay offline, and guessing it
produces either resurrection bugs or storage exhaustion in the field.

---

## Q3 — Is the server a full replica? ✅ resolved

> Does the server need to be a full replica, or can it be an authority that applies
> the same joins? — roadmap §12

**Resolved in Phase 2 (WI-2.8):** **full replica.**

Reasoning: it halves the state space. One merge implementation under test rather than
two, one set of invariants, one set of conformance vectors. The roadmap's own leaning
was full replica for simplicity of reasoning; the simulator turns that from a
preference into a concrete saving — a special-cased server would need its own
mutation suite and its own convergence proofs.

**Cost, recorded honestly:** the server carries per-record state it could otherwise
avoid, and server-side storage is the one place in this system where resources are
not scarce. That is the right place to spend.

**ADR:** WI-2.8 rung 5.

---

## Q4 — Photo handling: blob store or in-band chunks? ✅ resolved

> Separate content-addressed blob store, or in-band chunks? — roadmap §12

**Resolved in Phase 3 (WI-3.8):** **content-addressed, out-of-band, referenced by
hash from the record.**

Reasoning: it is what makes catalogue C-18 work. The record's metadata syncs in the
critical lane and is complete and mergeable without the blob; the bytes follow in the
bulk lane. In-band chunks would make a 400 KB image part of a record's delta, which
reintroduces exactly the failure the priority lanes exist to prevent — *a 400 KB
image blocking 2 KB of growth data.*

Secondary benefit: content addressing deduplicates identical images across records
for free.

**Boundary held:** `dhara` never compresses, resizes, or inspects an image. That
requires knowing what the image is *for*. `dhara` moves opaque bytes with a priority.

---

## Q5 — Aadhaar-adjacent identity path ❓ open

> Is an Aadhaar-adjacent identity path required for real ICDS deployment, and does
> that constrain the dedup design? — roadmap §12

**Must be answered by:** Phase 6 — but the answer is an input to the Phase 5 design,
so the question needs asking in **week 1**, alongside WI-0.0.

**Why it might not matter to the design:** the accept-then-reconcile backbone
(WI-5.6) uses an **opaque, schema-declared match key** computed by the consumer. If
ICDS requires an Aadhaar-derived identifier, that becomes one more input to the
consumer's match-key computation. `dhara` does not change.

**Why it might matter anyway:**
- Aadhaar-based verification requires connectivity, which is exactly the part that
  fails (roadmap §6.4). If a workflow *mandates* online verification at registration,
  offline registration may not be permitted at all — which is a policy constraint no
  engineering choice can route around.
- Storing an Aadhaar-derived identifier at rest on a shared field device has legal
  and regulatory implications that feed straight into the Phase 5 threat model.

**Action:** ask this in week 1 as part of the WI-0.0 conversation. The answer
constrains what can be deployed, not what can be built.

---

## Q6 — Version vector granularity 💭 leaning

*(added during planning)*

**Question:** per-replica version vectors, per-record, or a hybrid?

**Must be answered by:** Phase 3 (WI-3.0).

**Leaning:** per-replica vectors, with per-record vectors only for records under
active concurrent edit.

**Reasoning:** a vector per record for 300 beneficiaries × 20 devices is ~6,000
entries to exchange, against a 225 KB best-case window. It does not fit. Per-replica
vectors are compact but coarse — they can indicate a record needs syncing when it does
not, costing a little bandwidth but never correctness.

**⚠ Verify the arithmetic against a real centre's beneficiary count before
committing.** The 300 figure is an assumption, and this decision is entirely
determined by it.

---

## Q7 — Canonical numeric encoding ❓ open

*(added during planning)*

**Question:** how are floating-point measurement values encoded canonically so Python
and Dart produce byte-identical serialisations?

**Must be answered by:** Phase 1 (WI-1.6 rung 5), before the first vector is written.

**Why it is a real question:** Python's `repr(9.2)` and Dart's `9.2.toString()` do not
agree in every case, and canonical serialisation must be byte-identical for delta
computation to work at all — two replicas with the same logical state that serialise
differently will see a spurious difference and resend forever.

**Options:**
- Fixed decimal places per field, declared in the schema. Simple, and matches how
  measurements are actually recorded (weight to 0.1 kg, MUAC to 0.1 cm).
- Decimal string with a specified normalisation.
- Integer minor units — grams, millimetres — with the scale declared in the schema.

**Leaning toward integer minor units.** Floating point in a clinical record is a
liability regardless of the serialisation question, and a schema that declares
`weight` as grams removes an entire class of problem rather than encoding around it.

⚠ This is easy to defer and expensive to change: it affects every conformance vector
written from Phase 1 onward. Decide it before WI-1.15.

---

## Q8 — What counts as a "record" for bytes-per-record? ❓ open

*(added during planning)*

**Question:** M2 is the headline metric proving the delta design earned its
complexity. Is a "synced record" one beneficiary, one field, or one operation?

**Must be answered by:** Phase 3 (WI-3.12), before the baseline is recorded.

**Why it matters:** the three definitions differ by an order of magnitude, and the
number is meaningless without one. It also has to be the definition used for the
full-state baseline, or the comparison is invalid.

**Leaning:** one **beneficiary record converged**, since that is the unit a
supervisor or programme manager thinks in. Report operations-per-record alongside so
the figure can be re-derived under another definition.
