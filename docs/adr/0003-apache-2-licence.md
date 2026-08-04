# ADR-0003 — Apache-2.0 rather than MIT

**Status** accepted · **Date** 2026-08-01 · **Phase** 0

## Context

A repository with no licence cannot be cited, forked, or cleared by an employer's
legal team. The default choices are MIT and Apache-2.0.

## Decision

Apache-2.0.

## Consequences

**Buys**

- An **explicit patent grant.** This work may end up adjacent to a government
  programme, where a patent grant removes one class of question before it is asked.
- A licence choice with a stated reason, which reads differently from a default.
- Contribution terms and a `NOTICE` mechanism, if the project ever has contributors.

**Costs**

- Longer file than MIT.
- Slightly more friction for a consumer who wants to vendor the code, though not
  enough to matter at this scale.

## Alternatives

**MIT.** Shorter and more common in this ecosystem, but silent on patents. The silence
is the reason not to choose it here.

**AGPL.** Rejected. It would make the library unusable by the exact institutional
consumers this work is aimed at, which defeats the purpose of publishing it.
