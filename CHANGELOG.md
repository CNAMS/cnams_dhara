# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning is [SemVer](https://semver.org/), but pre-1.0 the **wire protocol
version** is tracked separately and is the one consumers actually depend on — see
[spec/versioning.md](spec/versioning.md).

One entry per phase, written at the phase exit review.

---

## [Unreleased]

### Added

- Design document and 24-week roadmap.
- Execution plan: 7 phases, 105 work items, per-work-item commit ladders
  ([EXECUTION.md](EXECUTION.md), [plan/](plan/)).
- Doubt register recording every assumption made during execution
  ([DOUBTS.md](DOUBTS.md)).

---

## Planned releases

| Version | Phase | Meaning |
|---|---|---|
| `v0.1.0-rc` | 4 | Wire protocol frozen. CGMS switches from path dependencies to a pinned tag. |
| `v0.1.0` | 6 | Field data collected, protocol spec published. |

Phase completions are marked with annotated `phase-N-complete` tags whose bodies
carry the exit checklist with the measured results.
