"""dhara — the conflict-resolution layer that generic sync engines leave to you.

This package knows nothing about any application domain. It receives a schema
descriptor at runtime, applies lattice joins field-wise, and reports what it
could not resolve. It never imports a domain model, never knows what a record
represents, and has no table name anywhere in it.

That constraint is enforced mechanically by ``scripts/check_no_domain_imports.py``
in CI, not by discipline alone.

Three properties this package exists to provide:

1. No silent data loss — a value a replica observed is never dropped by a merge.
2. Convergence — replicas that have seen the same operations, in any order,
   reach the same state.
3. Bounded bandwidth — a sync makes forward progress inside a small window and
   resumes from where it stopped.
"""

__version__ = "0.0.0"

# The wire protocol version is what consumers actually depend on. It is
# tracked separately from __version__ and bumped only on an incompatible
# change to the format on the wire. See spec/protocol-v0.1.md.
PROTOCOL_VERSION = 1

__all__ = ["PROTOCOL_VERSION", "__version__"]
