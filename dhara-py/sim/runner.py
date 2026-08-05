"""Seed sweeps, shrinking, and replay.

    Seed 4471 fails? Replay seed 4471 exactly and debug it.
    -- roadmap section 7.1

Three things live here, and the third is the one that decides whether the
simulator gets used:

**Sweep.** Run a seed range, collect failures, report throughput.

**Shrink.** A failure at seed 4471 with five devices, eighty writes and thirty
faults is a failure nobody debugs. Shrinking reduces it to the smallest scenario
that still fails.

**Replay.** One command from a seed to a rendered timeline. If it takes more
than one command it will not be used at 11 PM, and the simulator's value halves.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sim.scenario import Scenario, SimResult, Simulation, generate

__all__ = ["Failure", "SweepResult", "replay", "shrink", "sweep"]


@dataclass(frozen=True, slots=True)
class Failure:
    seed: int
    scenario: Scenario
    invariants: tuple[str, ...]
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "scenario": self.scenario.to_json(),
            "invariants": list(self.invariants),
            "detail": self.detail,
        }


@dataclass(slots=True)
class SweepResult:
    seeds: int
    failures: list[Failure] = field(default_factory=list)
    elapsed_s: float = 0.0
    operations: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def rate(self) -> float:
        return self.seeds / self.elapsed_s if self.elapsed_s else 0.0

    def summary(self) -> str:
        head = (
            f"{self.seeds} schedules in {self.elapsed_s:.1f}s "
            f"({self.rate:.0f}/s), {self.operations} operations"
        )
        if self.ok:
            return f"{head} - all invariants held"
        return f"{head} - {len(self.failures)} FAILED: " + ", ".join(
            str(f.seed) for f in self.failures[:10]
        )


def _failure(result: SimResult) -> Failure:
    return Failure(
        seed=result.scenario.seed,
        scenario=result.scenario,
        invariants=tuple(sorted({v.invariant for v in result.violations})),
        detail="\n".join(str(v) for v in result.violations),
    )


def run_seed(seed: int, preset: str = "hostile", *, trace: bool = False) -> SimResult:
    return Simulation(generate(seed, preset), trace=trace).run()


def sweep(
    seeds: Iterable[int],
    preset: str = "hostile",
    *,
    stop_after: int | None = None,
    progress_every: int = 0,
) -> SweepResult:
    """Run a seed range.

    `stop_after` exists for the mutation experiment, which only needs the
    *first* failing seed: continuing past it burns time to learn nothing.
    """
    started = time.perf_counter()
    result = SweepResult(seeds=0)

    for index, seed in enumerate(seeds, start=1):
        outcome = run_seed(seed, preset)
        result.seeds = index
        result.operations += outcome.operations

        if not outcome.ok:
            result.failures.append(_failure(outcome))
            if stop_after is not None and len(result.failures) >= stop_after:
                break

        if progress_every and index % progress_every == 0:
            elapsed = time.perf_counter() - started
            print(
                f"  {index} seeds, {len(result.failures)} failures, "
                f"{index / max(elapsed, 1e-9):.0f}/s",
                flush=True,
            )

    result.elapsed_s = time.perf_counter() - started
    return result


def _shard(args: tuple[int, int, str]) -> tuple[int, int, list[Failure]]:
    """One worker's slice. Top-level so it can be pickled."""
    start, count, preset = args
    seeds = 0
    operations = 0
    failures: list[Failure] = []
    for seed in range(start, start + count):
        outcome = run_seed(seed, preset)
        seeds += 1
        operations += outcome.operations
        if not outcome.ok:
            failures.append(_failure(outcome))
    return seeds, operations, failures


