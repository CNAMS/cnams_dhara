# Phase 6 — Field deployment and write-up

**Weeks 21–24 · ~50 hours · ~65 commits**

> Two or three real Anganwadi centres. Instrument everything. — roadmap §8, Phase 6

**Exit criteria (roadmap):** real numbers from real devices on real networks; tagged
`v0.1.0`; published protocol spec; blog post.

---

## What this phase is for

Everything before this is a well-tested library. Roadmap §10 states the risk in the
sharpest available terms: without field deployment, *"this is a well-tested library
with no evidence it survives reality."*

The simulator can tell you the merge semantics are sound. It cannot tell you:

- whether a worker will actually wait through a sync
- what a real 2G window looks like versus the modelled one
- how Android doze, OEM battery killers, and process death interact with a
  background sync
- what the filesystem on a ₹5,000 phone does when the battery dies mid-write
- whether the review queue produces two signals a week or two hundred

**The gap between simulated bandwidth caps and actual 2G behaviour is itself a
finding**, and reporting it honestly is worth more than a larger simulated number.

---

## The access problem, four weeks before it matters

WI-0.0 opened this conversation in **week 1**. By week 21 one of these is true:

| State | Action |
|---|---|
| Access to 2–3 centres confirmed | Proceed with WI-6.2 onward as written. |
| Access uncertain or delayed | Run the fallback **now**, in parallel with continuing to chase access. Do not spend week 21 waiting. |
| Access refused | Run the fallback and say so plainly in the write-up. |

**Fallback (roadmap §10):** a controlled trial with 5 phones and real workers for one
week. It is a weaker claim and it is still a real one, provided it is described
accurately. What it cannot support is any claim about sustained multi-week offline
behaviour, adoption, or review-queue volume at steady state — say that.

⚠ The one thing that must not happen is a write-up that presents simulator numbers in
a way that reads as field numbers. Every figure in the report carries its provenance:
`[sim]`, `[lab]`, or `[field]`.

---

## Work items

### WI-6.0 — Telemetry that works offline `[gate]`

**Why** Every metric in roadmap §9 has to be collected on a device that is offline
most of the time, on a phone with 2GB of RAM, without becoming the thing that fills
the storage or drains the battery.

**Touches** `dhara/metrics.py`, CGMS mobile

**Commit ladder**
1. `feat(metrics): buffer metrics locally with a bounded ring buffer`
2. `feat(metrics): sync metrics in the bulk lane, never the critical lane`
3. `feat(metrics): drop the oldest metrics rather than blocking on a full buffer`
4. `test(metrics): the buffer never exceeds its configured byte budget`
5. `feat(metrics): record session outcome, duration, bytes and lane breakdown`
6. `feat(metrics): record windows-to-drain and retransmission per session`
7. `feat(metrics): record review-signal counts by signal code`
8. `feat(metrics): record crash and restart events`
9. `test(metrics): telemetry never blocks or delays a data-entry path`
10. `feat(metrics): make telemetry collection disableable per deployment`

⚠ Rung 3 is the right trade-off and worth stating: **metrics are the first thing to
lose.** Growth data must never queue behind telemetry any more than it queues behind
a photograph. Rung 2 puts telemetry in the bulk lane for exactly that reason.

⚠ Rung 10 is not a nice-to-have. Field deployment involving children's health data
needs an off switch that a supervisor can reach, and needing one mid-deployment
without having built one is a bad afternoon.

---

### WI-6.1 — Battery and device instrumentation

**Why** Roadmap §9: *"Battery cost per sync session. Field workers will not adopt
something that kills the phone."* This is an adoption metric, not a performance one.

**Touches** CGMS mobile

**Commit ladder**
1. `feat(metrics): sample battery level before and after each sync session`
2. `feat(metrics): record whether the device was charging during a session`
3. `feat(metrics): record available memory at session start`
4. `feat(metrics): record crash-free session rate`
5. `test(metrics): battery sampling itself costs no measurable battery`
6. `feat(metrics): record doze and background-restriction state at session start`

