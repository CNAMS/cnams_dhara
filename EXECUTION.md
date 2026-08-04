# dhara — Execution Plan

**Source document:** [dhara-sync-engine-roadmap.md](dhara-sync-engine-roadmap.md)
**Owner:** Pranav Shukla
**Budget:** ~12–15 hours/week alongside coursework, 24 weeks
**Status:** Phase 0 not started

---

## What this document is

The roadmap says *what* to build and *why*. This plan says *what to do on Tuesday*.

Every phase below is broken into **work items (WI)**, and every work item is broken
into an ordered **commit ladder** — the actual sequence of commits, each one a thing
that compiles and can be explained in a sentence. The commit messages are written
out in the phase files. You are not expected to improvise them at 11 PM.

The plan targets roughly **600 commits** across 24 weeks. That is ~25/week, ~2 per
working hour. This is deliberate and it is not padding:

- A commit ladder is a decomposition. If you cannot write the ladder, you do not yet
  understand the work item, and that is the signal to stop and think rather than
  start typing.
- Small commits are what make `git bisect` useful when the simulator finds a
  convergence violation in Phase 3 that was actually introduced in Phase 1.
- The history is a legible record of how a correctness argument was constructed. For
  this project specifically, that record is part of the artifact.

See [plan/commit-conventions.md](plan/commit-conventions.md) for format and rules.

---

## Phase map

| Phase | Weeks | Title | Commits (est.) | Gate |
|---|---|---|---|---|
| [0](plan/phase-0-catalogue-and-spec.md) | 1–2 | Conflict catalogue and spec | ~60 | Every scenario has a stated desired outcome, no hand-waving |
| [1](plan/phase-1-clocks-and-lattices.md) | 3–5 | Clocks and lattices | ~95 | Algebraic laws green ×10,000; HLC correct under ±3 days skew |
| [2](plan/phase-2-simulator.md) | 6–9 | The simulator | ~115 | 1,000,000 schedules converge; deliberate-bug experiment finds injected fault <1,000 seeds |
| [3](plan/phase-3-delta-sync.md) | 10–13 | Delta sync and session protocol | ~120 | Six months of backlog drains over 90s/20kbps windows, zero loss, zero dup |
| [4](plan/phase-4-dart-and-integration.md) | 14–16 | Dart client and CGMS integration | ~90 | Two physical phones, airplane mode, correct merge on reconnect |
| [5](plan/phase-5-security-and-identity.md) | 17–20 | Security and identity | ~95 | Revoked device unreadable without coming online; duplicate registration reconciled |
| [6](plan/phase-6-field-and-writeup.md) | 21–24 | Field deployment and write-up | ~65 | Real numbers, real devices, real networks; `v0.1.0` tagged |

**Total: ~640 commits.**

---

## The irreducible core

From roadmap §10: *"Phases 0–2 are the irreducible core. Phases 5–6 can slip a
semester without invalidating the work."*

Treat this as binding, because it is what you fall back to when exams hit.

```
       MUST SHIP              SHOULD SHIP           CAN SLIP
   ┌────────────────┐     ┌────────────────┐    ┌────────────────┐
   │  Phase 0  spec │ ──▶ │  Phase 3 delta │──▶ │ Phase 5 security│
   │  Phase 1 lattice│     │  Phase 4 Dart  │    │ Phase 6 field   │
   │  Phase 2   sim │     │                │    │                │
   └────────────────┘     └────────────────┘    └────────────────┘
     weeks 1–9              weeks 10–16          weeks 17–24
```

If week 9 arrives and Phase 2 is not done, **do not start Phase 3.** Finish Phase 2.
A project with a verified merge layer and no network layer is a real contribution. A
project with a half-verified merge layer and a half-written network layer is the
fourth 70%-complete repository the roadmap warns about in §2.

---

## Weekly operating rhythm

