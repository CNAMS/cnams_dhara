# ADR-0001 — `dhara` is a separate repository from the CGMS monorepo

**Status** accepted · **Date** 2026-08-01 · **Phase** 0

## Context

The sync layer could live inside the CGMS backend repository as
`backend/app/sync/`, or as its own repository that CGMS depends on.

The positioning argument for separation is real but secondary: the artifact can be
described without mentioning CGMS, so coupling it to one backend costs the property
that makes it interesting.

**The engineering argument is stronger.** The moment sync code sits next to the
SQLAlchemy models, somebody — you, at 2 AM, during exams — will write
`from app.models import Child` inside a merge function. It is the locally correct
move: it is faster than extending the schema descriptor and it makes the failing test
pass. The merge logic then knows what a child is and is no longer a sync engine; it is
a feature of one backend.

A folder boundary does not prevent that. A repository boundary does, because the
import simply is not available.

## Decision

`dhara` is a separate repository. CGMS depends on it; **never the reverse.**

`dhara` receives a schema descriptor at runtime. It never imports a domain model,
never knows what a record represents, and has no table name anywhere in it.

## Consequences

**Buys**

- The dependency rule is enforced by the module system, not by discipline.
- The artifact stands alone: it can be described, published and evaluated without
  reference to CGMS.
- Domain knowledge is confined to two `schema_binding` files, both in the CGMS repo.

**Costs**

- Version pinning between two repositories.
- Two CI configurations.
- Friction when one logical change spans both. Mitigated by landing the `dhara` change
  first and citing its SHA in the CGMS commit — the cheap substitute for atomic
  cross-repo commits.
- Path dependencies for weeks 1–13, then pinned tags. Neither is free.

**Enforcement**

`scripts/check_no_domain_imports.py` fails CI on domain tokens under `dhara-py/`,
`dhara-dart/` and `spec/conformance/`. The word list lives in the script, so changing
it requires a commit that says why.

## Alternatives

**Monorepo with a folder boundary.** Rejected: it does not remove the import, so it
does not remove the temptation, and the failure is invisible until the day the sync
layer needs to be reused or described independently.

**Separate package inside the same repository.** Better than a folder, still allows
the import at 2 AM via a relative path or a test fixture.
