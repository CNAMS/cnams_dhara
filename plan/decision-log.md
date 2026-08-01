# Decision log

Append-only. Newest first. One entry per decision that would be expensive to
rediscover.

**What goes here:** the reasoning. **What goes in an ADR:** the same decision, written
for a reader who was not there. Substantial decisions get both — this log is the
running record, `docs/adr/` is the durable artifact.

**What does not go here:** anything the code, the commit history, or the phase files
already record.

---

### Template

```markdown
## YYYY-MM-DD — <decision, stated as an outcome>

**Context**      What forced the decision.
**Options**      What was considered, briefly.
**Decision**     What was chosen.
**Reasoning**    Why. Include the thing that tipped it.
**Cost**         What this decision gives up. Every real decision has one.
**Revisit if**   The observation that would justify reopening this.
**Refs**         WI-N.M, ADR-NNNN, seeds, catalogue entries.
```

The **Cost** and **Revisit if** fields are the ones with value in month five. A log
entry with no cost recorded is usually a decision that was not actually examined.

---

## 2026-08-01 — Execution plan structured as work items with commit ladders

**Context** The roadmap specifies 24 weeks across 7 phases at the level of "build the
simulator". That is a plan for deciding what to do, not for doing it. Sessions are
2–4 hours, often at the end of a day, and the cost of re-deriving "what exactly am I
building right now" at the start of each one is the thing most likely to stall the
project.

**Options**
- Issue tracker with tickets — better for collaboration, worse for a sole author, and
  the reasoning does not live next to the code.
- Freeform per-phase notes — lowest friction, but no mechanism that forces
  decomposition before implementation.
- Work items with explicit commit ladders — highest up-front cost.

**Decision** Work items with commit ladders, in `plan/`, versioned with the code.

**Reasoning** The ladder is the forcing function. If a work item's commits cannot be
written down in advance, the work item is not understood yet — and that is a signal
worth having *before* a session starts rather than an hour into it. The secondary
benefit is that the history becomes a legible record of how the correctness argument
was constructed, which for this project is part of the artifact rather than a
by-product.

**Cost** The plan will be wrong in places, and maintaining it against reality is real
overhead. Ladders will be re-written mid-phase. Accepted: a stale ladder still
decomposes the work better than no ladder.

**Revisit if** Two consecutive phases where the ladders bore no resemblance to what
was actually committed. That would mean the decomposition is happening at the wrong
granularity.

**Refs** EXECUTION.md, plan/00-overview.md

---

## 2026-08-01 — Repository hosted at `CNAMS/cnams_dhara`

**Context** Roadmap §4 recommends a personal-account repository, on the grounds that
org-hosted repos invite "which parts were yours?" in an interview. The repository
already exists under the CNAMS org.

**Decision** Keep `CNAMS/cnams_dhara`.

**Reasoning** The roadmap's concern is about attribution ambiguity, and that is
addressable without moving the repository: sole authorship is visible in the commit
history, and the write-up states scope explicitly. Moving a repository that already
exists costs more than it saves.

**Cost** The attribution question may still come up, and the answer is a sentence
rather than self-evident from the URL. The org prefix also appears in the clone URL,
which is mildly at odds with the generality pitch.

**Mitigation** The prefix stops at the repository name. Package names, import paths,
module names, wire fields, and spec documents all use `dhara` with no org prefix and
no domain vocabulary — the property that actually matters is that the artifact can be
described without mentioning CGMS, and that is unaffected.

**Revisit if** The repository is used as an outreach artifact and the attribution
question is raised more than once.

**Refs** plan/repo-layout.md §4

---

## 2026-08-01 — Fine-grained commits are a deliverable, not a side effect

**Context** ~640 commits across 24 weeks is roughly 25 per week. That is a deliberate
target rather than an emergent property.

**Decision** Commit at every rung. Never squash a ladder before pushing.

**Reasoning** Three reasons, in increasing order of importance:
1. `git bisect` is only useful at this granularity, and the bugs this project expects
   are exactly the kind that get found in Phase 3 but were introduced in Phase 1.
2. Resuming a half-finished work item never requires reconstructing where you were.
3. The history is a record of how a correctness argument was built. For a project
   whose central claim is "verified, not asserted", `git log --grep="Seed:"`
   eventually being a list of every bug the simulator caught is direct evidence for
   that claim.

**Cost** More commits means more commit messages, and a bad commit message at 11 PM
is worse than no commit. The ladders in the phase files mitigate this by writing the
messages in advance.

**Revisit if** Commit messages start degrading to "wip" and "fix" in bulk. That is a
sign the granularity has become ceremony rather than decomposition.

**Refs** plan/commit-conventions.md

---

## 2026-08-01 — Six mutations in the deliberate-bug experiment, not one

**Context** Roadmap §7.1 specifies one injected bug — swap a series append for an
overwrite — and calls the experiment *"the single most credible artifact in the
repo."*

**Decision** Six mutations (M1–M6), each with a recorded seeds-to-detection figure,
run nightly rather than once.

**Reasoning** One caught bug demonstrates the harness can catch *that* bug. Six across
different subsystems — series, register, clock, set, dedup, operation identity —
demonstrate it can catch a *class* of bug. The seeds-to-detection figures then do
double duty: they are the calibration signal for whether the scenario generator is
producing enough concurrency, which is otherwise invisible. If M1 is not caught within
50 seeds, the generator is too gentle, and no test would have said so.

Running nightly rather than once addresses a failure mode the roadmap does not
mention: harness sensitivity **decays**. A refactor that makes the generator less
adversarial fails nothing — except this suite.

**Cost** Six mutations is roughly a session and a half more than one, and the nightly
run adds CI time.

**Revisit if** Any mutation's detection time regresses from its Phase 2 baseline.

**Refs** WI-2.17, R8

---

## 2026-08-01 — Every number carries a provenance tag

**Context** This project's credibility rests on a clear line between what was
simulated and what was measured. That line is lost by accident, not by intent — a
simulated figure drifts into a README, then a slide, then a conversation.

**Decision** Every figure in any document, commit body, or presentation carries
`[sim]`, `[lab]`, or `[field]`. A number without a tag is a defect.

**Reasoning** Free if habitual from Phase 2, expensive to retrofit in week 24 when
the write-up is being assembled from six months of notes. It also makes the Phase 6
comparison table — simulated versus measured, including where the simulation was
optimistic — structural rather than an act of unusual honesty at the end.

**Cost** Mild verbosity in prose.

**Refs** plan/metrics-instrumentation.md §1, R11

---

## 2026-08-01 — Phases 0–2 are treated as a hard floor

**Context** Roadmap §10 states phases 0–2 are the irreducible core and phases 5–6 can
slip a semester. Under exam pressure the tempting move is to start the next phase
while the current one is 80% done, because the next one is more interesting.

**Decision** Do not start phase N+1 with phase N's exit checklist unticked. If week 9
arrives with Phase 2 incomplete, finish Phase 2.

**Reasoning** A verified merge layer with no network layer is a real contribution and
a coherent artifact. A half-verified merge layer with a half-written network layer is
the fourth 70%-complete repository the roadmap warns about in §2. The failure mode is
not slipping — it is producing two incomplete phases instead of one complete one.

**Cost** Some phases will be cut in scope rather than run long, and stretch work
items will be dropped.

**Refs** EXECUTION.md, R6
