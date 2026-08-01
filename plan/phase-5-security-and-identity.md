# Phase 5 — Security and identity

**Weeks 17–20 · ~56 hours · ~95 commits**

> SQLCipher, per-device keys, enrolment and revocation. Accept-then-reconcile
> duplicate detection. Supervisor review queue. — roadmap §8, Phase 5

**Exit criteria (roadmap):**
- A revoked device's local store is unreadable without that device coming online.
- A duplicate registration created at two centres is detected and reconciled, and
  both devices update local references without breaking.

---

## The two hard requirements

Everything in this phase is ordinary except two constraints, and both rule out the
obvious design.

**1. Revocation without the device's cooperation.**

> Server-side revocation that renders a lost device's data unreadable *without
> requiring that device to come back online*. This constraint rules out "send a wipe
> command" designs. — roadmap §6.5

A phone that is stolen, sold, or simply never turned on again will never receive a
wipe command. So the design must be one where the *absence* of contact with the
server causes the data to become unreadable. That means **the device cannot hold a
complete key**.

**2. Duplicate resolution without breaking local references.**

> The hard part: devices hold local references to the losing UUID and must not break
> when it is superseded. Requires a tombstone-with-forwarding-pointer design.
> — roadmap §6.4(a)

A device that has been offline for a month has operations, photos, and UI state
pointing at a UUID the server has since merged away. Those must keep working.

---

## Slip policy for this phase

Roadmap §10: *"Phases 5–6 can slip a semester without invalidating the work."*

If week 17 arrives with Phase 4 incomplete, **finish Phase 4 first.** A working,
verified sync engine without device revocation is a coherent artifact. A half-built
crypto layer on top of an unfinished client is not.

If this phase must be cut down, the order to cut is:
1. `[stretch]` WIs (bloom filters, key rotation) — cut first, cost nothing downstream
2. Duplicate reconciliation (WI-5.7 … WI-5.10) — defer, but keep the tombstone design
3. **Never** cut the at-rest encryption (WI-5.0 … WI-5.2). Children's health data on
   a shared phone with no encryption is not a defensible v0.1 at all.

---

## Work items

### WI-5.0 — Threat model `[spec]` `[research]`

**Why** A security implementation without a written threat model is a set of
mechanisms with no stated purpose, and it cannot be evaluated.

**Touches** `spec/security-model.md`

**Done when** Each threat has a mechanism, and each mechanism traces to a threat.
Anything with no threat gets deleted; anything with no mechanism is stated as an
accepted risk.

**Threats in scope**

| # | Threat | In scope |
|---|---|---|
| T1 | Phone lost, stolen, or resold with data at rest | Yes — the driving threat |
| T2 | Phone returned to the government pool and reissued to another worker | Yes |
| T3 | Multiple workers sharing one phone, each seeing only their own scope | Yes |
| T4 | Operation misattributed to the wrong worker | Yes |
| T5 | Network attacker reading sync traffic | Yes — TLS, plus the operations are signed |
| T6 | Malicious device forging another device's operations | Yes |
| T7 | Compromised server | **No** — accepted. Stated explicitly. |
| T8 | Physical attacker with the unlocked phone and the worker's credentials | **No** — accepted. |
| T9 | Rooted device extracting keys from the keystore | **Partially** — hardware-backed where available, degraded otherwise. Stated. |

**Commit ladder**
1. `spec: add the security model with assets, actors and trust boundaries`
2. `spec: enumerate threats T1 through T9 with in-scope decisions`
3. `spec: state the accepted risks explicitly - compromised server, unlocked device`
4. `spec: state the key hierarchy from device key to record encryption`
5. `spec: state the revocation requirement and why wipe commands are excluded`
6. `docs: add ADR-0009 on the revocation design and its constraints`

⚠ Rung 3 is what makes this document credible rather than aspirational. A threat
model that claims to cover everything covers nothing. T7 and T8 being written down as
accepted is more convincing than a longer list of mechanisms.

---

### WI-5.1 — Per-device keys and enrolment

**Why** Roadmap §6.5: per-device keys issued at enrolment, **never derived from a
user password.** Workers share devices and change passwords; a password-derived key
makes revocation impossible and shared-device access incoherent.

**Touches** `dhara/crypto.py`, `dhara-dart/lib/src/crypto.dart`

**Commit ladder**
1. `feat(crypto): define the key hierarchy - device key, data key, record keys`
2. `feat(crypto): generate a device keypair at enrolment`
3. `feat(crypto): register the device public key with the server during enrolment`
4. `feat(crypto): store the private key in platform secure storage`
5. `feat(crypto): fall back with an explicit warning when hardware backing is absent`
6. `test(crypto): the device key is never derived from a password`
7. `test(crypto): enrolment is idempotent and re-enrolment issues a new key`
8. `feat(crypto): sign every operation with the originating device key`
9. `test(crypto): an operation signed by an unknown device is rejected - threat T6`
10. `feat(identity): detect a duplicate device id at enrolment and refuse - C-24`
11. `test(crypto): key material never appears in a log line or an error message`

