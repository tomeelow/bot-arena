"""Soak test for the ranked jail: many matches, normal and hostile, several at once.

    docker run --rm --privileged arena-sandbox python sandbox/soak.py --matches 1000

Reports platform errors (an exception out of ranked_match), anything left behind (jail
processes, cgroups), whether the host process' memory stayed flat, and the CPU a normal
match costs, which feeds the capacity budget (Phase 9). Results go in docs/benchmarks.md.
"""

import argparse
import logging
import os
import resource
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from random import Random

from arena.limits import Limits
from arena.runner import Channel, run_match
from arena_sandbox import JailChannel, JailConfig, ranked_match

log = logging.getLogger("soak")
ADVERSARIAL = sorted((Path(__file__).parent / "adversarial").glob("*.py"))
BUILTINS = [f"builtin:{n}" for n in ("random", "greedy", "rush", "turtle", "scout")]


def pairing(i: int) -> tuple[str, str]:
    rng = Random(i)
    if rng.random() < 0.3:
        return (str(rng.choice(ADVERSARIAL)), rng.choice(BUILTINS))
    return (rng.choice(BUILTINS), rng.choice(BUILTINS))


def leftovers(config: JailConfig) -> list[str]:
    cgroups = [p.name for p in config.cgroup_root.iterdir() if p.is_dir()]
    procs = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        if b"arena.harness" in cmd or cmd.startswith(b"/usr/bin/bwrap"):
            procs.append(pid)
    return cgroups + procs


class KeepChannels:
    """Opens jails like ranked_match does, and keeps them so their CPU can be read."""

    def __init__(self, config: JailConfig) -> None:
        self.config = config
        self.channels: list[JailChannel] = []

    def __call__(self, spec: str, limits: Limits) -> Channel:
        self.channels.append(JailChannel(spec, self.config, limits))
        return self.channels[-1]


def cpu_per_match(config: JailConfig, matches: int) -> tuple[float, float]:
    """Seconds of CPU for a normal match, one at a time: (bots, host)."""
    bots: list[float] = []
    host: list[float] = []
    for i in range(matches):
        opener = KeepChannels(config)
        start = time.process_time()
        run_match(("builtin:scout", "builtin:turtle"), i, opener=opener, enforce=True)
        host.append(time.process_time() - start)
        bots.append(sum(c.cpu_us for c in opener.channels) / 1e6)
    return statistics.median(bots), statistics.median(host)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=1000)
    parser.add_argument("--parallel", type=int, default=8)
    args = parser.parse_args()
    config = JailConfig.from_env()

    outcomes: Counter[str] = Counter()
    errors: list[str] = []
    rss_mb: list[float] = []

    def one(i: int) -> None:
        players = pairing(i)
        try:
            record = ranked_match(players, seed=i, config=config)
            outcomes[record.result.reason] += 1
        except Exception as e:  # a platform failure: exactly what the soak is looking for
            errors.append(f"match {i} {players}: {e!r}")

    started = time.monotonic()
    with ThreadPoolExecutor(args.parallel) as pool:
        for done, _ in enumerate(pool.map(one, range(args.matches)), start=1):
            if done % 100 == 0:
                rss_mb.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
                log.info("%d matches, peak host RSS %.1f MiB", done, rss_mb[-1])
    elapsed = time.monotonic() - started

    bots_cpu, host_cpu = cpu_per_match(config, 20)
    log.info("matches: %d in %.0f s, %d at a time", args.matches, elapsed, args.parallel)
    log.info("outcomes: %s", dict(outcomes.most_common()))
    log.info("platform errors: %d %s", len(errors), errors[:5])
    log.info("left behind: %s", leftovers(config) or "nothing")
    log.info("host peak RSS per 100 matches (MiB): %s", [round(r, 1) for r in rss_mb])
    log.info("CPU per normal match (scout vs turtle): bots %.2f s, host %.2f s", bots_cpu, host_cpu)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
