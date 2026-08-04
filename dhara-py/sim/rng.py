"""Seeded randomness, threaded explicitly.

Every non-deterministic decision in a simulation comes from here, and every one
is reachable from the root seed. There is no module-level `random`, no
`time.time()`, no `uuid4()` anywhere a simulation can reach -- enforced by
`scripts/check_no_ambient_nondeterminism.py`.

## Per-entity streams

The subtle part, and the reason this is a module rather than one `Random`
instance passed around.

If every entity draws from one shared stream, adding a device to a scenario
reshuffles every other device's behaviour, because they are all consuming from
the same sequence. **Shrinking then becomes useless**: removing one device to
see whether the failure persists changes what every remaining device does, so
the "smaller" scenario is not a subset of the original -- it is a different
scenario that happens to be smaller.

So each entity gets a child stream derived from `(root_seed, entity_id)`. Adding
or removing an entity leaves every other entity's stream untouched, and
shrinking actually narrows the search rather than wandering sideways through it.

## Why not `random.Random(hash(...))`

`hash()` on a `str` is salted per process unless `PYTHONHASHSEED` is fixed, and
one CI leg deliberately randomises it. Derivation goes through BLAKE2b instead:
stable across processes, across Python versions, and across the two languages if
the Dart side ever needs to reproduce a stream.
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterable, Sequence, TypeVar

__all__ = ["Rng", "derive_seed"]

T = TypeVar("T")


def derive_seed(root: int, *labels: object) -> int:
    """A stable 64-bit child seed from a root seed and any labels.

    Stable across processes, Python versions and `PYTHONHASHSEED` settings,
    which `hash()` is not.
    """
    material = b"|".join(
        [str(root).encode()] + [str(label).encode() for label in labels]
    )
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big")


class Rng:
    """A named, seeded random stream.

    Wraps `random.Random` rather than exposing it, so that every draw goes
    through a method that could be logged or replayed. The interface is
    deliberately small: a simulator that needs a distribution not offered here
    should build it from these, in the module that needs it, where the choice is
    visible.
    """

    __slots__ = ("_random", "label", "seed")

    def __init__(self, seed: int, label: str = "root") -> None:
        self.seed = seed
        self.label = label
        self._random = random.Random(seed)

    def child(self, *labels: object) -> Rng:
        """A derived stream for a sub-entity.

        Independent of draw order in the parent: two devices created in either
        order get the same streams.
        """
        label = ".".join([self.label, *(str(x) for x in labels)])
        return Rng(derive_seed(self.seed, *labels), label)

    # -- draws ------------------------------------------------------------

    def integer(self, low: int, high: int) -> int:
        """Inclusive on both ends."""
        return self._random.randint(low, high)

    def fraction(self) -> float:
        """Uniform in [0, 1)."""
        return self._random.random()

    def chance(self, probability: float) -> bool:
        """True with the given probability.

        Draws unconditionally even when the probability is 0 or 1, so that
        changing a probability does not shift every subsequent draw in the
        stream. That keeps a scenario's shape stable when one knob is tuned.
        """
        draw = self._random.random()
        return draw < probability

    def choice(self, options: Sequence[T]) -> T:
        if not options:
            raise ValueError("cannot choose from an empty sequence")
        return options[self._random.randrange(len(options))]

    def sample(self, options: Sequence[T], count: int) -> list[T]:
        return self._random.sample(list(options), min(count, len(options)))

    def shuffled(self, items: Iterable[T]) -> list[T]:
        out = list(items)
        self._random.shuffle(out)
        return out

    def exponential(self, mean: float) -> float:
        """For inter-arrival times and latencies."""
        return self._random.expovariate(1.0 / mean) if mean > 0 else 0.0

    def __repr__(self) -> str:
        return f"Rng(seed={self.seed}, label={self.label!r})"
