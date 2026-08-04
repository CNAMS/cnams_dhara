# Leftover

What remains, what is blocked, and what cannot be done from a keyboard.

Companion to [plan/tracking-board.md](plan/tracking-board.md), which is the checkbox
state. This file explains **why** the unticked boxes are unticked, and separates the
three very different reasons:

| Category | Meaning |
|---|---|
| 🔨 **Buildable** | Ordinary remaining work. Nothing blocks it. |
| 🚧 **Blocked on a decision** | Written, but resting on an assumption only you can confirm. → [DOUBTS.md](DOUBTS.md) |
| 🌍 **Not doable from here** | Needs hardware, a network, a runner, or another human. |

Last updated at 58 commits · Phase 0 at 13/15 · Phase 1 at 6/18.

---

## 1. Not doable from here 🌍

These are the ones that matter most, because no amount of further coding removes
them.

### WI-0.0 — The field-access conversation

**The first item in the plan, and it has not happened.**

It is the mitigation for R1, the highest-severity risk in the register: *without field
access this is a well-tested library with no evidence it survives reality.* Lead time
is weeks and it is entirely outside the technical work.

| Week | What should be true |
|---|---|
| 1 | Request sent to the EPICS coordinator and the ICDS contact |
| 6 | Escalate if no reply |
| 12 | Commit to the fallback — 5 phones, one week, real workers — and stop waiting |
| 21 | Deployment begins, or the fallback runs |

⚠ Ask the **Q5** question in the same conversation: does ICDS require an
Aadhaar-adjacent identity path? The answer constrains the Phase 5 design and has the
same lead time. → [plan/open-questions.md](plan/open-questions.md) Q5

### CI has never run

`.github/workflows/py.yml` is committed and **no runner has executed it.** It uses
`astral-sh/setup-uv` and `uv sync`; `uv` is not installed on the machine this was
built on. Everything verified locally went through a plain venv and pytest — a
different path.

