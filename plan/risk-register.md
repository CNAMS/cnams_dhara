# Risk register

Live document. Roadmap §10 states the risks; this file tracks them, adds the ones
that only appear during execution, and — critically — gives each one a **trigger**:
an observable condition that says the risk has materialised and the mitigation must
start now, rather than a judgement call made too late.

**Review cadence:** at every phase exit, and any time a trigger fires.

| Status | Meaning |
|---|---|
| 🟢 open | Identified, mitigated, not currently materialising |
| 🟡 watch | A trigger is close or partially met |
| 🔴 active | Trigger met; mitigation in progress |
| ⚫ closed | No longer applicable, with the reason recorded |

---

## R1 — No field deployment access

**Severity: High** · **Status: 🟡 watch** · **Owner: Pranav**

> Without it this is a well-tested library with no evidence it survives reality.
> — roadmap §10

**Why it is watch, not open, from day one:** the mitigation has a lead time measured
in weeks and is entirely outside your control. It is the only risk in this register
that can be lost by doing nothing, silently, for twenty weeks.

**Trigger** No confirmed centre by **week 12**.

**Mitigation**
- Start the EPICS/ICDS conversation in **week 1**, not week 20. This is WI-0.0, the
  first work item in the plan.
- Escalate at week 6 if there has been no reply.
- At week 12, commit to the fallback and stop waiting: a controlled trial with 5
  phones and real workers for one week.

**If it materialises** Run the fallback and describe it accurately. A 5-phone
one-week trial, honestly reported, is a real result. What it cannot support is any
claim about sustained multi-week offline behaviour, adoption, or steady-state
review-queue volume — and the write-up says so.

**Review** Weeks 6, 12, 18, 21.

---

## R2 — Scope creep into building the whole app

**Severity: High** · **Status: 🟢 open**

**Trigger** Any commit in this repository that names a domain concept, or any week
where more than half the hours went to CGMS features rather than `dhara`.

**Mitigation**
- The non-goals list in roadmap §2 is binding. CGMS is the demo, not the deliverable.
- Mechanical enforcement: `check_no_domain_imports.py` (WI-1.0) fails the build.
- The two `schema_binding` files are the only place domain knowledge lives, and both
  are in the CGMS repository.

**If it materialises** Move the code to the CGMS repo. If it cannot be expressed
there, that is the signal the schema descriptor needs extending — which is a `dhara`
change with no domain vocabulary in it.

---

## R3 — Rust rewrite temptation

**Severity: Medium** · **Status: 🟢 open**

**Trigger** Any `spike/rust*` branch, or any week spent on FFI.

**Mitigation** Defer to v0.2. Two implementations plus conformance vectors is already
a strong story — arguably stronger, because it produces an interoperability claim a
single core cannot.

**If it materialises** The assessment goes in `docs/honest-tradeoffs.md` (WI-6.6
item 2), where "where a Rust core would be genuinely better and why it was not
attempted" is already a required section. Writing that section is the productive
version of the temptation.

---

## R4 — The simulator becomes a project of its own

**Severity: Medium** · **Status: 🟢 open**

**Trigger** Week 9 arrives with the million-schedule sweep unrun.

**Mitigation** Timebox Phase 2 to 4 weeks. It only needs the six fault classes in
roadmap §7.1: partitions, loss/reorder/dup, clock skew and jumps, crashes mid-write
and mid-sync, bandwidth caps, abrupt window closure. Four invariants. One runner.

**⚠ The specific failure shape** is not "the simulator is too small" — it is a
plugin architecture, a scenario DSL, or a visualisation UI. None of those find bugs.

**If it materialises** Freeze the simulator's feature set, run the sweep, move on.

---

## R5 — Protocol churn breaks CGMS repeatedly

**Severity: Medium** · **Status: 🟢 open**

**Trigger** More than one tag bump per week after week 14, or any CGMS build broken
by a `dhara` change for more than a day.

**Mitigation**
- Path dependencies until week 14, then pinned tags.
- Protocol frozen at Phase 3 exit (WI-3.14) before CGMS depends on a tag.
- Post-freeze changes go through a documented process and ship a migration note.

**If it materialises** Stop bumping. Batch protocol changes into one version bump
with one migration note.

---

## R6 — Exams and semester load

**Severity: High** · **Status: 🟢 open**

**Trigger** Two consecutive weeks under 6 hours.

**Mitigation** Phases 0–2 are the irreducible core. Phases 5–6 can slip a semester
without invalidating the work.

