# Wire protocol v0.1

> ## ⚠ DRAFT
>
> **This document is a draft and will change.** It is written in Phase 0 so that
> Phase 3 is implementation rather than design-while-implementing. Frozen at
> WI-3.14, after the six-month backlog scenario has been run and the design has met
> a simulated network.
>
> **Do not pin a consumer to this.** Path dependencies until week 14
> (roadmap §4). What Phase 3 may change is listed in §10.

**Protocol version on the wire:** `1` (an integer, see [DOUBTS.md D-06](../DOUBTS.md#d-06))

---

## 1. What this protocol is shaped by

One number: **a 90-second window at 20 kbps is 225 KB in the best case, and the best
case does not happen.**

| Requirement | Because |
|---|---|
| Version vectors | The server computes what the client is missing without either side enumerating its state |
| Delta transmission | Sending a full record to convey one new measurement wastes the window |
| Chunked, acknowledged, resumable | **The window closing mid-transfer is the normal case, not the exception** |
| Priority lanes | A 400 KB image blocking 2 KB of growth data is the most common real-world failure |
| Idempotent application | An acknowledgement lost in flight causes a resend. Replay must be a no-op. |

⚠ Every design below assumes **the session will be interrupted.** A protocol that
treats interruption as an error path rather than the expected path does not work on
this network.

---

## 2. Session lifecycle

```
        ┌──────────┐
        │   IDLE   │◀──────────────────────────────┐
        └────┬─────┘                               │
             │ open                                │
             ▼                                     │
      ┌─────────────┐   no common version    ┌─────┴─────┐
      │  HANDSHAKE  │──────────────────────▶ │  REFUSED  │
      └──────┬──────┘                        └───────────┘
             │ versions agreed
             ▼
      ┌─────────────┐
      │  NEGOTIATE  │  exchange version vectors, compute deltas both ways
      └──────┬──────┘
             │
             ▼
      ┌─────────────┐  ack watermark advances per lane
      │    PUSH     │◀─┐  client → server
      └──────┬──────┘  │
             │─────────┘
             ▼
      ┌─────────────┐
      │    PULL     │◀─┐  server → client
      └──────┬──────┘  │
             │─────────┘
             ▼
      ┌─────────────┐
      │   COMMIT    │  both sides durably record the new watermarks
      └──────┬──────┘
             │
             ▼
      ┌─────────────┐
      │    CLOSE    │
      └─────────────┘

  Abrupt close is reachable from EVERY state and is the normal path.
  In every state the invariant is the same: durable state is never
  ahead of what the peer has been told, and never behind what the
  peer has been told was received.
```

### Failure edge for every state

Every transition has one, because on this network every one of them will be taken.

| State | Abrupt close means | Recovery |
|---|---|---|
| `HANDSHAKE` | Nothing was exchanged | Retry from `IDLE`. No state to reconcile. |
| `NEGOTIATE` | Vectors possibly exchanged, no data moved | Retry from `IDLE`. Vectors are idempotent to re-exchange. |
| `PUSH` | Some chunks acked, some in flight, one partial | Resume at the client's persisted watermark. Partial chunk discarded and re-sent whole. |
| `PULL` | Same, other direction | Resume at the server's record of the client's watermark. |
| `COMMIT` | The dangerous one — one side may have committed and the other not | Both sides re-derive from their persisted watermarks. A commit that did not reach the peer costs a re-send, never a loss. |
| `CLOSE` | Indistinguishable from success | Harmless. Next session's `NEGOTIATE` reconciles. |

⚠ **`COMMIT` is where a silent-loss bug would live.** The ordering rule is absolute:
**persist, then acknowledge.** Acking before persisting means a crash loses data the
peer believes was delivered. The reverse costs at most one duplicated chunk, and §5
makes duplicates free.

---

## 3. Chunk framing

```
┌────────────┬───────────┬────────┬─────────┬──────────┬─────────┬──────────┐
│ proto_ver  │ session   │ lane   │ seq     │ total    │ payload │ checksum │
│ u8         │ u128      │ u8     │ u32     │ u32      │ bytes   │ u32      │
└────────────┴───────────┴────────┴─────────┴──────────┴─────────┴──────────┘
```

| Field | Notes |
|---|---|
| `session` | Identifies a logical sync across reconnections. A resumed session reuses it. |
| `lane` | §6. Determines scheduling priority. |
| `seq` | Per-lane, monotonic within a session. |
| `total` | Chunks in this lane's transfer. `0` means unknown/streaming. |
| `checksum` | Over the payload. A corrupted chunk is detected and discarded, never applied. |

### Sizing

Chunk size is **adaptive to the measured link rate**, bounded so that one chunk is a
small fraction of a window. Small enough that losing one costs little; large enough
that per-chunk overhead does not dominate at 20 kbps.

### Packing and the record-size bound

Multiple small records may be packed into one chunk. **A record is never split across
a chunk boundary.**

⚠ This is a deliberate simplification with a real cost: a record larger than one chunk
cannot be sent. Record size is bounded in the schema and oversize is rejected **at
write time, loudly** — never at sync time, where the worker has already left the
village.

The alternative, record fragmentation and reassembly, is a materially harder state
machine and does not earn its complexity for growth data. Photos take a different path
entirely (§6).

---

## 4. Version vectors and deltas

A `VersionVector` maps `node_id → max HLC seen from that node`. It is itself a
lattice: join is the pointwise maximum.

`NEGOTIATE` exchanges vectors. Each side computes the other's gap and sends only
that.

**Granularity:** per-replica vectors, with per-record vectors only for records under
active concurrent edit. A vector per record for 300 records × 20 devices is ~6,000
entries against a 225 KB window — it does not fit. Per-replica vectors are coarse
(they can indicate a record needs syncing when it does not) but the error costs
bandwidth, never correctness.

> Open: the arithmetic depends on a beneficiary-count assumption that has not been
> checked against a real centre. → [plan/open-questions.md](../plan/open-questions.md) Q6

**The delta correctness property**, which is a property test and not a code review:

```
join(peer_state, delta_since(peer_vv)) == join(peer_state, full_state)
```

⚠ For `LWWRegister`, `delta_since` must include **history** entries the peer lacks,
not only the current winner. Otherwise retained-losers is silently violated over the
wire — a bug that passes every unit test because the local state is correct.

---

## 5. Operation identity and idempotence

**Operation id:** `(device_id, hlc)`. Globally unique without coordination, given
unique device ids — which is why C-24 must fail at enrolment rather than at merge.

| Rule | |
|---|---|
| Re-application of a seen operation | A **no-op**. Not an error, not a duplicate. |
| Delay tolerance | Unbounded. A duplicate four hours later is still a no-op. |
| Seen-set bound | The version vector is the frontier. Only operations **above** it are held explicitly. |

⚠ Without that last rule the seen-set grows without bound across a six-month offline
period, and the device runs out of storage before it runs out of patience.

---

## 6. Priority lanes

| Lane | Id | Carries | Rule |
|---|---|---|---|
| `critical` | `0` | Measurements, status, demographics, review signals | Strict priority. Never delayed by any other lane. |
| `bulk` | `1` | Blob bytes, telemetry | Bounded allowance per window |

**Scheduling:** strict priority, with preemption **at chunk boundaries, not
mid-chunk.** Mid-chunk preemption puts partial frames on the wire and makes
reassembly materially harder; chunks are sized so boundary granularity is sufficient.

**Starvation protection:** a small guaranteed `bulk` allowance per window. Strict
priority with no allowance means photos never sync on a device that always has
pending measurements — technically correct, operationally useless.

**Independent watermarks per lane.** Closing a window mid-`bulk` must not rewind
`critical` progress.

### Blobs

Content-addressed, referenced by hash from the record, out of band.

- The record's metadata is **complete, valid and mergeable without the blob present**
  (C-18).
- Blobs deduplicate by content hash across records for free.
- `dhara` never compresses, resizes or inspects an image — that requires knowing what
  the image is *for*. It moves opaque bytes with a priority.

---

## 7. Version negotiation

`HANDSHAKE` exchanges supported protocol versions; the highest mutually supported one
is selected. No common version ⇒ `REFUSED`.

⚠ **A refusal must never clear the client's outbox.** A device offline for six months
reconnecting to a newer server is exactly the user this system exists to serve;
losing her unsynced work to a *version check* is the most avoidable data-loss bug
available, and it has shipped in real systems.

`REFUSED` is a terminal state for the session, not for the data.

---

## 8. Error taxonomy

| Class | Meaning | Behaviour |
|---|---|---|
| `retryable` | Window closed, partition, timeout, transient server error | Retry with **jittered** exponential backoff |
| `fatal` | No common protocol version, authentication failure, revoked device | Never retried. Surfaced to the operator. Outbox preserved. |
| `needs_review` | An operation merged but produced a review signal | **Does not fail the session.** The signal syncs like any other data. |

⚠ Jitter is not a detail. When the tower recovers, every device in the block
reconnects in the same second; without jitter they collide, back off together, and
collide again.

---

## 9. Flow control

- In-flight bytes are capped to the **estimated window budget**. Queuing more than one
  window of work wastes the window on data that cannot land.
- Window budget is estimated from measured throughput, not configured.

---

## 10. What Phase 3 may change

Listed explicitly so that "draft" is a specific claim rather than a disclaimer.

| Area | Expected to change |
|---|---|
| Chunk header layout | Field widths and ordering, once real sizes are measured |
| Adaptive chunk sizing | The whole algorithm; currently unspecified |
| Version vector granularity | The hybrid rule in §4, pending Q6 |
| Lane count | A third lane may be needed if telemetry competes with blobs |
| Bulk allowance | The value, and whether it is per-window or per-session |
| Blob transfer | Whether blobs are chunked through the same framing or a separate mechanism |
| `COMMIT` semantics | Whether a two-phase commit is needed or the watermark rule suffices |

Not expected to change, because the catalogue depends on them:

- persist-then-acknowledge ordering
- operation id as `(device_id, hlc)`
- idempotent re-application
- strict critical-lane priority
- refusal never clearing the outbox
- metadata mergeable without its blob