Rung 6 explains outliers you will otherwise be unable to explain. A session that took
four hours to complete because the OEM battery manager killed it is not a sync-engine
finding, but it is indistinguishable from one without this field.

---

### WI-6.2 — Deployment preparation

**Touches** `docs/field-report.md`, deployment scripts

**Commit ladder**
1. `docs: add the field deployment protocol with per-centre setup steps`
2. `docs: add the worker-facing brief in plain language`
3. `docs: add the data handling and consent note for the deployment`
4. `feat(sync): add a deployment build flag with the field configuration` *(CGMS)*
5. `docs: add the rollback procedure if a centre hits a blocking defect`
6. `docs: add the daily check-in checklist for the deployment period`
7. `docs: record baseline measurements taken before the deployment starts`

⚠ Rung 3 is not paperwork. This is children's health data collected through an app
that workers are professionally accountable for. Whatever the institutional
requirement is through EPICS/ICDS, meet it, and write down what was agreed.

⚠ Rung 5 exists because it will be needed. A blocking defect in week 22 with no
rollback path means either a broken centre or a panicked hotfix on a phone in a
village.

⚠ Rung 7 is what makes the headline claim possible. Roadmap §9: *"Sync success rate.
The headline number. **Compare against baseline.**"* Without a before, there is no
comparison, and the number becomes a bare figure with nothing to argue against.

---

### WI-6.3 — Deployment week 1

**Touches** `docs/field-report.md`

**Commit ladder**
1. `docs: record deployment day-1 observations per centre`
2. `fix: address blocking defects found in the first days` *(one commit per defect)*
3. `sim: add a regression scenario for every field defect found`
4. `docs: record daily sync success rates for week 1`
5. `docs: record worker feedback verbatim, before interpretation`

⚠ Rung 3 is the same discipline as WI-4.10: **every field bug the simulator did not
find is a gap in the simulator.** Close it in the same week, while the details are
still fresh. This is also the honest answer to "how do you know your harness models
reality?" — you do not, fully, and this is the mechanism for finding out where.

Rung 5: record what workers said before deciding what it means. The interpretation
can change; the quote should not.

---

### WI-6.4 — Deployment weeks 2–3

**Commit ladder**
1. `docs: record week 2 metrics with per-centre breakdown`
2. `docs: record week 3 metrics with per-centre breakdown`
3. `fix: address non-blocking defects found in the field` *(one per defect)*
4. `sim: extend the network profile using measured real-world window behaviour`
5. `docs: record the gap between the modelled and measured 2G behaviour`
6. `docs: record review-queue volume per 100 records`
7. `docs: record time-to-converge after multi-day offline periods`

⚠ Rung 4/5 are the most interesting technical output of the phase. The simulator's 2G
profile was a guess made in week 7. Measuring what a real window looks like —
duration distribution, throughput, how it dies — and **feeding it back into the
simulator** closes the loop between the model and reality. Then report the delta,
because roadmap §11 names it as one of the honest-tradeoffs items.

Rung 6 is the diagnostic from roadmap §9: too high means the merge rules are too
timid, too low is suspicious. Either way it is a finding about the merge design, not
just an operational statistic.

---

### WI-6.5 — Metrics analysis `[gate]`

**Touches** `docs/field-report.md`

**Commit ladder**
1. `docs: compute sync success rate against the pre-deployment baseline`
2. `docs: compute median and p95 bytes per synced record from field data`
3. `docs: compute time-to-converge after N days offline`
4. `docs: compute windows required to drain a backlog in the field`
5. `docs: compute battery cost per sync session`
6. `docs: compute crash-free session rate on 2GB devices`
7. `docs: compare every field metric against its simulated equivalent`
8. `docs: record where the simulation was optimistic and by how much`
9. `docs: state the sample size and what it does and does not support`

⚠ Rung 8 is the single most credible page in the report. Every reader's first
question about a simulation-heavy project is "but does it hold up in reality?", and
a table with a **Simulated** column, a **Measured** column, and a **Delta** column
answers it before it is asked — including where the answer is unflattering.

