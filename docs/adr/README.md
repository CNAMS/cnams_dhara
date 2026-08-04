# Architecture decision records

One file per decision that a future reader — including you in month five — would
otherwise have to reverse-engineer from the code.

**Format:** [MADR](https://adr.github.io/madr/)-ish, trimmed. Numbered sequentially,
never renumbered, never deleted. A superseded ADR keeps its number and gains a
`Superseded by ADR-NNNN` line; the reasoning that turned out to be wrong is often
more useful than the reasoning that turned out to be right.

**What belongs here, versus the other two records:**

| File | Holds |
|---|---|
| `docs/adr/` | A decision, written for someone who was not there |
| [plan/decision-log.md](../../plan/decision-log.md) | The running record, with the cost and the revisit-if |
| [DOUBTS.md](../../DOUBTS.md) | An assumption execution is resting on, not yet decided |

A doubt that gets decided becomes a decision-log entry, and — if substantial — an ADR.

## Template

```markdown
# ADR-NNNN — <decision as an outcome>

**Status** proposed | accepted | superseded by ADR-NNNN
**Date** YYYY-MM-DD
**Phase** N

## Context
What forced the decision. The constraint, not the preference.

## Decision
What was chosen, stated so it can be checked against the code.

## Consequences
What this buys, and — the load-bearing part — what it costs.

## Alternatives
What else was considered and the specific reason it was not chosen.
```

## Index

| ADR | Title | Status | Phase |
|---|---|---|---|
| [0001](0001-separate-repository.md) | `dhara` is a separate repository from the CGMS monorepo | accepted | 0 |
| [0002](0002-two-implementations-one-spec.md) | Two implementations against one spec, not a Rust core | accepted | 0 |
| [0003](0003-apache-2-licence.md) | Apache-2.0 rather than MIT | accepted | 0 |
