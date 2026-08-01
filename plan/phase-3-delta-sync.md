# Phase 3 — Delta sync and session protocol

**Weeks 10–13 · ~56 hours · ~120 commits**

> Version vectors, delta computation, chunked resumable transfer, priority queues,
> idempotent application. — roadmap §8, Phase 3

**Exit criteria (roadmap):** in simulation, a device carrying **six months** of
accumulated offline data fully converges across a sequence of 90-second / 20 kbps
windows with random disconnection — zero duplication, zero loss, bounded
retransmission. Record bytes-per-record as a headline metric.

---

## The constraint this phase is shaped by

On 2G, the connection is a 90-second window at 20 kbps that dies mid-transfer. That
is **225 KB per window in the best case**, and the best case does not happen.
"POST the whole changeset" is not an option (roadmap §6.3).

Every design decision below follows from that one number:

| Requirement | Because |
|---|---|
| Version vectors per (replica, record) | The server must compute exactly what the client is missing, without the client uploading a manifest of everything it has |
| Delta-state transmission | Sending full state for a record with 40 measurements to convey one new one wastes the window |
| Chunked transfer with acknowledged offsets | The window closes mid-transfer as the normal case. Resume from the last ack, never from zero. |
| Priority lanes | **A 400 KB image blocking 2 KB of growth data is the single most common real-world failure.** |
| Idempotent application | A chunk acked but not recorded as acked will be resent. Replay must be a no-op. |

⚠ **This phase runs against the simulator from day one.** Phase 2 exists so that
every WI here can be validated under partitions, window closure, and crashes as it
is written, not after. If you find yourself writing session code and testing it with
a unit test on a healthy network, stop and wire it into the simulator instead.

---

## Work items

### WI-3.0 — Version vectors

**Why** The mechanism by which the server computes what a client is missing without
either side enumerating its state.

**Touches** `dhara/version_vector.py`

**Design notes**
- `VersionVector` maps `node_id → max HLC seen from that node`.
- It is itself a lattice: `join` is the pointwise max. Reuse the Phase 1 law harness.
- **Granularity decision:** per-replica vectors, with per-record vectors only for
  records under active concurrent edit. A vector per record for 300 children × 20
  devices is 6,000 entries to exchange in a 225 KB window — it does not fit. Record
  this trade-off; it is the kind of thing an interviewer will probe.

**Commit ladder**
1. `feat(vv): add version vector as a node-to-hlc mapping`
2. `feat(vv): implement join as the pointwise maximum`
3. `test(vv): property - the three lattice laws over 10k orders`
4. `feat(vv): add dominates and concurrent-with comparisons`
5. `test(vv): concurrency detection matches the causal-order ground truth`
6. `feat(vv): add a compact wire encoding with delta-encoded node ids`
7. `test(vv): encoding round-trips and is smaller than the naive form`
8. `feat(vv): compute the set difference - what the peer has not seen`
9. `test(vv): set difference is exact against the simulator oplog`
10. `docs: add ADR-0008 on version vector granularity and its size trade-off`

---

### WI-3.1 — Delta-state computation `[gate]`

**Why** The difference between sending 40 measurements and sending one.

**Touches** `dhara/delta.py`

**Depends on** WI-3.0

**Design notes**
- Each lattice gains `delta_since(vv) -> Self`, returning the smallest state whose
  join with the peer's state yields the full join.
- **The correctness property that must hold for every lattice:**
  `join(peer_state, delta_since(peer_vv)) == join(peer_state, full_state)`.
  That is a property test, not a code review.
- Deltas are themselves lattice values, so they compose: a device that misses three
  syncs receives one merged delta, not three.

**Commit ladder**
1. `feat(delta): add delta_since to the Lattice protocol`
2. `feat(gset): implement delta_since returning only unseen elements`
3. `feat(series): implement delta_since returning only unseen entries`
4. `feat(lww): implement delta_since including history entries the peer lacks`
5. `feat(orset): implement delta_since covering both adds and observed removes`
6. `feat(status): implement delta_since`
7. `test(delta): property - joining a delta equals joining the full state`
8. `test(delta): property - deltas compose associatively`
9. `test(delta): a delta is never larger than the full state`
10. `feat(delta): compute a record-level delta across all fields of a schema`
11. `test(delta): record delta omits fields with no unseen changes entirely`
12. `sim: assert delta sync converges to the same state as full-state sync`