⚠ Rung 9 keeps the whole thing defensible. Three centres over three weeks is a small
sample. Stating that plainly, with what it supports and what it does not, is what
separates a credible engineering write-up from an overclaim that collapses under one
question.

---

### WI-6.6 — Honest tradeoffs `[gate]`

**Why** Roadmap §11 names this as *"the strongest credibility asset."*

**Touches** `docs/honest-tradeoffs.md`

**Contents** — the four items the roadmap specifies, plus what execution added:

1. **What the simulator cannot model** — real radio behaviour, Android doze, OEM
   battery killers, filesystem corruption on cheap flash. Plus the concrete blind
   spots found during execution: catalogue C-24 (duplicate device IDs are unreachable
   by construction), and whatever WI-2.17 rung 16 recorded.
2. **Where a Rust core would be genuinely better, and why it was not attempted** —
   one implementation instead of two, no cross-language canonical-serialisation
   problem, better performance on 2GB hardware. Not attempted because FFI debugging
   on Android would have consumed the timeline (roadmap §5.1), and because two
   implementations against a spec produce an interoperability claim a single core
   cannot.
3. **Scenarios where the engine still declines to decide, and why that is correct** —
   delete-versus-update (C-11), duplicate candidates (WI-5.6), ambiguous status
   joins. Each with the argument for why deciding would be worse.
4. **The gap between simulated bandwidth caps and actual 2G behaviour** — with the
   measured numbers from WI-6.4.
5. **The revocation trade-off** — a device offline past the validity period loses
   read access to its own store. What the default is, why, and what the field data
   suggests it should be.
6. **The dedup key's accepted information loss** — two genuinely distinct identical
   readings collapse to one (C-02 vs C-06). Why this is unavoidable and why the
   alternative is worse.

**Commit ladder**
1. `docs: add honest-tradeoffs with what the simulator cannot model`
2. `docs: add the concrete harness blind spots found during execution`
3. `docs: add the rust core assessment and why it was deferred`
4. `docs: add the scenarios where the engine declines to decide`
5. `docs: add the measured gap between simulated and real 2G behaviour`
6. `docs: add the revocation validity-period trade-off with field evidence`
7. `docs: add the dedup key's accepted information loss`
8. `docs: link honest-tradeoffs from the README`

---

### WI-6.7 — Publish the protocol spec `[gate]`

**Touches** `spec/`, `docs/`

**Commit ladder**
1. `spec: review protocol v0.1 against what was actually implemented`
2. `spec: correct every place the implementation diverged from the spec`
3. `spec: add the conformance vector index and how to run the suite`
4. `docs: add a spec reader's guide with a suggested reading order`
5. `docs: publish the merge-semantics rationale as a standalone document`
6. `docs: add the citation block and reference list`

⚠ Rung 2 is the one that requires discipline. Six months of implementation always
leaves places where the code is right and the spec was never updated. Publishing a
spec that does not match the implementation is worse than publishing no spec,
because the conformance vectors then encode behaviour the document contradicts.

---

### WI-6.8 — Write-up `[gate]`

**Why** Roadmap §11 gives the positioning. This WI executes it.

**Touches** `docs/`, blog post

**The framing, verbatim from the roadmap:**

> **Do not say:** "I built a sync engine."
>
> **Do say:** "Generic sync engines default to last-write-wins or hand conflict
> resolution to your API. That is wrong for longitudinal health records — a child's
> weight is an event, not a mutable field. I built the resolution layer for that
> domain and verified it with deterministic simulation testing: a million randomised
> schedules of partitions, clock skew, and mid-write crashes, all asserting
> convergence and no measurement loss."

**Commit ladder**
1. `docs: draft the write-up opening with the problem, not the technology`
2. `docs: add the prior-art section stating what was not built`
3. `docs: add the merge-semantics argument with the worked example`
4. `docs: add the simulation testing section with the deliberate-bug experiment`
5. `docs: add the field results with baseline comparison`
6. `docs: add the honest-tradeoffs section`
7. `docs: add the what-next section with the v0.2 candidates`
8. `docs: revise for length - cut anything that is not evidence or argument`
9. `docs: add the final write-up to the repository`

