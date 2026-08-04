# Doubts

Every uncertainty hit while executing the plan, with the assumption made to keep
moving and what it would cost if the assumption is wrong.

**This is not [plan/open-questions.md](plan/open-questions.md).** That file tracks
design questions the roadmap itself left open — things nobody has decided yet. This
file tracks places where **execution proceeded on an assumption**: the work is done,
but it rests on a reading of the roadmap, a judgement call, or a gap between two
documents. Every entry here is a place where a correction changes committed code or
committed spec.

**Read the 🔴 entries first.** They block or invalidate work if the assumption is
wrong.

| Field | Meaning |
|---|---|
| **Hit while** | The work item that surfaced it |
| **Doubt** | The actual question |
| **Assumed** | What execution proceeded on |
| **Cost if wrong** | What has to be redone |
| **Resolves by** | What would settle it — usually your decision, sometimes field data |

| Severity | Meaning |
|---|---|
| 🔴 | Blocks or invalidates committed work if wrong |
| 🟠 | Costs rework but is contained |
| 🟢 | Noted for the record; cheap either way |

---

## Index

| ID | Severity | One line | Status |
|---|---|---|---|
| [D-01](#d-01) | 🟠 | Where exactly does the domain-token checker apply? | resolved in-plan |
| [D-02](#d-02) | 🔴 | `keep_losers` is a flag in the roadmap and semantics in the plan | open |
| [D-03](#d-03) | 🟠 | `supersedes` chains on `MeasurementSeries` may be scope creep | open |
| [D-04](#d-04) | 🔴 | Canonical numeric encoding must be settled before any vector | open |
| [D-05](#d-05) | 🔴 | Is `recorded_by` a worker id or a device id? | open |
| [D-06](#d-06) | 🟠 | Wire protocol version `1` versus a spec called `v0.1` | open |
| [D-07](#d-07) | 🟢 | "Same calendar day" needs a timezone that may not be needed | open |
| [D-08](#d-08) | 🟠 | Device ids assumed server-issued at enrolment | open |
| [D-09](#d-09) | 🟢 | Repository hosted under the CNAMS org against roadmap §4 | decided |
| [D-10](#d-10) | 🟠 | CI workflow is unverified — no runner has executed it | open |
| [D-11](#d-11) | 🟢 | The 90% coverage gate is currently meaningless | open |
| [D-12](#d-12) | 🔴 | WI-0.0 field access is a real-world action nobody has taken | open |
| [D-13](#d-13) | 🟠 | Fourteen commit subjects exceed the 72-char limit the hook now enforces | open |
| [D-14](#d-14) | 🟢 | WI-1.0 was done before Phase 0's exit gate | noted |

---

<a id="d-01"></a>
## D-01 — Where exactly does the domain-token checker apply? 🟠

**Hit while** WI-0.4, writing `spec/conflict-catalogue.md`.

**Doubt**
Two plan documents disagree. [plan/repo-layout.md](plan/repo-layout.md) §3 says the
checker fails on domain tokens in any file under `dhara-py/` or `dhara-dart/`.
[plan/phase-1-clocks-and-lattices.md](plan/phase-1-clocks-and-lattices.md) says
"Domain vocabulary leaks into vectors → **Checker fails on `spec/`**".

Under the second reading the conflict catalogue cannot be written at all, because it
is *required* to describe real scenarios — that is its entire purpose (roadmap §8,
Phase 0: *"enumerate every concurrent-edit scenario in the real CGMS schema"*).

**Assumed**
The checker covers `dhara-py/`, `dhara-dart/`, and `spec/conformance/**` — the code
and the machine-readable vectors. It does **not** cover `spec/*.md` prose or `docs/`.

The catalogue therefore uses domain vocabulary and declares a neutral field-id
mapping per entry, so vectors derived from it are clean.

**Cost if wrong** Low, and it is caught mechanically the moment WI-1.0 lands. Worst
case the catalogue is rewritten in neutral vocabulary, which would make it
substantially less useful to anyone checking it against reality.

**Resolves by** Your call on whether a spec document that describes the motivating
deployment counts as a dependency-rule violation. My reading: it does not — the rule
exists to stop merge *logic* knowing about children, and prose that cannot be
imported cannot violate it.

**Action taken** The plan text is being corrected to state the narrower scope.

---

<a id="d-02"></a>
## D-02 — `keep_losers` is a flag in the roadmap and semantics in the plan 🔴

**Hit while** WI-0.6 (C-08), and it will bind hard at WI-1.8.

**Doubt**
Roadmap §5.4's schema sketch passes it as a per-field constructor argument:

```python
Field("display_name",   LWWRegister,        keep_losers=True),
Field("guardian_phone", LWWRegister,        keep_losers=True),
```

The prose immediately below says *"a last-write-wins register that discards the loser
is a data-loss bug wearing a design-decision costume"* — which argues it should not
be optional at all. The execution plan took the stronger reading and made retention
unconditional (EXECUTION.md non-negotiable #2, WI-1.8).

**Assumed**
Retention is **semantics, not an option**. `LWWRegister` has no `keep_losers`
parameter and no code path that discards. The roadmap's sketch is treated as
illustrative rather than as an API commitment.

**Cost if wrong** Moderate and it grows with time. If some fields genuinely should
discard losers — a large free-text field where history is a storage problem on a 2GB
device, say — then `LWWRegister` needs the flag back, `delta_since` needs to respect
it (WI-3.1 rung 4), the wire format needs to carry it, and both implementations
change. Cheap now, expensive after Phase 4.

**Resolves by** Your decision. My recommendation is to keep it unconditional for
v0.1: it is the project's headline claim, the storage cost is small for the field
kinds in scope, and a flag that defaults to safe but can be turned off will
eventually be turned off at 2 AM.

⚠ If retention ever becomes optional, the no-loss invariant (WI-2.11) must be taught
about it, or the simulator will report false violations on every discarding field.

---

<a id="d-03"></a>
## D-03 — `supersedes` chains on `MeasurementSeries` may be scope creep 🟠

**Hit while** WI-0.5, writing C-03.

**Doubt**
Roadmap §6.2 defines `MeasurementSeries` as *"append-only set, deduplicated by
`(taken_at, recorded_by, value)`"* — nothing more. But the roadmap's own starter
scenario list includes *"a measurement is entered, then corrected, then the correction
is corrected"*, and an append-only set with no supersedes link cannot express which
of three values is current. It can only say all three exist.

So either the scenario is under-specified, or `MeasurementSeries` needs more than the
roadmap says.

**Assumed**
Entries carry an optional `supersedes` reference to another entry in the same series.
It is an annotation, never a deletion: a superseded entry is fully retained. "Current"
is derived as the entry no other entry supersedes. Concurrent supersedes of one entry
produce a fork, which converges and emits `superseded_fork`.

**Cost if wrong** Contained if caught before WI-1.10. `supersedes` touches the entry
type, the dedup key's interaction with it, the delta computation, the wire format, and
one review signal. After Phase 3 it is a protocol change.

**Resolves by** Your call on whether v0.1 needs a notion of "the current value of a
measurement field" at all. The alternative — the consumer derives currency from
`taken_at` and HLC ordering, and `dhara` stays a pure set — is simpler and arguably
more correct given the dependency rule. **I lean toward the simpler option**, but C-03
as written assumes the richer one.

⚠ This is the one place in Phase 0 where I extended the roadmap's data model rather
than implementing it. It deserves an explicit yes or no before WI-1.10.

---

<a id="d-04"></a>
## D-04 — Canonical numeric encoding must be settled before any vector 🔴

**Hit while** WI-0.5. Blocks WI-1.6 rung 5 and everything downstream of it.

**Doubt**
Measurement values are decimals — 9.2 kg, 74 cm, 12.1 cm. Canonical serialisation
must be **byte-identical** across Python and Dart, because two replicas whose states
serialise differently will see a spurious difference and resend forever (this is a
convergence bug, not a cosmetic one).

Python's `repr(9.2)` and Dart's `9.2.toString()` do not agree in all cases, and IEEE
754 comparison for the dedup key means `9.2` recorded on two devices may or may not
be the same value depending on the parsing path.

**Assumed**
Nothing yet — the catalogue is written with decimal values as prose, which is safe.
**No vector has been written**, so no commitment exists.

**Cost if wrong** Very high if discovered late. Every conformance vector, both
serialisers, the dedup key, and the delta comparison all depend on it. Discovering it
during the Phase 4 Dart port means rewriting every vector.

**Resolves by** Your decision, before WI-1.15. Options in
[plan/open-questions.md](plan/open-questions.md) Q7. My recommendation: **integer
minor units declared in the schema** — grams, millimetres, tenths of a centimetre.
Floating point in a clinical record is a liability independent of serialisation, and
this removes the class of problem rather than encoding around it.

The cost of that choice is that `Field` gains a `scale` parameter and the consumer's
`schema_binding` does the unit conversion — which is the right place for it, since
"weight is in grams" is domain knowledge.

---

<a id="d-05"></a>
## D-05 — Is `recorded_by` a worker id or a device id? 🔴

**Hit while** WI-0.5, writing C-02 and C-06.

**Doubt**
The dedup key is `(taken_at, recorded_by, value)`. What `recorded_by` refers to
changes which scenarios dedup:

- **Worker id.** Two workers recording the same reading on the same child at the same
  instant produce two entries — arguably correct, since two people did two things.
  One worker recording on two devices produces one entry.
- **Device id.** The opposite. And C-17's requirement that operations are attributed
  to the *worker, not the device* argues strongly against device id here.

**Assumed**
`recorded_by` is the **worker id**, consistent with C-17 and roadmap §6.5
(*"each operation attributed to the worker, not the device"*). C-06 is written on
that basis — it describes one worker entering the same reading on two devices.

**Cost if wrong** Moderate. It changes the dedup key's behaviour, which changes C-02
and C-06's outcomes and their vectors, and it interacts with D-02 and D-04 in the
schema API.

**Resolves by** Your confirmation. Note that this also implies **every operation
carries a worker id from Phase 1 onward**, not from Phase 5 when per-worker sessions
are built — which is a small but real change to the Phase 1 entry type.

⚠ If a worker id is not available at write time in the current CGMS app, this
assumption is not implementable and the whole dedup key needs revisiting.

---

<a id="d-06"></a>
## D-06 — Wire protocol version `1` versus a spec called `v0.1` 🟠

**Hit while** WI-0.2, adding `PROTOCOL_VERSION` to `dhara/__init__.py`.

**Doubt**
[plan/ci-and-tooling.md](plan/ci-and-tooling.md) §6 says the wire protocol version is
an **integer** in the handshake, bumped on any incompatible change. The spec document
is `spec/protocol-v0.1.md`. Is protocol integer `1` the same thing as "protocol v0.1"?
If the library later reaches `v0.2` with an unchanged wire format, is the document
renamed?

**Assumed**
They are decoupled. `PROTOCOL_VERSION = 1` is the integer on the wire.
`protocol-v0.1.md` is a document name that describes the **first** wire protocol, and
it keeps its name even if the library version moves. A wire-incompatible change
produces `PROTOCOL_VERSION = 2` and a new document.

**Cost if wrong** Low — a rename and a note in `spec/versioning.md`. Recorded because
it is exactly the kind of thing that becomes confusing at Phase 4 when CGMS pins a
tag and has to state what it is compatible with.

**Resolves by** Your preference, ideally before WI-3.14 freezes the protocol.

---

<a id="d-07"></a>
## D-07 — "Same calendar day" needs a timezone that may not be needed 🟢

**Hit while** WI-0.5, writing C-01's `multiple_weights_same_day` signal.

**Doubt**
Two devices with different clocks may disagree about what calendar day it is,
particularly around midnight and particularly when one is skewed by days (C-15). I
specified the signal as computed against a **schema-declared record timezone**.

But India is a single timezone. This may be machinery for a problem this deployment
does not have.

**Assumed**
A schema-declared timezone, defaulting to a single configured value. Costs one field
in the schema descriptor and removes an ambiguity.

**Cost if wrong** Negligible either way. If it is over-engineering it is one unused
parameter; if it is omitted and later needed, it is a schema change.

**Resolves by** Not urgent. Worth a sentence in `merge-semantics.md` when WI-1.16 is
written.

---

<a id="d-08"></a>
## D-08 — Device ids assumed server-issued at enrolment 🟠

**Hit while** WI-0.8, writing C-24.

**Doubt**
C-24 (duplicate device ids) is unrecoverable-by-design if ids can collide: the HLC
tiebreak stops being a tiebreak and operations are silently discarded as duplicates
of each other. Preventing it requires knowing where device ids come from, and the
roadmap does not say — it says only that per-device *keys* are issued at enrolment
(§6.5).

**Assumed**
Device ids are **server-issued at enrolment and bound to the device keypair**, never
derived from a hardware identifier (which a cloned image or a re-flashed phone would
reproduce). The server refuses to issue an id it has already bound to a live key.

**Cost if wrong** Moderate, and it lands in Phase 5. If ids must be locally generated
— for instance because enrolment itself has to work offline — then collision becomes
a probabilistic argument (a 128-bit random id) rather than a structural guarantee,
and C-24's "detect at enrolment" outcome is not achievable as written.

**Resolves by** Your call, and it depends on a question I cannot answer: **must device
enrolment work offline?** If a device can be enrolled in a village with no network,
server-issued ids are impossible and the whole entry changes.

---

<a id="d-09"></a>
## D-09 — Repository hosted under the CNAMS org against roadmap §4 🟢

**Hit while** Initial setup.

**Doubt**
Roadmap §4 recommends personal-account hosting, on the grounds that *"org-hosted
repos invite 'which parts were yours?' in an interview."* The repository exists at
`CNAMS/cnams_dhara`.

**Assumed**
Keep it. You created it after writing that section, so it reads as a decision rather
than an oversight.

**Cost if wrong** Low now, higher later — transferring a repository with a published
tag and an external consumer pinning it is more disruptive than transferring an empty
one.

**Resolves by** Decided. Recorded in [plan/decision-log.md](plan/decision-log.md)
with the mitigation: the org prefix stops at the repository name and appears in no
import path, module name, wire field or spec document.

---

<a id="d-10"></a>
## D-10 — CI workflow is unverified 🟠

**Hit while** WI-0.3.

**Doubt**
`.github/workflows/py.yml` is committed but **no runner has executed it.** It uses
`astral-sh/setup-uv` and `uv sync --all-groups`; `uv` is not installed on this
machine, so the workflow's install and lint steps have never run. The tests were run
locally with a plain `venv` and `pytest`, which is a different path.

**Assumed**
The workflow is correct as written. This is an assumption, not a verified fact.

**What is actually verified:** `pytest` passes locally under Python 3.12.4. Nothing
else — not ruff, not mypy, not the coverage gate, not either matrix leg.

**Cost if wrong** Low. A broken workflow fails visibly on the first push and is fixed
in one commit.

**Resolves by** Pushing and reading the Actions tab. Until then, **the Phase 0 exit
checklist item "CI is green" is unticked and must stay unticked.**

---

<a id="d-11"></a>
## D-11 — The 90% coverage gate is currently meaningless 🟢

**Hit while** WI-0.2.

**Doubt**
`fail_under = 90` is configured, and the package currently contains two constants and
a docstring. Coverage is trivially 100%. The gate will pass throughout Phase 0 while
testing nothing.

**Assumed**
Leave it. It costs nothing and starts doing real work at WI-1.1.

**Cost if wrong** None. Recorded so that a green coverage badge during Phase 0 is not
mistaken for evidence.

---

<a id="d-12"></a>
## D-12 — WI-0.0 field access is a real-world action nobody has taken 🔴

**Hit while** Phase 0 execution.

**Doubt**
WI-0.0 is the **first work item in the plan** and the mitigation for R1, the
highest-severity risk in the register: *without field access this is a well-tested
library with no evidence it survives reality.* It requires contacting the EPICS
coordinator and the ICDS contact.

**No such contact has been made.** It cannot be made from here.

**Assumed**
Nothing. This is flagged, not assumed.

**Cost if wrong** This is the risk that cannot be recovered late. It has a lead time
measured in weeks and is entirely outside the technical work. Every week it slips is a
week subtracted from Phase 6, and by week 12 the fallback (5 phones, one week, real
workers) is the only option left.

**Resolves by** You sending the request. Nothing else in this repository substitutes
for it, and it is worth doing before the next line of code is written.

⚠ Also ask the Q5 question in the same conversation — whether ICDS requires an
Aadhaar-adjacent identity path — because the answer constrains the Phase 5 design and
has the same lead time.

---

<a id="d-13"></a>
## D-13 — Fourteen commit subjects exceed the limit the hook now enforces 🟠

**Hit while** WI-0.13, running `scripts/check_commit_message.py` over the existing
history as a self-check.

**Doubt**
[plan/commit-conventions.md](plan/commit-conventions.md) §1 sets the subject limit at
**72 characters**, and the hook enforces it. **Fourteen commits already on `main`
violate it**, by between 1 and 14 characters. They were written before the hook
existed.

Two defensible responses and one indefensible one:

| Option | |
|---|---|
| Rewrite history to shorten them | Clean result. Requires a force-push, which rewrites every SHA. The repository is days old with no external consumer, so the blast radius is small — but it is still a destructive push to a shared remote. |
| Leave them and enforce going forward | Honest, zero risk, leaves a visibly inconsistent history for its first 34 commits. |
| Relax the documented limit to a number the existing commits meet | **Rejected.** That is rationalising a rule to match a violation, and the rule is a reasonable one. |

**Assumed**
The second. The limit stays at 72, the hook enforces it from now on, and the existing
fourteen stand as-is.

**Cost if wrong** Cosmetic. `git log --oneline` wraps for those fourteen entries in a
narrow terminal.

**Resolves by** Your call. If you want the rewrite, it is
`git filter-branch`/`git filter-repo` plus a force-push, and it should happen **now**
rather than after the CGMS repository starts citing SHAs — a rewritten SHA breaks
every cross-repo reference, and the plan calls for those from week 14.

⚠ I did not force-push. Rewriting published history is not a call to make
unprompted.

---

<a id="d-14"></a>
## D-14 — WI-1.0 was completed before Phase 0's exit gate 🟢

**Hit while** WI-0.13.

**Doubt**
The plan says: *"Do not start Phase 1 with an unticked box."* WI-1.0 (the
domain-token checker) is a Phase 1 item, and it was implemented during Phase 0.

**Assumed**
Justified by a dependency the plan did not anticipate: `.pre-commit-config.yaml`
(WI-0.13) **references** `scripts/check_no_domain_imports.py`. Committing the hook
config first would have left a broken hook chain — every commit failing on a missing
script — which is worse than a small ordering violation.

**Cost if wrong** None. WI-1.0 is a gate for Phase 1, not for Phase 0, and doing it
early strictly reduces risk: the dependency rule was enforced from the first line of
engine code rather than after it.

**Resolves by** Noted rather than resolved. Worth reflecting back into
[plan/phase-0-catalogue-and-spec.md](plan/phase-0-catalogue-and-spec.md) if the plan
is ever revised: WI-1.0 is a natural Phase 0 item.

---

## How to use this file

- Entries are appended as execution proceeds. Nothing is deleted; a resolved entry
  gets its resolution written into it and its status changed.
- A 🔴 entry that stays open past the phase that depends on it is a phase-exit
  blocker.
- When an entry is resolved, the decision goes to
  [plan/decision-log.md](plan/decision-log.md) and, if substantial, an ADR. This file
  keeps only the record that the question was asked and what was assumed meanwhile.