def parallel_sweep(
    start: int,
    count: int,
    preset: str = "hostile",
    *,
    workers: int | None = None,
) -> SweepResult:
    """Shard a seed range across processes.

    Each seed is an independent world, so sharding is embarrassingly parallel
    and - crucially - changes nothing about determinism: seed 4471 produces the
    same run whichever worker executes it, and whether it is executed alone or
    alongside a million others.

    This is what makes the million-schedule gate an overnight job rather than a
    week. Single-core throughput is ~43 schedules/s, most of it full-state
    serialisation that Phase 3's delta design removes; until then, parallelism
    is the cheaper lever than optimising a path about to be replaced.
    """
    workers = workers or os.cpu_count() or 4
    per_worker = max(1, count // workers)
    slices = [
        (start + i * per_worker, per_worker if i < workers - 1 else count - i * per_worker, preset)
        for i in range(workers)
    ]
    slices = [sl for sl in slices if sl[1] > 0]

    started = time.perf_counter()
    result = SweepResult(seeds=0)

    with multiprocessing.Pool(len(slices)) as pool:
        for seeds, operations, failures in pool.imap_unordered(_shard, slices):
            result.seeds += seeds
            result.operations += operations
            result.failures.extend(failures)

    result.failures.sort(key=lambda f: f.seed)
    result.elapsed_s = time.perf_counter() - started
    return result


# -- shrinking ------------------------------------------------------------


def _still_fails(scenario: Scenario, invariants: tuple[str, ...]) -> bool:
    """Does this scenario still fail *the same way*?

    Same-way matters. A shrunk scenario that fails a different invariant is a
    different bug, and following it leads away from the one being debugged.
    """
    outcome = Simulation(scenario).run()
    if outcome.ok:
        return False
    return bool(set(invariants) & {v.invariant for v in outcome.violations})


def shrink(failure: Failure, *, max_steps: int = 200) -> Scenario:
    """Reduce a failing scenario to something a person can read.

    Greedy, one dimension at a time, keeping any reduction that preserves the
    failure. Bounded by `max_steps` so shrinking never dominates a sweep - an
    unbounded shrink on a rare failure can outlast the sweep that found it.

    This is where the per-entity RNG streams earn their keep. With one shared
    stream, dropping a device would reshuffle every remaining device's
    behaviour, and the "smaller" scenario would be a different one that merely
    looks smaller.
    """
    current = failure.scenario
    steps = 0

    def try_replace(**changes: Any) -> bool:
        nonlocal current, steps
        if steps >= max_steps:
            return False
        steps += 1
        candidate = Scenario(**{**current.to_json(), **changes})
        if _still_fails(candidate, failure.invariants):
            current = candidate
            return True
        return False

    # Devices first: it is the dimension that most reduces what a reader has to
    # hold in their head.
    while current.devices > 2 and try_replace(devices=current.devices - 1):
        pass

    for target in (current.writes // 2, current.writes // 4, 10, 5, 3, 2, 1):
        if 0 < target < current.writes:
            try_replace(writes=target)

    while current.records > 1 and try_replace(records=current.records - 1):
        pass

    for divisor in (2, 4, 8):
        target = current.horizon_ms // divisor
        if target > 60_000:
            try_replace(horizon_ms=target)

    try_replace(crash_rate=0.0)
    try_replace(partition_rate=0.0)

    return current


# -- replay ---------------------------------------------------------------


def replay(seed: int, preset: str = "hostile") -> SimResult:
    return run_seed(seed, preset, trace=True)


def render_timeline(result: SimResult, *, record: str | None = None) -> str:
    """A human-readable timeline of one run.

    Filtered to a single record when asked, because a run touching three records
    interleaves three unrelated stories and the one you want is the one that
    broke.
    """
    lines = [
        f"seed {result.scenario.seed}  preset={result.scenario.profile}  "
        f"devices={result.scenario.devices}  writes={result.scenario.writes}",
        "-" * 72,
    ]
    start = result.trace[0]["at"] if result.trace else 0

    for event in result.trace:
        if record is not None and event.get("record") not in (None, record):
            continue
        offset_h = (event["at"] - start) / 3_600_000
        detail = " ".join(
            f"{k}={v}" for k, v in event.items() if k not in {"at", "kind"}
        )
        lines.append(f"  +{offset_h:8.2f}h  {event['kind']:<10} {detail}")

    lines.append("-" * 72)
    if result.ok:
        lines.append("all invariants held")
    else:
        lines.append(f"{len(result.violations)} violation(s):")
        lines.extend(f"  {v}" for v in result.violations)
    return "\n".join(lines)


def write_failure(failure: Failure, directory: Path) -> Path:
    """Persist a failure so it can be committed to the regression corpus.

    A failure that only exists in a terminal is a failure that will be
    rediscovered.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"seed_{failure.seed}.json"
    path.write_text(json.dumps(failure.to_json(), indent=2, sort_keys=True))
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="dhara deterministic simulator")
    parser.add_argument("--seeds", type=int, default=2_000)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--preset", default="hostile")
    parser.add_argument("--replay", type=int, help="replay one seed and print a timeline")
    parser.add_argument("--record", help="filter the timeline to one record id")
    parser.add_argument("--shrink", action="store_true", help="shrink the first failure")
    parser.add_argument("--progress", type=int, default=0)
    parser.add_argument(
        "--workers", type=int, default=1, help="shard the range across N processes"
    )
    args = parser.parse_args(argv)

    if args.replay is not None:
        outcome = replay(args.replay, args.preset)
        print(render_timeline(outcome, record=args.record))
        return 0 if outcome.ok else 1

    if args.workers > 1:
        result = parallel_sweep(
            args.start, args.seeds, args.preset, workers=args.workers
        )
    else:
        result = sweep(
            range(args.start, args.start + args.seeds),
            args.preset,
            progress_every=args.progress,
        )
    print(result.summary())

    if result.failures and args.shrink:
        smallest = shrink(result.failures[0])
        print("\nshrunk reproducer:")
        print(json.dumps(smallest.to_json(), indent=2, sort_keys=True))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