Rung 10 closes catalogue C-24, which WI-2.17 identified as a scenario the simulator
structurally cannot generate. Handling it at enrolment is the right place: it fails
loudly, once, instead of corrupting the total order silently forever.

---

### WI-5.2 — SQLCipher at rest `[gate]`

**Touches** `dhara-dart/lib/src/store.dart`

**Commit ladder**
1. `build(dart): add sqlcipher and replace the plain sqlite dependency`
2. `feat(store): open the local database with a key from secure storage`
3. `feat(store): migrate an existing plaintext database into an encrypted one`
4. `test(store): the database file is unreadable without the key`
5. `test(store): migration preserves every record and the outbox`
6. `perf(store): measure the encryption overhead on 2GB hardware`
7. `test(store): the store fails closed when the key is unavailable`
8. `docs: record the sqlcipher configuration and kdf parameters`

⚠ Rung 7: "fails closed" means an unavailable key produces an error, never an
automatic fallback to a plaintext database. A silent plaintext fallback is the
single worst bug available in this WI, and it is the kind that ships because it makes
a confusing crash go away.

⚠ Rung 6 matters more here than elsewhere. SQLCipher's page-level encryption has a
real cost on a 2GB device with slow flash. If the six-month backlog query moves from
100 ms to 2 s, the KDF parameters need tuning — and that is a security trade-off to
record, not a number to quietly lower.

---

### WI-5.3 — Revocation without device cooperation `[gate]`

**Why** The exit criterion, and the constraint that rules out the obvious design.

**Touches** `dhara/crypto.py`, `spec/security-model.md`

**Design:** the device holds **half** of what it needs. The local data key is
wrapped by a server-held component that is re-supplied on each successful sync, with
a bounded validity period. Revocation is the server refusing to re-supply it.

Consequences, all of which must be stated in the spec:
- A device offline longer than the validity period **loses read access to its own
  local store** until it syncs again. That is a real cost paid by exactly the users
  this project exists to help.
- Therefore the validity period is a policy dial, and the right value is a field
  question, not an engineering one. **Start long — 90 days — and tune with real
  data in Phase 6.**
- **The outbox is exempt.** Unsynced operations must remain readable and syncable
  even when the read key has expired, or an expiry event destroys exactly the data
  that has never reached the server. This is the requirement that makes the design
  acceptable at all.

**Commit ladder**
1. `spec: define the wrapped-key revocation design and its offline cost`
2. `feat(crypto): wrap the local data key with a server-supplied component`
3. `feat(crypto): re-supply the wrapping component on each successful sync`
4. `feat(crypto): give the wrapping component a bounded validity period`
5. `feat(crypto): keep the outbox readable under a separate key that never expires`
6. `test(crypto): the outbox survives read-key expiry intact`
7. `feat(crypto): refuse to re-supply the component for a revoked device`
8. `test(crypto): a revoked device cannot decrypt its store after expiry`
9. `test(crypto): a revoked device never needing to come online is still covered`
10. `feat(crypto): warn the worker before the validity period expires`
11. `test(crypto): the warning fires with enough lead time to reach a network`
12. `docs: state the validity-period trade-off and its default of 90 days`

⚠ Rung 5/6 are the heart of this WI. Without them the design has a catastrophic
failure mode: a worker offline for 91 days loses everything she recorded in that
time — the project's own worst-case scenario, caused by its own security layer.

⚠ Rung 10/11 are usability as a safety property. A worker who receives no warning has
no chance to seek a network; a warning that fires on day 89 is not a warning.

---

### WI-5.4 — Per-worker sessions on shared devices

**Why** Roadmap §6.5, and catalogue C-17. Every operation is attributed to the
worker, not the device.

**Touches** `dhara/session.py`, `dhara/crypto.py`

**Commit ladder**
1. `feat(session): add a worker identity distinct from the device identity`
2. `feat(session): attribute every operation to the worker who made it`
3. `test(session): device and worker identity are independently recorded`
4. `feat(session): scope local queries to the current worker`
5. `test(session): a worker cannot read another worker's unsynced operations`
6. `feat(session): survive a mid-sync worker switch without losing partial progress`
7. `test(session): session expiry mid-sync preserves the outbox - catalogue C-17`
8. `test(session): operations retain their original worker across a device handover`
9. `feat(session): log worker switches to the audit trail`

⚠ Rung 8 is the one to be careful about. The recorded worker is a **clinical
provenance fact** — who took this measurement — not an access-control token. It must
never be rewritten when a device changes hands, even though that is the convenient
thing to do when reconciling state.

