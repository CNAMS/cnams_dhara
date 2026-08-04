# ADR-0002 — Two implementations against one spec, not a Rust core

**Status** accepted · **Date** 2026-08-01 · **Phase** 0

## Context

The client is Flutter/Dart; the server is Python/FastAPI. The merge logic has to run
on both.

Three options: a Rust core with FFI bindings to both; one implementation with the
other calling it over the network; or two implementations validated against shared
conformance vectors.

The Rust core is the maximalist path and is genuinely better on the merits —
one implementation, no cross-language serialisation problem, better performance on
2GB hardware. It is also the entire timeline. FFI debugging on Android eats weeks, and
those weeks come directly out of the simulator and the field deployment, which are the
two things that make this project credible.

## Decision

**Two implementations, one spec, shared conformance vectors.**

- Python — server-side plus the simulator.
- Dart — client-side, inside the Flutter app.
- `spec/conformance/` — language-agnostic JSON fixtures both must pass.

CI runs both against the identical vector tree. **Divergence is a build failure.**

## Consequences

**Buys**

- An **interoperability story** rather than a "trust me, it's the same code" story.
  This is how real protocol implementations are verified, and it is a stronger claim
  than a single shared core can make.
- The spec becomes load-bearing rather than documentation. An ambiguity in it shows up
  as two implementations disagreeing, which is a defect report with a location.
- No FFI, no build toolchain risk on Android, no debugging across a language boundary
  on a 2GB device.

**Costs**

- Every behaviour is written twice.
- **Canonical serialisation must be byte-identical across two languages**, including
  numeric formatting. This is a real problem, not a formality — Python's `repr` and
  Dart's `toString` disagree on some floats, and two replicas that serialise the same
  logical state differently will see a spurious delta and resend forever.
  → [DOUBTS.md D-04](../../DOUBTS.md#d-04)
- Performance on 2GB hardware is whatever Dart gives; there is no native fallback.

**The failure mode to guard against**

If the Dart port is written with the Python source open beside it, it is a
transliteration, the two implementations share every misunderstanding, and the
conformance suite confirms only that the same thing was typed twice.

The working rule (WI-4.11, risk R9): implement Dart from the spec and its vectors;
consult Python only when a vector fails and the spec is genuinely ambiguous — and when
that happens, **fix the spec.** The resulting list of ambiguities is the evidence that
the two implementations are independent.

## Alternatives

**Rust core with FFI.** Deferred to v0.2, and it is a legitimate upgrade if systems
credibility becomes the goal. The assessment of where it would have been better is a
required section of `docs/honest-tradeoffs.md` (WI-6.6).

**Server-side only, client calls over the network.** Rejected outright: the premise of
the project is that there is no network.
