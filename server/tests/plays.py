"""Match functions for workers under test: the local runner, not the jail (which needs
Linux; sandbox/tests covers it). Module-level so worker processes can import them."""

from arena.runner import MatchRecord, run_match
from arena_engine import Rules


def local(players: tuple[str, str], seed: int, rules: Rules | None) -> MatchRecord:
    return run_match(players, seed, rules)


def quick(players: tuple[str, str], seed: int, rules: Rules | None) -> MatchRecord:
    return run_match(players, seed, rules or Rules(max_turns=5))
