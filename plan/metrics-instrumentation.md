# Metrics and instrumentation

> Collect from week 21 onward. These are what make the write-up credible.
> — roadmap §9

That is when **field** collection starts. Simulated equivalents are collected much
earlier, because a field number with nothing to compare it to is a number with no
argument attached.

---

## 1. Provenance is part of every number

Every figure that ever appears in a document, a README, a commit body, or a talk
carries one of three tags:

| Tag | Means |
|---|---|
| `[sim]` | Produced by the deterministic simulator. Configuration must be stated alongside. |
| `[lab]` | Measured on real hardware under controlled conditions — the two-phone test, a bench run on a 2GB device. |
| `[field]` | Measured on real devices, real networks, real workers. |

**A number without a tag is a defect.** This is the discipline that makes the Phase 6
write-up survive questioning, and it costs nothing if it is habitual from Phase 2.

---

## 2. The seven headline metrics

From roadmap §9, with the operational definition each one needs to be measurable
rather than merely quotable.

### M1 — Sync success rate

**Definition:** sync attempts that reach convergence ÷ total sync attempts, per
device per day.

**Why it matters** The headline number. Compare against baseline.

⚠ "Attempt" needs a definition that does not flatter the result. An attempt is
**every time the app tries to sync**, including attempts that fail before a session
opens. Counting only sessions that got as far as a handshake produces a number that
looks excellent and means nothing.

**Baseline:** recorded pre-deployment in WI-6.2 rung 7, using whatever the centre
currently uses. Without it, M1 is a bare figure.

| Source | When |
|---|---|
| `[sim]` | Phase 3, WI-3.13 |
| `[field]` | Phase 6, WI-6.3 onward |

---

### M2 — Bytes per synced record (median, p95)

**Definition:** total bytes on the wire in a session ÷ records converged in that
session. Report median and p95 separately; the mean is dominated by the first sync
after a long offline period and is not informative.

**Why it matters** Proves the delta design earned its complexity.

**⚠ Always report against the full-state baseline.** "82 bytes per record" means
nothing alone. "82 bytes per record `[field]`, against 1,340 for full-state sync
`[sim]`" is the claim. The baseline comes from WI-3.12 rung 7.

Report the critical lane separately from bulk. A photo-heavy session's bytes-per-record
is a statement about images, not about the delta design.

| Source | When |
|---|---|
| `[sim]` | Phase 3, WI-3.12 |
| `[field]` | Phase 6, WI-6.5 |

---

### M3 — Time-to-converge after N days offline

**Definition:** wall-clock time from the first sync attempt after an offline period
of N days until full convergence, as a function of N.

**Why it matters** **The three-day limit is the thing being beaten.** This metric is
the direct answer to the problem statement in roadmap §1, and it is the one to lead
with in the write-up.

Report as a curve, not a single figure. `N=3`, `N=7`, `N=30`, `N=180`. The shape is
the finding: if it is linear in N, the delta design works; if it is superlinear,
something is retransmitting.

⚠ Wall-clock, not connected time. A device that needs six windows spread over two
days has converged in two days from the worker's point of view, and hers is the one
that matters.

| Source | When |
|---|---|
| `[sim]` | Phase 3, WI-3.13 |
| `[field]` | Phase 6, WI-6.4 |

---

### M4 — Windows required to drain a backlog

**Definition:** count of connectivity windows consumed between the first sync attempt
after an offline period and full convergence.

**Why it matters** Directly measures resumability. A design that restarts from zero
on every window closure has an unbounded value here and never converges at all on a
bad link.

**Paired with:** retransmission ratio — bytes sent ÷ bytes strictly necessary. Phase 3's
"bounded retransmission" exit criterion is this number.

| Source | When |
|---|---|
| `[sim]` | Phase 3, WI-3.13 |
| `[field]` | Phase 6, WI-6.4 |

---

### M5 — Review-queue volume per 100 records

**Definition:** review signals emitted ÷ records touched, ×100, broken down by signal
code.

**Why it matters** Roadmap §9: *"Too high = merge rules too timid. Too low =
suspicious."*

This is the only metric that is diagnostic in **both** directions, which makes it the
most interesting one. It is a measurement of the merge design, not of the system's
performance.

**Interpretation, decided in advance so the result is not rationalised afterwards:**

