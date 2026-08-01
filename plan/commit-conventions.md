# Commit conventions

The history is part of the artifact. Someone evaluating this project will read
`git log` to see whether the correctness argument was constructed or asserted.
Optimise for that reader.

---

## 1. Format

Conventional Commits, with a mandatory scope for anything under `dhara-py/`,
`dhara-dart/`, or `spec/`.

```
<type>(<scope>): <subject in imperative mood, lowercase, no trailing period>

<body: why, not what. wrap at 72. optional for trivial commits,
required for anything touching merge semantics or the wire protocol.>

<footers: Refs:, Seed:, Spec:, BREAKING CHANGE:>
```

**Subject line: ≤ 72 characters, imperative mood.** "add HLC send path", not "added"
or "adding" or "this adds".

---

## 2. Types

| Type | Use for |
|---|---|
| `feat` | New capability visible to a caller of the library |
| `fix` | Corrects wrong behaviour. Body must state the failure mode it fixes. |
| `test` | Adds or changes tests only |
| `sim` | Simulator, fault injection, invariant checkers, scenario generators |
| `spec` | Anything under `spec/` — protocol, merge semantics, catalogue, vectors |
| `perf` | Measurable improvement, with the number in the body |
| `refactor` | No behaviour change. If behaviour changes it is not a refactor. |
| `docs` | Prose outside `spec/` — README, `plan/`, `docs/` |
| `build` | Packaging, dependencies, pyproject, pubspec |
| `ci` | Workflow files |
| `chore` | Tooling, formatting config, housekeeping |
| `wip` | Session ended mid-ladder. Body states the next rung. Must not survive to `main` overnight where avoidable. |

**`fix` requires a failure mode in the body.** Not "fixes merge bug" —
"concurrent add and remove on the same tag resolved to remove, losing the add;
observed-remove requires the add to win when the remove did not observe it."

---

## 3. Scopes

Fixed list. Adding a scope is itself a `chore` commit that edits this file.

| Scope | Covers |
|---|---|
| `hlc` | Hybrid logical clock |
| `lattice` | Lattice base types and the registry |
| `lww` | LWW register |
| `gset` | Grow-only set |
| `orset` | Observed-remove set |
| `series` | MeasurementSeries |
| `status` | StatusLattice / domain join |
| `vv` | Version vectors |
| `delta` | Delta-state computation |
| `session` | Sync session state machine, chunking, acks |
| `queue` | Priority queues, backpressure, photo lane |
| `schema` | Schema descriptor API |
| `store` | Local persistence (SQLite / SQLCipher) |
| `crypto` | Keys, enrolment, revocation |
| `identity` | Duplicate detection, tombstones, forwarding pointers |
| `review` | Review-queue signal emission |
| `conformance` | Vector runner in either language |
| `sim` | Simulator internals (used as a scope as well as a type) |
| `net` | Simulated network model |
| `clock` | Simulated clock / skew model |
| `dart` | Dart-side code with no more specific scope |
| `py` | Python-side code with no more specific scope |
| `plan` | Files under `plan/` |
| `metrics` | Instrumentation and telemetry |

Language is implied by path, not scope. `feat(series)` in `dhara-dart/` does not
need to say `dart`.

---

## 4. Footers

| Footer | When | Example |
|---|---|---|
| `Refs:` | Link to the WI | `Refs: WI-2.7` |
| `Seed:` | A simulator seed that reproduces the bug being fixed | `Seed: 4471` |
| `Spec:` | The spec section this implements or changes | `Spec: merge-semantics.md#status-lattice` |
| `Vector:` | The conformance vector added or changed | `Vector: merge/concurrent_weight_same_morning.json` |
| `BREAKING CHANGE:` | Wire-protocol incompatibility. Required from week 14. | `BREAKING CHANGE: chunk header gains a priority byte` |

**`Seed:` on every simulator-found bug fix, without exception.** That footer is what
makes the history a record of the simulator doing its job. `git log --grep="Seed:"`
should eventually be a list of every bug the harness caught, which is directly the
evidence roadmap §7.1 asks for.

---

## 5. Ladder rules

1. **One rung, one commit.** Do not squash a ladder before pushing. The granularity
   is the point.
2. **Green at every rung.** If rung 3 needs rung 4 to pass tests, the new test is
   added at rung 4, or added at rung 3 marked `xfail` with the reason in the
   decorator.
3. **Test commits may precede implementation.** A `test:` commit adding a failing
   conformance vector, followed by `feat:` making it pass, is the preferred shape
   for merge semantics work. It puts the specification of the behaviour before the
   behaviour in the history.
4. **Never mix a rename with a change.** Rename in one commit, change in the next.
   `git log --follow` and `git blame` both degrade otherwise, and blame on the merge
   functions is something you will want in month five.
5. **Never mix formatting with logic.** Run the formatter as its own `chore` commit.

---

## 6. Authorship

Commits are authored by the repository owner. No co-author trailers, no
tool-generated attribution footers, no `Generated with` lines.

Verify before the first push:

```bash
git config user.name
git config user.email
git log --format='%an <%ae>%n%b' | grep -iE 'co-authored|generated' || echo "clean"
```

If a trailer has already landed, rewrite it out before pushing:

```bash
git filter-branch -f --msg-filter \
  'grep -viE "^(Co-Authored-By|Co-authored-by|.*Generated with)" ' \
  -- --all
```

Do this before the branch is public. After it is public, rewriting history is a
worse problem than the trailer.

---

## 7. Branching

- `main` is the trunk and is always green. Phases 0–3 commit directly to it; you are
  the sole author and a PR to yourself is ceremony.
- From Phase 4, when the CGMS monorepo depends on tags, use short-lived branches for
  anything that changes the wire protocol: `proto/<change>`. Merge with `--no-ff` so
  the protocol change is one identifiable range in the history.
- Experiments that may be thrown away: `spike/<name>`. Never merged; findings go to
  the decision log and the branch is deleted.

---

## 8. Tags

| Tag | When | Meaning |
|---|---|---|
| `phase-N-complete` | Every phase exit | All exit criteria ticked. Annotated tag, body = the exit checklist with results. |
| `v0.1.0-rc` | End of Phase 4 | Wire protocol frozen. CGMS switches from path deps to this tag. |
| `v0.1.0` | End of Phase 6 | Field data collected, spec published. |

Annotated tags only (`git tag -a`). The tag body for `phase-N-complete` is the
phase's exit checklist with the actual measured numbers filled in — that is the
cheapest possible way to keep the evidence attached to the point in history it
describes.

---

## 9. Examples

Good:

```
feat(series): dedup appends on (taken_at, recorded_by, value)

Two syncs of the same measurement must not produce two entries. The
dedup key deliberately excludes the HLC: the same physical reading
re-delivered gets a fresh HLC on the second path, so keying on it would
admit the duplicate the key exists to reject.

Refs: WI-1.6
Spec: merge-semantics.md#measurementseries
Vector: merge/duplicate_delivery_same_reading.json
```

```
fix(orset): keep concurrent add when remove did not observe it

Removes carried only the element, not the set of observed tags, so a
remove issued before an add was delivered would erase that add on merge
- the exact scenario in catalogue entry C-14. Removes now carry the
observed tag set.

Refs: WI-1.9
Seed: 88213
Vector: merge/concurrent_add_remove_unobserved.json
```

Bad:

```
update merge logic            # no type, no scope, no information
fix(lattice): fix bug         # which bug, what failure mode
feat(session): implement session, add tests, run formatter   # three commits
```