⚠ Rung 4 is the subtle one. An LWW register's delta must include **history** entries
the peer has not seen, not just the current winner — otherwise `keep_losers` is
silently violated over the wire, which is exactly the class of bug that passes every
unit test. Rung 7's property is what catches it.

⚠ Rung 12 is the strongest test in this WI: run the same scenario twice, once with
full-state sync and once with delta sync, and assert identical final state. Any
divergence is a delta bug, localised immediately.

---

### WI-3.2 — Operation identity and idempotence

**Why** Catalogue C-22, C-23. Replay must be a no-op, not an error and not a
duplicate.

**Touches** `dhara/session.py`, `dhara/store.py`

**Commit ladder**
1. `feat(session): define operation ids as (device_id, hlc) pairs`
2. `feat(session): reject an operation id that is not well formed`
3. `feat(session): record applied operation ids in a durable seen-set`
4. `feat(session): make re-application of a seen operation a no-op`
5. `test(session): applying the same operation twice changes nothing - C-22`
6. `test(session): a restored backup replaying synced ops is rejected - C-23`
7. `feat(session): bound the seen-set using the version vector as the frontier`
8. `test(session): an operation below the vv frontier is rejected without lookup`
9. `sim: duplicate delivery separated by hours is still idempotent`

⚠ Rung 7 is what stops the seen-set growing without bound over six months offline.
The version vector is the compact frontier; the explicit seen-set only needs to hold
operations *above* it. Without this the device runs out of storage before it runs out
of patience.

---

### WI-3.3 — Chunk framing

**Touches** `dhara/session.py`, `spec/protocol-v0.1.md`

**Commit ladder**
1. `spec: finalise the chunk frame header layout`
2. `feat(session): encode a payload into size-bounded chunks`
3. `feat(session): add a per-chunk sequence number and total count`
4. `feat(session): add a per-chunk checksum`
5. `test(session): a corrupted chunk is detected and not applied`
6. `feat(session): make the chunk size adaptive to the measured link rate`
7. `test(session): chunk size stays within the window budget on the 2G profile`
8. `feat(session): pack multiple small records into one chunk`
9. `test(session): packing never splits a record across a chunk boundary`

⚠ Rung 9 is a deliberate simplification with a cost: a record larger than one chunk
cannot be sent. Bound record size in the schema and reject oversize at write time,
loudly. The alternative — record fragmentation and reassembly — is a materially
harder state machine and does not earn its complexity for growth data. Photos take a
different path entirely (WI-3.7).

---

### WI-3.4 — Acknowledged offsets and resumption `[gate]`

**Why** *"Resume from the last ack, never from zero."* This is the WI the whole
bandwidth argument rests on.

**Touches** `dhara/session.py`

**Depends on** WI-3.3

**Commit ladder**
1. `feat(session): track the highest contiguously acknowledged chunk per lane`
2. `feat(session): persist the ack watermark before acknowledging to the peer`
3. `feat(session): resume a transfer from the watermark on a new session`
4. `test(session): resumption after chunk 7 of 20 restarts at 8 - catalogue C-21`
5. `test(session): zero chunks are retransmitted on a clean resume`
6. `feat(session): handle an ack lost in flight by tolerating a resent chunk`
7. `test(session): a lost ack costs at most one duplicated chunk`
8. `feat(session): expire a stale session and restart from the durable watermark`
9. `sim: run resumption against abrupt mid-byte window closure`
10. `sim: assert bounded retransmission across 100 window closures`

⚠ Rung 2's ordering is the classic bug and it must be this way round: **persist,
then ack.** Acking before persisting means a crash loses data the peer believes was
delivered — silent loss, which is the one thing this project cannot have. The reverse
ordering costs at most a duplicate chunk, and WI-3.2 makes duplicates free.