**If it materialises**
1. Finish the phase in progress. Do not start the next one.
2. If mid-Phase 2, cut scenario variety before cutting the mutation experiment — the
   experiment is the phase's value.
3. If in Phase 5+, tag `v0.1.0-rc`, write up what exists, and resume next semester.
   The artifact is coherent at that point.

**⚠ The failure mode to avoid** is not slipping. It is starting Phase 3 with Phase 2
unfinished, which produces two half-done phases instead of one complete one.

---

## R7 — Two-repo friction

**Severity: Low** · **Status: 🟢 open** · *(added during planning)*

**Trigger** Any change requiring simultaneous edits in both repos more than twice in
one week.

**Mitigation** Land the `dhara` change first, then the CGMS side with the `dhara`
commit SHA in the commit body. That is the cheap substitute for atomic cross-repo
commits and it is sufficient.

**If it materialises** Usually a sign the schema descriptor is not expressive enough.
Fix the descriptor, not the process.

---

## R8 — Harness sensitivity decays

**Severity: Medium** · **Status: 🟢 open** · *(added during planning)*

**Why this is not in the roadmap:** it only becomes visible during execution. The
simulator's ability to find bugs depends on the scenario generator producing enough
concurrency, and any refactor can quietly reduce that **without failing a single
test.** A harness that has stopped testing anything looks exactly like a harness that
is finding no bugs because there are none.

**Trigger** Any mutation from WI-2.17 taking longer to detect than its Phase 2
baseline.

**Mitigation**
- The mutation suite runs nightly (WI-2.17 rung 17), not once.
- Seeds-to-detection is recorded per mutation, so regression is measurable rather
  than felt.
- Re-run after every structural change to the simulator — in particular after Phase 3
  replaces direct state exchange with real sessions (WI-3.11 rung 7), and after
  Phase 5 adds crypto to the hot path (WI-5.10 rung 4).

**If it materialises** Fix the generator, not the invariant. Bias harder toward
concurrent edits on a small record space.

---

## R9 — Two implementations converge by transliteration

**Severity: Medium** · **Status: 🟢 open** · *(added during planning)*

**Why it matters:** the entire justification for two implementations (roadmap §5.1)
is that they produce an interoperability story rather than a "trust me, it's the same
code" story. If the Dart port is written with the Python source open beside it, that
justification evaporates and the conformance suite becomes theatre — it will confirm
that the same misunderstanding was typed twice.

**Trigger** Phase 4 completes with **zero** spec ambiguities logged.

**Mitigation** Implement Dart from the spec and its vectors. Consult Python only when
a vector fails and the spec is genuinely ambiguous — and when that happens, **fix the
spec**. Log each one (WI-4.11 rung 2).

**If it materialises** The list of logged ambiguities being empty is the diagnosis.
Pick the three subtlest behaviours — delta of an LWW register's history, ORSet remove
tags, canonical numeric encoding — and check the spec alone actually determines them.

---

## R10 — Security layer causes the data loss it exists to prevent

**Severity: High** · **Status: 🟢 open** · *(added during planning)*

**Why it matters:** the revocation design (WI-5.3) makes the local store unreadable
after a validity period expires without a sync. A worker offline for longer than that
period is exactly the user this project exists to serve. If the outbox is encrypted
under the expiring key, the security layer destroys precisely the data that never
reached the server — a worse outcome than having no security layer at all.

**Trigger** Any design or code path where unsynced operations are unreadable after
read-key expiry.

**Mitigation**
- The outbox is held under a separate key that never expires (WI-5.3 rungs 5–6).
- The validity period defaults to **90 days**, tuned with field data, not guessed
  tighter for a cleaner security story.
- The worker is warned with enough lead time to reach a network (rungs 10–11).

**If it materialises** This is a stop-everything defect, not a bug to schedule.

---

## R11 — Numbers lose their provenance

**Severity: Medium** · **Status: 🟢 open** · *(added during planning)*

**Why it matters:** this project's credibility rests on a clear line between what was
simulated and what was measured. A simulated figure that drifts into a README, a
slide, or a conversation without its tag is the single fastest way to lose that
credibility — and it happens by accident, not by intent.

**Trigger** Any figure appearing without a `[sim]` / `[lab]` / `[field]` tag.

**Mitigation** Tag every number from Phase 2 onward, in commit bodies and documents
alike. The Phase 6 comparison table (WI-6.5) makes the distinction structural.

**If it materialises** Audit the README and the write-up before publishing. This one
is cheap to fix while the project is private and expensive afterwards.

---

## Closed risks

*(none yet — entries move here with the phase and reason they closed)*
