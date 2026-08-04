# The deliberate-bug experiment

**Phase 2 · WI-2.17 · measured at commit 100, Python 3.12.4**

> Deliberately introduce a known-bad merge — swap a series append for an
> overwrite — and confirm the simulator finds it within 1,000 seeds. **A harness
> that never fails is a harness that is not testing anything.** Document this
> experiment; it is the single most credible artifact in the repo.
> — roadmap §7.1

---

## Why this exists

A million passing schedules mean nothing on their own. They are equally
consistent with "the merge logic is correct" and with "the harness cannot see
anything."

The only way to tell those apart is to break the code on purpose and check that
the harness notices. This page is that check, and the numbers below are the
evidence behind every other claim in this repository.

**Result: five of seven mutations detected, four within two seeds. Two are
structurally undetectable by this simulator, and the reason is written down
rather than tuned around.**

---

## Results

| # | Mutation | Detected at seed | By |
|---|---|---|---|
| **M1** | Series join overwrites instead of appending | **1** | `no_measurement_lost` |
| **M2** | LWW register discards the loser | **2** | `no_observation_lost` |
| **M3** | HLC tie-break drops `node_id` | **not detected** | — see §blind spots |
| **M3b** | HLC encoding drops `node_id` | **not detected** | — see §blind spots |
| **M4** | OR-Set remove keys on element, not observed tags | **7** | `removals_are_honoured` |
| **M5** | Dedup key includes the HLC | **1** | `no_phantom_measurements` |
| **M6** | Clock reissues timestamps within a tick | **1** | `hlc_causality_respected`, `no_duplicate_operation_ids` |

Control: 1,000 unmutated seeds, zero violations.

M1 — the mutation the roadmap names — is caught by the **first seed**, against a
budget of 1,000.

---

## What the experiment found in the harness itself

The headline result is not that five mutations were caught. It is that **the
first run caught two of six**, and fixing that exposed three genuine defects in
the correctness argument — none of which any other test would have found.

### 1. The no-loss property was only half implemented

`no_measurement_lost` checked that every written measurement was present. Nothing
checked the converse.

M5 survived 1,000 seeds while producing **11 entries where 10 distinct readings
existed**. Every expected entry was present, so the invariant was satisfied — by
a state containing a measurement that never happened.

> **No silent data loss has two directions.** Nothing disappears, *and nothing is
> invented.* Inventing clinical data is at least as bad as losing it: a phantom
> weighing is a data point a supervisor will act on, and it did not happen.

Fixed by `no_phantom_measurements`, which also catches the subtler case where
every key is legitimate but the dedup did not collapse them.

### 2. Nothing checked removal semantics at all

M4 survived because deleting an add locally *converges perfectly well*: the
peer's copy is re-merged in and the element quietly resurrects. Every replica
agrees, on the wrong answer.

Resurrection is the failure the observed-remove design exists to prevent, and it
was the one thing the invariants did not look for. Fixed by
`removals_are_honoured`.

⚠ The first version of that invariant was written at **element** level and fired
on seed 49 — where a concurrent add the remove never observed legitimately kept
the element present, which is correct C-14 behaviour. An invariant that reports
correct behaviour trains you to ignore its output, which is as damaging as one
that misses a bug. It is now checked at tag level, which is exactly what OR-Set
semantics guarantee.

### 3. A derived view can diverge while state agrees

Canonical state equality is necessary but not sufficient. `all_converged` passed
while two replicas would show two different current values to two different
workers, because `max()` over a tied set is only deterministic if the order is
total.

Fixed by `derived_views_agree`.

### And the generator had the blind spot it was written to avoid

The scenario generator's docstring warns — citing the Phase 1 lesson by name —
that generating by constructing states rather than driving operations exempts
every write path from testing.

It then **never called `remove()`**, and never re-recorded an identical reading
with a fresh HLC. M4 and M5 were unreachable for exactly the reason the file
warned about. Writing the warning down did not prevent the mistake; running the
experiment did.

---

## Blind spots