| Volume | Reading |
|---|---|
| > 15 per 100 | Merge rules are too timid. Supervisors will stop reading the queue, and then the queue is worse than useless. |
| 2–15 per 100 | Expected range. |
| < 1 per 100 | Suspicious. Either the deployment had almost no concurrency, or signals are not being emitted. Check the concurrency rate before concluding anything. |

⚠ Always report alongside the observed **concurrency rate**. A low review volume in a
deployment where no two workers ever touched the same record says nothing about the
merge rules.

| Source | When |
|---|---|
| `[sim]` | Phase 5, WI-5.7 |
| `[field]` | Phase 6, WI-6.4 |

---

### M6 — Battery cost per sync session

**Definition:** battery percentage delta across a sync session, excluding sessions
where the device was charging, normalised by session duration and bytes transferred.

**Why it matters** **Field workers will not adopt something that kills the phone.**
This is an adoption metric. A technically perfect sync engine that costs 8% battery
per session will be disabled by workers, and then it syncs nothing.

⚠ Battery percentage on cheap Android hardware is coarse and non-linear. Report the
distribution across many sessions rather than a precise per-session figure, and
report the sample size. Do not overclaim precision the sensor does not have.

| Source | When |
|---|---|
| `[lab]` | Phase 4, WI-4.10 |
| `[field]` | Phase 6, WI-6.1 |

---

### M7 — Crash-free session rate on 2GB devices

**Definition:** sync sessions completing without an app crash or process death ÷ total
sessions, segmented by device RAM.

**Why it matters** **The hardware constraint is real.** Anganwadi workers in
Maharashtra returned over 80,000 government-issued 2GB-RAM smartphones because they
could not run the app (roadmap §1). Any number reported on better hardware is
answering a question nobody asked.

⚠ Distinguish **crash** from **OEM process kill**. They look identical in
crash-reporting output and have completely different causes. WI-6.1 rung 6 records
the doze and background-restriction state precisely so these can be separated.

| Source | When |
|---|---|
| `[lab]` | Phase 4, WI-4.5 |
| `[field]` | Phase 6, WI-6.1 |

---

## 3. Secondary metrics

Not headline, but collected because they explain the headline numbers when a reviewer
asks why.

| Metric | Why it is worth the byte budget |
|---|---|
| Window duration distribution | The simulator's 2G profile was a guess made in week 7. This is the measurement that corrects it. |
| Window throughput distribution | Same, for the 20 kbps assumption. |
| Session outcome breakdown | Success / window closed / partition / fatal error. Explains M1's failures. |
| Chunks retransmitted per session | Explains M4. |
| Lane occupancy | Confirms the critical lane is not being starved in the field. |
| Concurrency rate | Records touched by ≥2 devices between syncs. **Required to interpret M5.** |
| Outbox depth over time | Detects a device that never fully converges. |
| Store size growth | Detects unbounded tombstone or seen-set growth. Feeds open question Q2. |
| Time since last successful sync | The revocation validity period (WI-5.3) needs real data to tune. |

---

## 4. Constraints on collection

Telemetry on this deployment is subject to the same constraints as the data it
measures, and it has a lower priority than that data.

1. **Bulk lane only.** Metrics never occupy the critical lane. Growth data does not
   queue behind telemetry any more than it queues behind a photograph.
2. **Bounded buffer, drop oldest.** A device offline six months must not fill its
   storage with metrics. Metrics are the first thing to lose.
3. **Never blocks.** No data-entry path ever waits on a metrics write.
4. **Disableable per deployment.** WI-6.0 rung 10. A supervisor-reachable off switch.
5. **No personal data.** Metrics carry device and worker identifiers and counters.
   They never carry a record's contents, a name, or a measurement value.
6. **Costs no measurable battery.** Instrumentation that changes M6 invalidates M6.

---

## 5. The comparison table

The deliverable of WI-6.5, and the most credible page in the write-up. Sketch:

| Metric | `[sim]` | `[field]` | Delta | Reading |
|---|---|---|---|---|
| M1 sync success rate | | | | |
| M2 bytes/record (median) | | | | |
| M2 bytes/record (p95) | | | | |
| M3 converge after 7d offline | | | | |
| M3 converge after 30d offline | | | | |
| M4 windows to drain | | | | |
| M5 review volume /100 | | | | |
| M6 battery per session | — | | — | no simulated equivalent |
| M7 crash-free rate | — | | — | no simulated equivalent |

⚠ **Fill in the unflattering rows.** Where the simulation was optimistic, the delta
column says so with a number. That row is worth more to a reader than any of the
green ones, because it is the row that demonstrates the numbers were not selected.
