# ADR-0007 — Single-threaded virtual-time event loop for the simulator

**Status** accepted · **Date** 2026-08-04 · **Phase** 2

## Context

The simulator runs N virtual devices and a virtual server **inside a single
process**, with a seeded PRNG controlling everything non-deterministic:
partitions, packet loss, reordering, duplication, clock skew, clock jumps,
crashes mid-write and mid-sync, bandwidth caps, and abrupt window closure.

Its entire value rests on one property: **seed 4471 fails, and seed 4471 replays
exactly.** A simulator that finds a bug it cannot reproduce is a random number
generator with extra steps.

Three execution models were available:

| Model | |
|---|---|
| Real threads, real time | The obvious first instinct |
| `asyncio`, real time | Familiar, avoids GIL arguments |
| Single thread, virtual time, event queue | What FoundationDB and TigerBeetle do |

## Decision

**Single-threaded, single-process, an event loop over a priority queue of
scheduled events, virtual time only.** No threads, no `asyncio`, no real
sleeping.

Events are ordered by `(virtual_time, sequence)`, where `sequence` is a
monotonic counter assigned at scheduling time. That secondary key is not a
detail: without it, two events at the same virtual millisecond are ordered by
whatever the heap does with equal keys, and the run stops being reproducible in
exactly the situations that matter most — simultaneous delivery, simultaneous
partition healing.

## Consequences

**Buys**

- Determinism is a function of the seed, not of the OS scheduler. This is the
  whole point and nothing else delivers it.
- Six virtual months run in milliseconds. The Phase 3 exit criterion — a device
  carrying six months of backlog draining across 90-second windows — is
  otherwise unrunnable.
- A failing schedule is a value: it can be serialised, shrunk, committed to the
  regression corpus, and replayed on another machine years later.

**Costs**

- Nothing in the simulated system may block, sleep, or touch real I/O. That is a
  constraint on `dhara` itself, not only on `sim/` — and it is why the HLC takes
  an injected `physical_time` callable rather than reading the wall clock.
- Real concurrency bugs inside a single device's own code are **not** modelled.
  The simulator finds distributed bugs, not data races. That limit is real and
  belongs in `docs/honest-tradeoffs.md`.
- Wall-clock cost of a real sync session is not measured here. Bytes and windows
  are; latency and battery are field measurements (Phase 6).

## Alternatives

**Threads.** Rejected outright: determinism would depend on the OS scheduler,
which is precisely the thing that must be under the seed's control. A bug found
at seed 4471 would not reproduce at seed 4471.

**`asyncio`.** Better than threads — the scheduler is in-process — but event
ordering still depends on loop internals and on real timer resolution, and
virtual time would have to be faked on top of it anyway. All of the cost, none
of the benefit.

**Property-based testing alone, no simulator.** This is what Phase 1 already
does, and it is not sufficient. Property tests exercise one lattice at a time
with no network, no partitions and no crashes. The bugs this project is most
afraid of — a merge that looks correct and loses data under one specific
interleaving — live precisely in the gap between them.