---

### WI-5.5 — Tombstones with forwarding pointers `[gate]`

**Why** Roadmap §6.4(a): *"devices hold local references to the losing UUID and must
not break when it is superseded."*

**Touches** `dhara/identity.py`

**Commit ladder**
1. `spec: define tombstones with forwarding pointers in identity-resolution.md`
2. `feat(identity): add a tombstone carrying a forwarding pointer to the survivor`
3. `feat(identity): resolve a record id through forwarding pointers transitively`
4. `test(identity): a chain of three forwards resolves to the final survivor`
5. `test(identity): a forwarding cycle is detected and rejected, not looped on`
6. `feat(identity): rewrite references at read time, never destructively on disk`
7. `test(identity): an operation naming a superseded id applies to the survivor`
8. `test(identity): an offline device's queued operations survive a merge - C-13`
9. `feat(identity): make forwarding pointers a lattice so merges converge`
10. `test(identity): property - forwarding resolution satisfies the three laws`

⚠ Rung 6 is the design decision that makes this tractable. **Resolve at read time,
never rewrite history on disk.** Destructive rewriting means a device that was
offline during the merge has operations referencing an ID that no longer exists
anywhere, and there is no way back. Read-time resolution means old references keep
working forever at the cost of one indirection.

⚠ Rung 5: a merge decided concurrently on two servers, or a merge later reversed, can
produce A→B and B→A. Detect and refuse rather than looping; a hung sync on a field
device is indistinguishable from a dead app.

---

### WI-5.6 — Duplicate detection: accept-then-reconcile `[gate]`

**Why** Roadmap §6.4: *"Recommended: implement (a) as the correctness backbone…
(a) alone is sufficient for v0.1."*

**Touches** `dhara/identity.py`, `spec/identity-resolution.md`

**Design:** locally generated UUIDs, always accepted. Duplicates are detected
server-side and a merge decision propagates back as an ordinary operation.

**⚠ The candidate-matching rule is domain knowledge and must not live in `dhara`.**
Whether two records are the same child depends on names, dates of birth, and mother's
name — concepts this repository is not allowed to know. `dhara` provides the
mechanism: a schema-declared **match key** the consumer computes, plus the
tombstone-and-forwarding machinery to act on a decision. The decision itself is the
consumer's.

**Commit ladder**
1. `spec: define accept-then-reconcile with the schema-declared match key`
2. `feat(schema): let a schema declare an opaque match key over its fields`
3. `feat(identity): index records by match key on the server replica`
4. `feat(identity): surface match-key collisions as duplicate candidates`
5. `test(identity): independent registration at two centres is surfaced - C-13`
6. `feat(identity): apply a merge decision as an ordinary propagating operation`
7. `feat(identity): merge two records field-wise using the existing lattice joins`
8. `test(identity): merging two records loses no measurement from either`
9. `test(identity): a merge decision converges on every replica`
10. `feat(review): emit a duplicate_candidate review signal rather than auto-merging`
11. `test(identity): a merge is idempotent when delivered twice`
12. `sim: duplicate registration under partition reconciles on reconnect`

⚠ Rung 10 is a deliberate refusal to be clever. Auto-merging two children who are not
the same child creates a corrupted longitudinal record for two real people, and it is
not recoverable by the worker. The engine surfaces; a supervisor decides. This is
roadmap §6.2's last row applied to identity, and it is the same argument.

Rung 8 is the no-loss invariant applied to the hardest case. A record merge that
drops one child's measurements is the worst possible bug in this project, and it is
reachable only through this code path.

---

### WI-5.7 — Review queue integration

**Why** Open question Q1, resolved in Phase 1: `dhara` emits, the consumer renders.
This WI makes the emission complete and durable.

**Touches** `dhara/review.py`, CGMS `review_queue.py`

**Commit ladder**
1. `feat(review): make review signals durable and syncable, not ephemeral`
2. `feat(review): carry the evidence needed to render a decision`
3. `feat(review): allow a resolved signal to be acknowledged and propagate`
4. `test(review): a resolution converges across replicas`
5. `test(review): an unacknowledged signal survives a device restart`
6. `feat(sync): render the review queue for supervisors` *(CGMS repo)*
7. `feat(sync): apply a supervisor decision as a dhara operation` *(CGMS repo)*
8. `test(review): signal volume per 100 records is measurable`

Rung 8 feeds the metric from roadmap §9: *"Review-queue volume per 100 records. Too
high = merge rules too timid. Too low = suspicious."* Instrument it now so Phase 6
has a number rather than an impression.

---

### WI-5.8 — Bloom filter pre-push `[stretch]`

**Why** Roadmap §6.4(b), explicitly a UX improvement on top of the correctness
backbone. **Cut this first if the phase is running long.**