Unverified: ruff, ruff-format, mypy strict, the coverage gate, both matrix legs, and
the randomised-hash-seed leg. → [DOUBTS.md D-10](DOUBTS.md#d-10)

**Check the Actions tab.** Until it is green, the Phase 0 exit box stays unticked.

### Anything needing real hardware

| Item | Phase | Needs |
|---|---|---|
| WI-4.5 rung 11 — backlog query under 100 ms | 4 | An actual 2GB Android device. An emulator on an M-series Mac reports a number that means nothing. |
| WI-4.10 — two-phone test | 4 | Two physical phones in airplane mode |
| WI-5.2 rung 6 — SQLCipher overhead | 5 | Same 2GB device |
| WI-6.1 — battery instrumentation | 6 | Real devices in real use |
| All of Phase 6 | 6 | Real workers, real networks, real centres |

### The CGMS-side work items

WI-4.7 (FastAPI adapter) and WI-4.8 (Flutter integration) land in the **other**
repository. Planned here because they are on this phase's critical path; not
executable here.

---

## 2. Blocked on a decision 🚧

Four assumptions are load-bearing and only you can confirm them. Work continues on my
stated recommendation, recorded in each entry — but a reversal costs rework, and the
cost grows with every phase.

| Doubt | Question | Proceeding on | Cost of reversal |
|---|---|---|---|
| [D-02](DOUBTS.md#d-02) | Is `keep_losers` a per-field flag or unconditional semantics? | **Unconditional.** No flag, no discarding code path. | Grows: register, delta, wire format, both implementations. Cheap now, expensive after Phase 4. |
| [D-04](DOUBTS.md#d-04) | How are decimals encoded canonically across Python and Dart? | **Integer minor units, scale declared in the schema.** | Every merge vector rewritten. Cheapest possible moment is before WI-1.15. |
| [D-05](DOUBTS.md#d-05) | Is `recorded_by` a worker id or a device id? | **Worker id**, consistent with C-17 and roadmap §6.5. | Changes the dedup key, so C-02 and C-06 and their vectors. Also implies operations carry a worker id from Phase 1, not Phase 5. |
| [D-03](DOUBTS.md#d-03) | Do measurement entries need `supersedes` chains? | **Yes** — because the catalogue says so, and the rule is that implementation follows spec, never the reverse. I still lean toward the simpler pure-set version. | A spec change plus a wire-format change after Phase 3. |

⚠ **D-04 is the one to answer first.** Nothing is committed to yet, and it is the only
one whose cost jumps discontinuously — the moment merge vectors exist, changing the
numeric encoding rewrites all of them, in both languages.

---

## 3. Buildable now 🔨

### Phase 1 — twelve items remain

The clock layer is done. The lattice layer is not.

| WI | Item | Notes |
|---|---|---|
| 1.6 | Lattice base contract | The `join`/`leq`/codec protocol plus reusable law checkers, so adding a lattice costs three lines of test |
| 1.7 | `GSet` | Simplest; validates the base contract on something with no subtlety |
| 1.8 | `LWWRegister` with retained losers `[gate]` | Where D-02 becomes code |
| 1.9 | `ORSet` | Observed-remove; C-14 |
| 1.10 | `MeasurementSeries` `[gate]` | The conceptual centre. Where D-03, D-04 and D-05 all land. |
| 1.11 | `StatusLattice` | Domain join, validated exhaustively at construction |
| 1.12 | Schema descriptor API | `Field`, `Schema`, field-wise record join |
| 1.13 | Review signal emission | Plus `spec/review-signals.md` — eleven signals declared by the catalogue |
| 1.14 | Conformance runner (merge) | All `n!` permutations of replica order |
| 1.15 | Merge vectors `[gate]` | 16 of the 24 catalogue entries are expressible here |
| 1.16 | Complete `merge-semantics.md` `[gate]` | The rationale sections; skeleton exists |
| 1.17 | Phase 1 exit review `[gate]` | 10,000 orders per lattice, green |

### Phases 2–6

Fully planned, not started. See the phase files for work-item breakdowns:
[2](plan/phase-2-simulator.md) · [3](plan/phase-3-delta-sync.md) ·
[4](plan/phase-4-dart-and-integration.md) · [5](plan/phase-5-security-and-identity.md) ·
[6](plan/phase-6-field-and-writeup.md)

⚠ Phase 2 is the one not to compress. It is where "I believe this is correct" becomes
"here is a search that failed to find a counterexample, and here is proof the search
would have found one." Phases 0–2 are the irreducible core.

---

## 4. Deferred deliberately

Not forgotten — decided against, for a stated reason.

| Item | Why deferred | Revisit |
|---|---|---|
| Rust core with FFI | FFI debugging on Android eats the timeline; two implementations produce a stronger interoperability claim | v0.2 (ADR-0002) |
| Tombstone GC policy | The right retention period is an empirical question about how long devices are actually offline. Guessing gives either resurrection bugs or storage exhaustion. | Phase 6 data (Q2) |
| Bloom filter pre-push | A UX improvement on a correctness backbone that does not exist yet | Phase 5 `[stretch]` |
| Key rotation | Same | Phase 5 `[stretch]` |
| Publishing to PyPI / pub.dev | No external consumers. Git tags suffice until there are. | When there are |
| Benchmarks in the push pipeline | Shared runners are too noisy for bytes-per-record numbers | Local, fixed machine |

---

## 5. Housekeeping

| Item | Detail |
|---|---|
| History rewrite | Fourteen commits exceed the 72-char subject limit the hook now enforces. Rewriting needs a force-push and should happen **before** CGMS starts citing SHAs. → [D-13](DOUBTS.md#d-13) |
| `phase-0-complete` tag | Blocked on WI-0.0 and CI verification |
| Coverage gate | Configured at 90%, currently meaningless — the package is nearly empty. Starts doing real work at WI-1.6. → [D-11](DOUBTS.md#d-11) |
| `plan/phase-0-*.md` revision | WI-1.0 is a natural Phase 0 item; the plan puts it in Phase 1. → [D-14](DOUBTS.md#d-14) |

---

## 6. The order to do things in

1. **Send the field-access request.** It has the longest lead time and nothing here
   substitutes for it.
2. **Answer D-04.** It is the cheapest decision to make now and the most expensive to
   change later.
3. Finish Phase 1's lattice layer — WI-1.6 through WI-1.17.
4. Do not start Phase 3 before Phase 2's exit checklist is fully ticked. A verified
   merge layer with no network layer is a real contribution; two half-finished layers
   are not.