⚠ Rung 9 is the payoff for Phase 2's WI-2.6 rung 4. Closing the window *between*
messages tests almost nothing; closing it mid-byte is the real network.

---

### WI-3.5 — Session state machine

**Touches** `dhara/session.py`, `spec/protocol-v0.1.md`

**Commit ladder**
1. `spec: finalise the session state machine with all failure edges`
2. `feat(session): add the state enum and the legal transition table`
3. `feat(session): implement handshake and negotiate`
4. `feat(session): implement the push phase`
5. `feat(session): implement the pull phase`
6. `feat(session): implement commit and close`
7. `feat(session): reject an illegal transition loudly rather than ignoring it`
8. `test(session): every legal transition is exercised`
9. `test(session): an abrupt close in each state leaves recoverable durable state`
10. `feat(session): add a session id so a resumed session is identifiable`
11. `test(session): a session abandoned mid-push resumes without data loss`

Rung 9 is a loop over every state, not a single test. On this network **abrupt close
is the normal path**, so "what happens if the connection dies here" must have an
answer for every state, and the cheapest way to guarantee that is a parameterised
test over the state enum.

---

### WI-3.6 — Version negotiation

**Why** A device offline six months reconnects speaking an older protocol. →
`ci-and-tooling.md` §6

**Touches** `dhara/session.py`, `spec/versioning.md`

**Commit ladder**
1. `spec: define protocol version negotiation in the handshake`
2. `feat(session): exchange supported protocol versions during handshake`
3. `feat(session): select the highest mutually supported version`
4. `feat(session): fail cleanly when there is no common version`
5. `test(session): an unsupported client is refused without losing its outbox`
6. `spec: add the versioning policy and the migration-note requirement`
7. `docs: document the six-month-old-client upgrade path`

⚠ Rung 5 is the requirement that makes this WI worth doing now rather than later.
A refusal that clears the device's outbox is a data-loss bug caused by a *version
check* — the most avoidable kind, and one that has shipped in real systems.

---

### WI-3.7 — Priority lanes `[gate]`

**Why** Roadmap §6.3: *"Growth data must never queue behind a photograph… A 400 KB
image blocking 2 KB of growth data is the single most common real-world failure."*

**Touches** `dhara/queue.py`

**Commit ladder**
1. `feat(queue): add named lanes with a strict priority order`
2. `feat(queue): schedule chunks by lane priority within a window`
3. `feat(queue): add the critical lane for measurements and status`
4. `feat(queue): add the bulk lane for photos and attachments`
5. `test(queue): a full bulk lane never delays a critical-lane chunk`
6. `test(queue): a critical item arriving mid-transfer preempts at a chunk boundary`
7. `feat(queue): add per-lane ack watermarks so lanes resume independently`
8. `test(queue): closing a window mid-bulk does not rewind critical progress`
9. `feat(queue): add lane starvation protection with a bounded bulk allowance`
10. `test(queue): the bulk lane eventually drains on a link with spare capacity`
11. `sim: six months of photos never delays a measurement past one window`

⚠ Rung 6: preemption happens **at a chunk boundary, not mid-chunk.** Mid-chunk
preemption means partial frames on the wire and a much harder reassembly problem.
Chunks are sized so that one chunk is a small fraction of a window, which makes
boundary-granularity preemption sufficient.

⚠ Rung 9 is the counterweight to rung 5. Strict priority with no allowance means
photos never sync on a device that always has pending measurements — technically
correct, operationally useless. A small guaranteed bulk allowance per window fixes it
without endangering the critical lane.

---

### WI-3.8 — Photo handling

**Why** Open question Q4: separate content-addressed blob store, or in-band chunks?

**Touches** `dhara/queue.py`, `spec/protocol-v0.1.md`

**Decision to record:** content-addressed, out-of-band, referenced by hash from the
record. The record's metadata syncs in the critical lane and is complete without the
blob; the blob follows in the bulk lane. This is what makes catalogue C-18 work —
metadata merges without waiting on 400 KB.