| When | What | Time |
|---|---|---|
| Start of week | Read the phase file's WI list, pick this week's WIs, tick them into [plan/tracking-board.md](plan/tracking-board.md) | 15 min |
| Each session | Work one WI to completion. Commit at every rung of the ladder. Push at end of session. | 2–4 h |
| End of week | Write the week's entry in [plan/decision-log.md](plan/decision-log.md): what shipped, what was learned, what changed in the design | 20 min |
| Phase end | Run the phase exit checklist. Do not start the next phase until every box is ticked. | 1 h |

**Never leave a session with uncommitted work.** If a WI is half-done, commit the
half with a `wip:` prefix and a note in the body about the next rung. The point of
the commit ladder is that resuming never requires reconstructing where you were.

---

## Files in this plan

| File | Purpose |
|---|---|
| [plan/00-overview.md](plan/00-overview.md) | Execution philosophy, definitions of done, how to read a work item |
| [plan/commit-conventions.md](plan/commit-conventions.md) | Commit message format, scopes, ladder rules |
| [plan/ci-and-tooling.md](plan/ci-and-tooling.md) | CI pipeline, local toolchain, pre-commit, versioning |
| [plan/repo-layout.md](plan/repo-layout.md) | Target directory tree and what lands when |
| [plan/phase-0-catalogue-and-spec.md](plan/phase-0-catalogue-and-spec.md) | Weeks 1–2 |
| [plan/phase-1-clocks-and-lattices.md](plan/phase-1-clocks-and-lattices.md) | Weeks 3–5 |
| [plan/phase-2-simulator.md](plan/phase-2-simulator.md) | Weeks 6–9 |
| [plan/phase-3-delta-sync.md](plan/phase-3-delta-sync.md) | Weeks 10–13 |
| [plan/phase-4-dart-and-integration.md](plan/phase-4-dart-and-integration.md) | Weeks 14–16 |
| [plan/phase-5-security-and-identity.md](plan/phase-5-security-and-identity.md) | Weeks 17–20 |
| [plan/phase-6-field-and-writeup.md](plan/phase-6-field-and-writeup.md) | Weeks 21–24 |
| [plan/metrics-instrumentation.md](plan/metrics-instrumentation.md) | What to measure, how, and from when |
| [plan/risk-register.md](plan/risk-register.md) | Live risks with owners, triggers, and mitigations |
| [plan/open-questions.md](plan/open-questions.md) | Roadmap §12 questions, tracked to resolution |
| [DOUBTS.md](DOUBTS.md) | Assumptions execution is resting on. **Read the 🔴 entries before starting a phase.** |
| [plan/tracking-board.md](plan/tracking-board.md) | Checkbox state of every work item |
| [plan/decision-log.md](plan/decision-log.md) | Append-only log of decisions and their reasons |

---

## Non-negotiables

These come from the roadmap and override any local convenience during execution.

1. **`dhara` never imports a domain model.** No `Child`, no `Beneficiary`, no table
   name. If a merge function needs to know what a field means, it gets that from the
   schema descriptor at runtime. Enforced by a CI import-linter rule from Phase 1
   (WI-1.0).
2. **`keep_losers=True` is the default, not an option.** An LWW register that
   discards the loser is a data-loss bug wearing a design-decision costume.
3. **Measurements are append-only.** There is no code path anywhere that overwrites
   a value in a `MeasurementSeries`. Phase 2's deliberate-bug experiment exists
   specifically to prove the simulator catches a violation of this.
4. **The simulator is built before the network layer.** Roadmap §8, Phase 2. It
   shapes the design of everything after it.
5. **Non-goals in roadmap §2 are binding.** No text CRDTs, no P2P, no arbitrary
   user schemas, no live subscriptions, no building the CGMS app.
6. **The engine is allowed to say "I don't know."** Surfacing to a supervisor review
   queue is a designed outcome, not a failure. Never add a tiebreak to make a
   scenario go away.
