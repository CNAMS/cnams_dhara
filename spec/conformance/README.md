# Conformance vectors

Language-agnostic test cases that **every** `dhara` implementation must reproduce
identically. Python and Dart both run this tree. **Divergence is a build failure.**

---

## The contract

```
     spec/merge-semantics.md          the argument
              │
              ▼
     spec/conformance/**/*.json       the executable form of the argument
              │
      ┌───────┴───────┐
      ▼               ▼
  dhara-py        dhara-dart         two things that must agree
```

Three rules, in the order they matter:

1. **A behaviour change starts in the spec.** Edit `merge-semantics.md`, add or amend
   the vector, watch both implementations fail, then fix them. Not the other way
   round.
2. **A vector is never edited to match an implementation.** If a vector is wrong, the
   fix is a spec commit that says why it was wrong, and the decision log records it.
3. **Every vector traces to a catalogue entry.** A vector covering nothing in
   [conflict-catalogue.md](../conflict-catalogue.md) is testing behaviour nobody
   decided was correct. The `catalogue` field is required by the schema.

---

## Layout

| Directory | Kind | Phase | Contents |
|---|---|---|---|
| `hlc/` | `hlc` | 1 | Clock ordering transcripts — send/receive sequences and the expected clock state after each |
| `merge/` | `merge` | 1 | Replica states → expected join, plus expected review signals |
| `sessions/` | `session` | 3 | Full sync transcripts — frames and expected responses |

---

## Runner requirements

Both implementations' runners must:

| Requirement | Why |
|---|---|
| Validate every vector against `schema.json` before running it | A vector Python parses and Dart rejects is a build failure with a confusing message |
| Apply **every permutation** of replica order (all `n!` for n ≤ 4) | The claim is order-independence. One order tests a fraction of it. |
| Compare in **canonical form** | Two states that are logically equal must compare equal regardless of insertion order |
| Assert `expected_signals` as a **set** | Signal order is not part of the contract; signal content is |
| Treat `"expected_signals": []` as an assertion | It asserts *no* signals. A clean merge emitting a spurious signal is a real defect (C-04, C-07). |
| Report **field-wise diffs** | "Blob mismatch" on a 40-entry series is not a debuggable failure message |

⚠ If Python runs all `n!` orders and Dart runs one, the two suites are not testing the
same claim and the comparison is theatre.

---

## Neutral field ids

Vectors **never** contain domain vocabulary. The prefix declares the lattice family:

| Prefix | Lattice | Example |
|---|---|---|
| `m_` | `MeasurementSeries` | `m_a`, `m_b` |
| `d_` | `LWWRegister` | `d_a`, `d_c` |
| `st_` | `StatusLattice` | `st_a` |
| `set_` | `ORSet` | `set_a` |
| `g_` | `GSet` | `g_a` |

Each catalogue entry declares the neutral id its vector uses, so the mapping from
domain field to vector field is written down exactly once, in a document, on purpose.

This directory is **in scope** for `check_no_domain_imports.py`; `spec/*.md` prose is
not. → [plan/repo-layout.md](../../plan/repo-layout.md) §3

---

## Adding a vector

1. Find or write the catalogue entry. If the scenario is not in the catalogue, it does
   not have a decided correct outcome yet — write the entry first.
2. Name the file `<catalogue-id>_<short_name>.json`, lowercase with underscores.
3. Set `catalogue` to the entries it covers and `phase` to the earliest phase whose
   machinery can run it.
4. Commit the **failing** vector first, then the implementation that satisfies it. The
   specification of the behaviour precedes the behaviour in the history.

---

## Status

| | Count |
|---|---|
| Schema | ✅ `schema.json`, validated in CI |
| `hlc/` vectors | 0 — Phase 1, WI-1.5 |
| `merge/` vectors | 0 — Phase 1, WI-1.15 (16 planned) |
| `sessions/` vectors | 0 — Phase 3, WI-3.10 |

Sixteen of the twenty-four catalogue entries are expressible as Phase 1 merge
vectors; the remaining eight need session, identity or enrolment machinery and are
annotated with their phase in the
[catalogue index](../conflict-catalogue.md#index).