⚠ Rung 2 is what makes the whole piece land. Stating plainly that Automerge, Yjs,
PowerSync, and ElectricSQL exist and are production-ready, **before** describing what
was built, is what makes the contribution claim credible. A write-up that omits prior
art reads as naive to anyone who knows the space (roadmap §3), and this space has a
lot of people who know it.

⚠ Rung 4 leads with the deliberate-bug experiment, not the million schedules. The big
number is impressive; the experiment is what makes the big number *mean* something.

---

### WI-6.9 — Release `v0.1.0` `[gate]`

**Commit ladder**
1. `docs: finalise the README with field results and the headline metrics`
2. `docs: add the changelog entry for v0.1.0`
3. `docs: add release notes with the metrics table and known limitations`
4. `chore: tag v0.1.0`
5. `docs(plan): record phase 6 exit checklist results`
6. `docs(plan): record what slipped, what was cut, and what v0.2 should address`

---

### WI-6.10 — v0.2 candidates `[research]`

**Why** Close the project deliberately rather than trailing off.

**Touches** `docs/roadmap-v0.2.md`

**Candidates, from the roadmap's own deferrals:**
- Rust core with FFI bindings, if systems credibility becomes the goal (§5.1)
- Tombstone garbage collection with a retention policy grounded in field data (Q2)
- Bloom filter pre-push, if it was cut from Phase 5
- Peer-to-peer device↔device sync — still a non-goal, but the field data may argue
  otherwise
- Whatever the review-queue volume data says about the merge rules being too timid or
  too aggressive

**Commit ladder**
1. `docs: add the v0.2 candidate list with evidence from the field deployment`
2. `docs: record which non-goals the field data challenged`
3. `docs: state what would need to be true to justify the rust core`

---

## Exit checklist

- [ ] **Real numbers from real devices on real networks**, each tagged `[sim]`,
      `[lab]`, or `[field]`.
- [ ] Deployment at 2–3 centres, **or** the documented fallback with its limits
      stated plainly.
- [ ] Pre-deployment baseline recorded, so the sync success rate is a comparison.
- [ ] All seven roadmap §9 metrics collected: sync success rate, bytes per record
      (median/p95), time-to-converge after N days offline, windows to drain a
      backlog, review-queue volume per 100 records, battery per session, crash-free
      session rate on 2GB devices.
- [ ] Every field metric compared against its simulated equivalent, **including where
      the simulation was optimistic**.
- [ ] Every field defect has a simulator regression scenario.
- [ ] The 2G network profile updated from measured behaviour, and the delta reported.
- [ ] `docs/honest-tradeoffs.md` complete, covering all six items.
- [ ] Protocol spec reviewed against the implementation and corrected.
- [ ] Write-up leads with the problem and states prior art before the contribution.
- [ ] Sample size and its limits stated explicitly.
- [ ] `v0.1.0` tagged; release notes include the metrics table and known limitations.
- [ ] v0.2 candidates recorded with the evidence behind each.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| **No field access** | Week 21 with no confirmed centre | Run the fallback immediately and in parallel. A described 5-phone trial beats a delayed deployment that never happens. |
| Simulator numbers presented as field numbers | Any figure without a provenance tag | Tag every number. This is the failure that would undermine the whole project's credibility. |
| Telemetry competes with growth data | Sync sessions dominated by metrics payloads | Bulk lane, bounded buffer, drop-oldest (WI-6.0). |
| A blocking defect strands a centre | A centre unable to record for a day | Rollback procedure (WI-6.2 rung 5), prepared before deployment. |
| Field bugs not fed back to the simulator | Field defect fixed with no new scenario | WI-6.3 rung 3. Every uncaught field bug is a harness gap. |
| Write-up overclaims | "Proven correct", "guaranteed no data loss" | The claim is: a million-schedule search found no counterexample, and here is proof the search can find one. That is stronger *because* it is bounded. |
| Sample size oversold | Conclusions about adoption from three weeks at three centres | WI-6.5 rung 9. State what the sample supports. |
| Project trails off | Week 24 with no tag | WI-6.9 is short by design. Tag it, write the notes, close it. |
