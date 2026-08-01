# Execution overview

How to read and use this plan. Read once, then refer back when a phase file's
notation is unclear.

---

## 1. The unit of work

### Work item (WI)

A work item is one sitting's worth of work — 2 to 4 hours — that produces something
demonstrable. Every WI in a phase file has the same shape:

```
### WI-N.M — <title>

**Why**        One or two sentences. If you cannot state why, the WI is wrong.
**Touches**    Files created or modified.
**Depends on** Other WIs that must be done first.
**Done when**  A checkable condition. Not "implemented X" — something you can run.

**Commit ladder**
  1. <exact commit subject>
  2. <exact commit subject>
  ...
```

`N` is the phase number, `M` is the sequence within the phase. WI numbers are
permanent. If a work item is dropped, its number is retired, not reused — the
decision log records why.

### Commit ladder

The ordered list of commits that completes the WI. Rules:

- **Each rung leaves the tree green.** Tests pass, or the tests that exist pass and
  the new ones are marked `xfail`/`skip` with a reason. Never commit a red tree
  without `wip:`.
- **Each rung is explainable in one sentence.** That sentence is the commit subject.
- **Ladders are a floor, not a ceiling.** If implementing rung 3 turns out to need
  four commits, make four commits. The estimate in the phase header absorbs it.
- **Ladders are not a schedule.** Two rungs can land in ten minutes. One rung can
  take two hours.

---

## 2. Definitions of done

Three levels, used throughout the phase files. Do not blur them.

| Level | Symbol | Means |
|---|---|---|
| **Implemented** | `impl` | The code exists and runs on a happy path you typed by hand. |
| **Tested** | `test` | Property tests and/or conformance vectors pass. Adversarial inputs covered. |
| **Verified** | `verif` | The deterministic simulator exercises it under fault injection and the invariants hold. |

**Nothing in the merge or session layer is allowed to ship at `impl`.** The whole
premise of the project (roadmap §7) is that an LLM — or a tired student — will
happily write a sync layer that looks correct and loses data under one specific
interleaving. `impl` is the state where that bug is still present and invisible.

Phase exit criteria are always stated at `verif` for correctness-critical code and
at `test` for everything else.

---

## 3. The three questions before starting any WI

1. **Does this belong in `dhara` or in the consumer?** If the answer requires knowing
   what a child is, it belongs in the consumer's `schema_binding`. This question has
   a wrong answer that feels right at 2 AM, which is exactly why the repository is
   separate (roadmap §4).
2. **What is the failure mode this prevents?** If you cannot name a concrete
   interleaving, partition, or clock skew that this WI defends against, you may be
   building something the non-goals list already excluded.
3. **How will the simulator see it?** From Phase 2 onward, every correctness-relevant
   change should be reachable by the fault injector. Code the simulator cannot reach
   is code with no evidence behind it.

---

## 4. Estimation and slip policy

Each phase file gives an hour estimate per WI. They assume:

- 12–15 hours/week, in 2–4 hour blocks, not 30-minute fragments.
- You have already read the relevant roadmap section.
- Reading time for a paper (HLC, delta-state CRDTs) is budgeted separately and
  called out where it applies.

**When a phase slips:**

| Slip | Response |
|---|---|
| ≤ 1 week | Absorb it. Phases 1 and 3 have the most slack. |
| 1–2 weeks | Cut scope inside the phase from its "stretch" WIs (marked `[stretch]`). Never cut a WI that a later phase's exit criteria depend on. |
| > 2 weeks in phases 0–2 | Stop. Re-plan. These are the irreducible core; compressing them defeats the project. |
| > 2 weeks in phases 3–4 | Push phases 5–6 to the next semester, as the roadmap's risk table already allows. |
| Any slip in phases 5–6 | Acceptable. Ship `v0.1.0-rc` and write up what exists. |

**The one deadline that does not move:** the field-access conversation starts in
week 1 (roadmap §10, highest-severity risk). It is WI-0.0 for that reason — it is the
first thing in the plan, before any technical work, because it has a lead time you do
not control.

---

## 5. What "the spec is the source of truth" means in practice

Two implementations (Python, Dart) against one spec, validated by shared conformance
vectors (roadmap §5.1). The operational consequence:

```
      spec/merge-semantics.md          ← the argument
              │
              ▼
      spec/conformance/**/*.json       ← the executable form of the argument
              │
      ┌───────┴───────┐
      ▼               ▼
  dhara-py        dhara-dart          ← two things that must agree
```

- **A behaviour change starts in the spec.** Edit `merge-semantics.md`, add or amend
  the conformance vector, watch both implementations fail, then fix them. Not the
  other way round.
- **A vector is never edited to match an implementation.** If a vector is wrong, the
  fix is a spec commit that says why it was wrong, and the decision log records it.
- **Divergence is a build failure.** CI runs both suites against the same
  `spec/conformance/` tree. There is no "the Dart one is close enough."

This ordering is what turns "trust me, it's the same logic" into an
interoperability claim.

---

## 6. Working with the CGMS monorepo

Weeks 1–13 use local path dependencies (roadmap §4):

```bash
# in the cgms backend venv
pip install -e ../dhara/dhara-py
```

```yaml
# cgms mobile pubspec.yaml
dependencies:
  dhara:
    path: ../../dhara/dhara-dart
```

From week 14 (WI-4.9), switch to pinned git tags. Every protocol version change from
that point ships with a migration note.

**The dependency rule is one-directional and absolute:**

```
cgms monorepo  ────depends on───▶  dhara
     (never the reverse)
```

`dhara` has no test fixture, no example, and no docstring that mentions CGMS by
name except in `docs/` prose describing the origin of the project.

---

## 7. Notation used in phase files

| Marker | Meaning |
|---|---|
| `[stretch]` | Cut first when the phase is slipping. Nothing downstream depends on it. |
| `[gate]` | Phase exit depends on this WI. Cannot be cut, cannot be deferred. |
| `[spec]` | Produces or amends a document under `spec/`. Changes here precede code. |
| `[research]` | Reading/thinking work with a written artifact as output, not code. |
| `→ §N.M` | Cross-reference into `dhara-sync-engine-roadmap.md`. |
| `⚠` | A known trap. Read the note before starting. |

---

## 8. Related documents

- [commit-conventions.md](commit-conventions.md) — message format and scope list
- [repo-layout.md](repo-layout.md) — the target tree and what lands when
- [ci-and-tooling.md](ci-and-tooling.md) — pipeline, local setup, versioning
- [tracking-board.md](tracking-board.md) — live checkbox state
- [decision-log.md](decision-log.md) — why things are the way they are