**Touches** `dhara/identity.py`

**Design:** a bloom filter over fuzzy hashes of the match key for the surrounding
block, pushed during the last successful sync. Gives an offline "this may already
exist" warning without shipping a plaintext beneficiary list to every phone.

**Commit ladder**
1. `spec: define the bloom filter pre-push and its privacy properties`
2. `feat(identity): build a bloom filter over opaque match-key hashes`
3. `feat(identity): size the filter to a stated false-positive rate and byte budget`
4. `feat(identity): push the filter in the bulk lane during sync`
5. `feat(identity): query the filter offline for a possible-duplicate warning`
6. `test(identity): the false-positive rate matches the configured target`
7. `test(identity): the filter never produces a false negative`
8. `docs: state what the filter leaks and what it does not`

⚠ Rung 8 is required, not optional. A bloom filter over hashes of personal data is
**not** anonymisation — an attacker with the phone and a candidate list can test
membership. The honest claim is narrow: it avoids shipping a plaintext beneficiary
list, and it is not a privacy guarantee. Say exactly that.

⚠ Rung 7: false negatives would make this a correctness feature, and it is not one.
It is a hint. The accept-then-reconcile backbone remains the correctness mechanism
whether or not the filter fires.

---

### WI-5.9 — Key rotation `[stretch]`

**Commit ladder**
1. `feat(crypto): support rotating the device key without re-enrolment`
2. `feat(crypto): re-wrap the data key under a rotated device key`
3. `test(crypto): rotation preserves access to existing records`
4. `test(crypto): the old key cannot decrypt after rotation completes`
5. `docs: document the rotation procedure and when to use it`

---

### WI-5.10 — Security review and phase exit `[gate]`

**Commit ladder**
1. `docs: complete the security model with the as-built mechanisms`
2. `docs: record the residual risks not mitigated by the implementation`
3. `test(crypto): run the full security test suite against the exit criteria`
4. `sim: run the million-schedule sweep with crypto and identity enabled`
5. `docs(plan): record phase 5 exit checklist results`
6. `docs: add changelog entry for security and identity`
7. `chore: tag phase-5-complete`

⚠ Rung 4 is the one to actually run rather than assume. Signing, key wrapping, and
identity forwarding all sit on the hot path and all touch serialisation. If any of
them broke a merge property, the sweep is what says so — and the mutation detection
times will say whether the harness is still sharp.

---

## Exit checklist

- [ ] **A revoked device's local store is unreadable without that device coming
      online**, verified by test.
- [ ] **The outbox remains readable and syncable after read-key expiry** — an expiry
      event never destroys unsynced work.
- [ ] The worker is warned before expiry with enough lead time to reach a network.
- [ ] **A duplicate registration created at two centres is detected and reconciled**,
      and both devices update local references without breaking.
- [ ] Forwarding pointers resolve transitively at read time; cycles are refused.
- [ ] A record merge loses no measurement from either side, asserted as a property.
- [ ] Duplicates are surfaced for supervisor decision, never auto-merged.
- [ ] Match-key computation lives in the consumer; the domain-token checker is green.
- [ ] Every operation is attributed to a worker, and attribution is never rewritten.
- [ ] The device key is never derived from a password; a duplicate device ID is
      refused at enrolment.
- [ ] The store fails closed when the key is unavailable — no plaintext fallback.
- [ ] SQLCipher overhead measured on real 2GB hardware.
- [ ] Threat model complete, with accepted risks stated explicitly.
- [ ] Million-schedule sweep green with crypto and identity enabled; mutation
      detection times unchanged.
- [ ] `phase-5-complete` tag pushed.

---

## What can go wrong in this phase

| Failure | Signal | Response |
|---|---|---|
| **Read-key expiry destroys unsynced data** | The outbox is encrypted under the expiring key | WI-5.3 rung 5. This is the failure that would make the security layer worse than no security layer. |
| Silent plaintext fallback | A confusing crash "fixed" by opening the database unencrypted | Fail closed (WI-5.2 rung 7). |
| Domain matching logic leaks into `dhara` | Name or DOB comparison in `identity.py` | The match key is opaque and computed by the consumer. WI-5.6. |
| Auto-merging duplicates | No `duplicate_candidate` signal in the flow | Surface, do not decide. Corrupting two children's longitudinal records is unrecoverable. |
| Destructive reference rewriting | Offline devices break after a merge | Resolve at read time (WI-5.5 rung 6). |
| Crypto overhead makes the app unusable | Backlog query seconds instead of milliseconds | Tune KDF parameters and record it as a security trade-off, with the number. |
| Phase runs long | Week 20 with reconciliation unstarted | Cut WI-5.8 and WI-5.9 first. Never cut at-rest encryption. |