**Commit ladder**
1. `spec: define blob references as content hashes carried in the record`
2. `feat(queue): treat blobs as opaque content-addressed objects`
3. `feat(queue): sync blob references in the critical lane, bytes in the bulk lane`
4. `test(queue): a record is complete and mergeable without its blob present`
5. `test(queue): metadata edited on another device merges before the blob arrives - C-18`
6. `feat(queue): deduplicate blobs by content hash across records`
7. `docs: resolve open question Q4 - content-addressed and out of band`

⚠ `dhara` never compresses or resizes an image. That is the consumer's job — it
requires knowing what the image is *for*. `dhara` moves opaque bytes with a
priority. Keeping this boundary is what stops the queue layer growing a media
pipeline.

---

### WI-3.9 — Backpressure and retry

**Touches** `dhara/session.py`, `spec/protocol-v0.1.md`

**Commit ladder**
1. `spec: define the error taxonomy - retryable, fatal, needs-review`
2. `feat(session): classify every failure into the taxonomy`
3. `feat(session): retry retryable failures with jittered exponential backoff`
4. `feat(session): never retry a fatal failure`
5. `feat(session): surface needs-review failures without blocking the session`
6. `test(session): backoff jitter prevents synchronised retry across devices`
7. `feat(session): cap in-flight bytes to the estimated window budget`
8. `test(session): the session does not queue more than one window of work`
9. `sim: twenty devices reconnecting simultaneously do not synchronise their retries`

Rung 9 models a real event: the power comes back, or the tower recovers, and every
device in the block reconnects in the same second. Without jitter they collide,
back off together, and collide again.

---

### WI-3.10 — Session conformance vectors `[spec]`

**Touches** `spec/conformance/sessions/*.json`

**Commit ladder**
1. `spec: define the session transcript vector format`
2. `spec: add a session vector for a clean full sync`
3. `spec: add a session vector for resumption after mid-transfer close`
4. `spec: add a session vector for duplicate chunk delivery`
5. `spec: add a session vector for lane priority under contention`
6. `spec: add a session vector for version negotiation failure`
7. `spec: add a session vector for a six-month delta`
8. `feat(conformance): run session transcript vectors in the python suite`
9. `spec: add session vectors for catalogue entries C-21 through C-23`

These are what Phase 4's Dart client must reproduce exactly. Write them as
transcripts of frames and expected responses, so they test the wire behaviour rather
than internal state.

---

### WI-3.11 — Simulator integration

**Touches** `sim/device.py`, `sim/server.py`, `sim/scenario.py`

**Commit ladder**
1. `sim: replace direct state exchange with real sync sessions`
2. `sim: model window opening and closing as session lifecycle events`
3. `sim: generate scenarios with realistic sync-attempt cadence`
4. `sim: add an invariant that no chunk is applied twice`
5. `sim: add an invariant that retransmission stays bounded`
6. `sim: add an invariant that the critical lane is never starved`
7. `test(sim): the phase 2 mutation suite still detects all six mutations`

⚠ Rung 7 is not optional. Replacing direct state exchange with a real session layer
changes what the simulator explores. If the mutation suite's detection times get
worse, the harness has lost sensitivity and must be recalibrated **before** the
sweep in WI-3.13 is believed.

---

### WI-3.12 — Metrics instrumentation

**Touches** `dhara/metrics.py`, `bench/`

**Commit ladder**
1. `feat(metrics): add counters for bytes sent, chunks and retransmissions`
2. `feat(metrics): add per-lane and per-session breakdowns`
3. `feat(metrics): keep metrics allocation-light and I/O free`
4. `feat(bench): add a bytes-per-record harness over a fixed scenario`
5. `feat(bench): add a windows-to-drain harness for a backlog`
6. `test(metrics): counters agree with the simulator's observed byte totals`
7. `docs: record the baseline bytes-per-record for full-state sync`

Rung 7 establishes the baseline the delta design is measured against. Without a
full-state number to compare to, "82 bytes per record" is a figure with no meaning.

---

### WI-3.13 — The six-month backlog scenario `[gate]`

**Why** Direct exit criterion.