**Two mutations are undetectable by this simulator, by construction.** This
section matters more than the results table: every mutation harness has limits,
and one that claims none is not being honest about what it measured.

### M3 — HLC tie-break drops `node_id`

**Why it is unreachable.** A tiebreak bug diverges replicas only if two replicas
resolve the same tie *differently*. In this design:

- every `join` is a set union, so ordering does not affect merged state;
- canonical form sorts by `encode()`, which carries `node_id` independently;
- the one order-sensitive step is `max()` over a tied set — and in a
  **single-process** simulation both replicas share the interpreter's hash
  seeding, so identical sets iterate identically.

The bug is real in production, where two devices are two processes with
different hash seeds. It is unreachable here because of ADR-0007's execution
model, which is the same single-threaded determinism the harness depends on for
everything else. **This is a cost of that decision, not an oversight.**

Adding synchronised-clock devices so ties actually occur did not change the
result, which is how the diagnosis was confirmed rather than assumed.

**Compensating control:** `tests/unit/test_hlc.py::test_ordering_is_lexicographic_on_pt_then_c_then_node`
catches it directly — verified, not asserted, by
`test_compensating_controls_actually_catch_the_blind_spots`. The randomised
`PYTHONHASHSEED` CI leg covers cross-process iteration order.

### M3b — HLC encoding drops `node_id`

Written to be the reachable variant of M3, and it is not. Collapsing two
encodings only corrupts state when every *other* field of the two values also
matches — and if they all match, the values are genuinely identical and
collapsing them is correct.

**Compensating control:** the HLC encoding and round-trip unit tests.

### C-24 — duplicate device ids

Not a mutation, but the same class of limit. The scenario generator assigns
unique device ids by construction, so the catalogue's worst failure — two
devices sharing an id, breaking operation identity silently — **cannot be
generated at all.**

**Compensating control:** it is handled at enrolment (Phase 5, WI-5.1), where it
fails loudly once rather than corrupting quietly forever.

### What the model cannot see at all

- **Real concurrency bugs inside one device.** Single-threaded by design. The
  simulator finds distributed bugs, not data races.
- **Android process death, doze, OEM battery killers, filesystem corruption on
  cheap flash.** Phase 6 field measurement, and named in
  `docs/honest-tradeoffs.md`.
- **Wall-clock cost and battery.** Bytes and windows are simulated; latency and
  power are field measurements.

---

## How the blind spots are kept honest

They are asserted, not skipped. `test_known_blind_spot_stays_blind` requires each
to *remain* undetected within the push budget.

That reads backwards until you consider the alternative. If M3 starts being
caught, either the recorded analysis was wrong or something meaningful changed
about the execution model — and both are things to be told about rather than to
absorb silently. A skipped test tells you nothing; an inverted assertion tells
you when your own reasoning expired.

Each blind spot must also carry a `blind_spot_reason` and a
`compensating_control`, enforced by `test_every_blind_spot_documents_itself`. A
blind spot with nothing else covering it is an untested behaviour, not a limit.

---

## Reproducing this

```bash
cd dhara-py
python -m pytest tests/sim/test_mutations.py -q      # push budget, 40 seeds
```

Full budget, as run for the table above:

```bash
DHARA_MUTATION_BUDGET=1000 python -m pytest tests/sim/test_mutations.py -q
```

A single mutation, interactively:

```python
from sim.faults import apply_mutation
from sim.scenario import Simulation, generate

with apply_mutation("M1"):
    print(Simulation(generate(1)).run().summary())
```

---

## Why it runs nightly

**Harness sensitivity decays, and nothing else reports it.** A refactor that
makes the scenario generator less adversarial breaks no test — except this one.

Two scheduled events must re-run it before their own results are believed:

| When | Why |
|---|---|
| Phase 3, WI-3.11 | Real sync sessions replace direct state exchange, changing what the simulator explores |
| Phase 5, WI-5.10 | Crypto and identity land on the hot path and touch serialisation |

If any detection time regresses, **fix the generator, not the invariant.** A
generator that has stopped producing concurrency fails nothing; it just quietly
stops finding things.
