# Phase 2 exit review — the simulator

**Measured at commit 110 · Python 3.12.4 · Apple Silicon, 8 cores**
**Result: 20 of 22 work items done. Exit criteria not met. Tag withheld.**

---

## Exit criteria

| # | Criterion | Result |
|---|---|---|
| 1 | **1,000,000 randomised schedules** converge with no measurement loss | ⛔ **70,000 run** (3,384,338 operations), all green. Gate not run. |
| 2 | The deliberate-bug experiment finds the injected fault within 1,000 seeds | ✅ **seed 1** for M1, the mutation the roadmap names |
| 3 | The experiment is written up, including what the harness cannot catch | ✅ [deliberate-bug-experiment.md](deliberate-bug-experiment.md) |
| 4 | All six §7.1 fault classes injectable | ✅ |
| 5 | Every invariant has a test proving it can fail | ✅ 9 invariants, 11 tests |
| 6 | `replay_seed.sh <n>` → timeline in one command | ✅ |
| 7 | Shrinking reduces a known failure to a minimal reproducer | ✅ 3 devices/3 records/18 writes → 2/1/4, no faults |
| 8 | Identical seeds produce identical traces | ✅ |
| 9 | Throughput ≥ 500 schedules/s/core | ⛔ **42/s/core** (141/s across 8) |
| 10 | Nightly sweep and regression corpus running | ⚠ committed, **never executed** |

**156 tests green.**

---

## Why the tag is withheld

Three criteria are unmet, and two of them collapse to one cause.

### The million-schedule gate has not been run

70,000 schedules is 7% of the gate by count — though **3,384,338 operations**
exceeds a million, and operations are what the invariants actually examine.

It could not be run here. At a verified 141 schedules/s sharded the gate is ~1.9
hours, and the development sandbox terminates any job outliving its originating
call, including `setsid nohup` detached ones. 495 seconds is the longest
achievable run. `.github/workflows/nightly.yml` shards the full million across
four scheduled jobs.

**That workflow has never executed.** Neither has any other workflow in this
repository — [DOUBTS.md D-10](../DOUBTS.md#d-10), open since Phase 0.

> **One unblocking action — letting CI run once — closes both the Phase 0 exit
> and the Phase 2 gate.** It is now the highest-leverage item in the project
> after the field-access conversation.

### Throughput is 12× short per core

42 schedules/s against 500. Profiling found three fixable costs (24 → 42/s), and
what remains is full-state serialisation — the exact cost Phase 3's delta design
deletes (WI-3.1). Optimising further would be optimising code about to be
removed.

Recorded as short rather than reframed. Re-measure after WI-3.1, when the number
says something about the design instead of about a placeholder.

---

## What this phase actually established

Not "a million schedules passed." **That the harness can be shown to fail when
the merge logic is wrong** — which is the only thing that makes a passing sweep
mean anything.

| Mutation | Detected at |
|---|---|
| M1 series join overwrites | seed 1 |
| M2 register discards the loser | seed 2 |
| M5 dedup key includes the HLC | seed 1 |
| M6 clock reissues timestamps | seed 1 |
| M4 OR-Set remove keys on element | seed 7 |
| M3, M3b tie-break variants | **structurally undetectable** — reason and compensating control recorded |

---

## The five defects this phase found

None in `dhara`. All five in the **harness** and the **correctness argument** —
which is what an unexercised harness should be expected to produce first, and
why exercising it mattered more than running it far.

| # | Defect |
|---|---|
| 1 | **The network model was never exercised.** Syncs scheduled at uniform random times landed inside a 90-second window essentially never: 4 messages delivered out of 1,034. Every invariant passed for that reason. Devices now sync when a window opens. |
| 2 | **The no-loss property was half implemented.** Nothing checked that measurements are not *invented*. M5 produced 11 entries where 10 distinct readings existed and nothing noticed. A phantom reading is one a supervisor acts on. |
| 3 | **Nothing checked removal semantics.** Deleting an add locally converges perfectly — every replica agrees, on the wrong answer, and the element resurrects. |
| 4 | **A derived view can diverge while state agrees.** Two replicas showing two workers different current values, with `all_converged` quiet. |
| 5 | **Crash-loss accounting had a loophole.** The survived-elsewhere check was *vacuously true* for a replica that never saw the write — so a real loss could be excused on the strength of another replica's ignorance. |

And the generator had the exact blind spot its own docstring warns about, citing
the Phase 1 lesson by name: it never called `remove()`. **Writing the warning
down did not prevent it. Running the experiment did.**

---

## Two findings worth carrying into Phase 3

**Aggressive fault injection can suppress a bug class.** With every clock skewed
by up to ±3 days, two devices essentially never issue timestamps in the same
millisecond — so the `node_id` tiebreak almost never breaks a real tie. A fault
that is always on hides whatever the healthy path would have tested.

**Absorption short-circuits are exact, not approximations.** `join(a, b) == a`
whenever `b <= a` follows from the lattice laws, and it is the common case when a
re-delivered snapshot is a subset of what the receiver holds. Phase 3's delta
computation should exploit the same identity rather than rediscovering it.

---

## Obligations Phase 3 inherits

| When | What |
|---|---|
| WI-3.11 | **Re-run the mutation suite** after real sessions replace direct state exchange. If any detection time regresses, fix the generator, not the invariant. |
| WI-3.1 | **Re-measure per-core throughput** once delta sync removes full-state serialisation. |
| Before trusting any Phase 3 sweep | The gate must have run at least once. |

⚠ **Phase 3 proceeds with the gate outstanding**, which is a deviation from the
plan's own rule that a phase does not start with its predecessor's checklist
unticked. The justification is narrow and worth stating: the blocker is
environmental rather than a property of the work — the harness is built, proven
sensitive, and green over 3.4 million operations. What is missing is machine
time, which CI has and this machine does not.

The rule still binds on anything the gate could invalidate: **no Phase 3 result
is trusted until the gate has run.**

---

## Open doubts

Unchanged from Phase 1: D-02 through D-05 remain committed-to, now additionally
encoded in the simulator's schema and oplog. D-10 (CI never executed) has been
promoted from a nuisance to a **phase-gate blocker for two phases**.