**Scenario:** one device, six virtual months offline, a realistic write volume
(~25 beneficiaries × ~8 fields × weekly measurements ≈ 5,000 operations), draining
across 90-second / 20 kbps windows with random disconnection.

**Commit ladder**
1. `sim: add the six-month-offline preset with a realistic write volume`
2. `sim: drain the backlog across seeded 90 second 20 kbps windows`
3. `test(sim): the backlog converges fully with zero duplication`
4. `test(sim): the backlog converges fully with zero loss`
5. `test(sim): retransmission stays under the bounded threshold`
6. `test(sim): critical-lane data converges before bulk-lane data`
7. `sim: run the scenario across 10k seeds with random disconnection points`
8. `docs: record windows-to-drain and bytes-per-record for the backlog scenario`
9. `docs: compare delta sync against the full-state baseline`

**Headline metrics to record** (they go in the README and the Phase 6 write-up):
- median and p95 **bytes per synced record**
- **windows required to drain** six months of backlog
- retransmission ratio
- time-to-converge in virtual days

---

### WI-3.14 — Freeze protocol v0.1 `[spec]` `[gate]`

**Why** Phase 4 wires CGMS to pinned tags. The protocol must stop moving first.

**Touches** `spec/protocol-v0.1.md`, `spec/versioning.md`

**Commit ladder**
1. `spec: remove the draft marker from protocol v0.1`
2. `spec: record what changed between the phase 0 draft and the frozen version`
3. `spec: state the compatibility guarantee for v0.1 clients`
4. `spec: define the change process for post-freeze protocol edits`
5. `docs: add the architecture document describing the full sync path`
6. `docs: update the README with the phase 3 headline metrics`

---

### WI-3.15 — Phase 3 exit review `[gate]`

**Commit ladder**
1. `docs(plan): record phase 3 exit checklist results`
2. `docs: add changelog entry for delta sync and the session protocol`
3. `chore: tag phase-3-complete`

---

## Exit checklist

- [ ] A device carrying **six months** of accumulated offline data fully converges
      across a sequence of 90-second / 20 kbps windows with random disconnection.
- [ ] **Zero duplication** across 10,000 seeds of that scenario.
- [ ] **Zero loss** across 10,000 seeds of that scenario.
- [ ] **Bounded retransmission** — threshold stated, measured, and met.
- [ ] **Bytes-per-record recorded** (median and p95) against a full-state baseline.
- [ ] Delta sync and full-state sync produce identical final state, asserted in
      simulation.
- [ ] Resumption restarts at the last acked chunk; persist-then-ack ordering verified.
- [ ] Critical lane never starved by bulk; bulk lane eventually drains.
- [ ] A record is mergeable without its blob present.
- [ ] Version negotiation refuses cleanly without clearing a client's outbox.
- [ ] Every session state has a tested abrupt-close path.
- [ ] The Phase 2 mutation suite still detects all six mutations within budget.
- [ ] `protocol-v0.1.md` frozen with a stated compatibility guarantee.
- [ ] `phase-3-complete` tag pushed.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| Delta computation silently drops LWW history | Conformance passes, no-loss invariant fails rarely | WI-3.1 rung 7's property is the guard. If it was skipped, add it before debugging anything else. |
| Ack-before-persist | Rare loss under crash injection only | Invert the ordering (WI-3.4 rung 2). Duplicates are free; loss is not. |
| Seen-set grows unbounded | Memory growth in the six-month scenario | The version vector is the frontier (WI-3.2 rung 7). |
| Priority inversion under contention | Measurements arriving after photos in the sim | WI-3.7 rung 5. Check the scheduler is priority-strict, not weighted round-robin. |
| Harness sensitivity lost after session integration | Mutations take longer to detect than in Phase 2 | Recalibrate the generator before trusting the backlog sweep. |
| Protocol keeps changing after freeze | CGMS breaking repeatedly in Phase 4 | Post-freeze changes go through WI-3.14 rung 4's process and get a migration note. |
| Phase runs long | Week 13 with the backlog scenario unrun | Cut WI-3.8 rung 6 and WI-3.9 rung 7-8 to stretch. Do **not** cut WI-3.13; it is the exit criterion. |
