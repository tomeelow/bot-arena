"""Every bot in sandbox/adversarial/ against a built-in, in the real jail. Each must end the
way its docstring says, without escaping, and leave the host as it found it.

Runs only inside the sandbox image (`make sandbox-check`): the jail needs Linux.
"""

import os
from pathlib import Path

import pytest
from arena_sandbox import JailConfig, ranked_match

ADVERSARIAL = Path(__file__).parent.parent / "adversarial"
CANARY = Path("/tmp/arena-canary")
PLAYS_ON = {"turn_limit", "core_destroyed"}
EXPECTED = {
    "infinite_loop": {"timeout"},
    "slow_init": {"timeout"},
    "sleeper": {"timeout"},
    "cpu_hog": {"timeout"},
    "background_burner": PLAYS_ON | {"timeout"},
    "memory_bomb": {"memory"},
    "import_bomb": {"memory"},
    "stdout_flood": {"memory"},
    "fork_bomb": PLAYS_ON,
    "thread_bomb": PLAYS_ON,
    "network": PLAYS_ON,
    "fs_probe": PLAYS_ON,
    "fs_fill": PLAYS_ON | {"memory"},
    "stderr_flood": PLAYS_ON,
    "ctypes_escape": PLAYS_ON,
    "process_kill": PLAYS_ON,
    "protocol_garbage": {"invalid_output"},
    "protocol_huge": {"invalid_output"},
    "wrong_turn": {"invalid_output"},
    "harness_tamper": {"invalid_output"},
    "slowloris": {"timeout"},
    "signal_ignorer": {"timeout"},
    "early_exit": {"crash"},
    "recursion_bomb": {"memory", "crash"},
}


def jail_processes() -> list[str]:
    found = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        except OSError:
            continue
        if "arena.harness" in cmdline or cmdline.startswith("bwrap"):
            found.append(f"{pid}: {cmdline[:120]}")
    return found


@pytest.fixture
def host():
    """The jail config, with a canary planted on the host, and a check afterwards that no
    jail process or cgroup outlived its match."""
    CANARY.write_text("host secret")
    os.environ["ARENA_CANARY"] = "host secret"
    config = JailConfig.from_env()
    yield config
    del os.environ["ARENA_CANARY"]
    CANARY.unlink()
    assert [p.name for p in config.cgroup_root.iterdir() if p.is_dir()] == []
    assert jail_processes() == []


def play(bot: str, config: JailConfig):
    record = ranked_match((bot, "builtin:greedy"), seed=1, config=config)
    escapes = [text for _, text in record.logs[0] if "ESCAPED" in text]
    return record, escapes


def test_every_adversarial_bot_has_an_expectation():
    assert {p.stem for p in ADVERSARIAL.glob("*.py")} == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_adversarial_bot_is_contained(name, host):
    record, escapes = play(str(ADVERSARIAL / f"{name}.py"), host)
    assert escapes == []
    assert record.result.reason in EXPECTED[name], (record.result, record.stderr[0][-1500:])
    if record.result.reason not in PLAYS_ON:
        assert record.result.winner == 1


def test_a_parser_bomb_never_reaches_the_host(tmp_path, host):
    bomb = tmp_path / "bomb.py"
    bomb.write_text("x = " + "(" * 100_000 + ")" * 100_000 + "\n")
    record, _ = play(str(bomb), host)
    assert (record.result.reason, record.result.turns) == ("crash", 0)


def test_cpu_burned_between_turns_still_counts(tmp_path, host):
    """The burner's thread runs while its opponent thinks. Give it an opponent that takes
    300 ms a turn (sleeping, so free for the opponent) and the stolen CPU empties its bank."""
    slow = tmp_path / "slow.py"
    slow.write_text(
        "import time\nfrom arena import Bot\n\n"
        "class Slow(Bot):\n"
        "    def act(self, obs):\n"
        "        time.sleep(0.3)\n"
        "        return []\n"
    )
    burner = str(ADVERSARIAL / "background_burner.py")
    record = ranked_match((burner, str(slow)), seed=1, config=host)
    assert (record.result.winner, record.result.reason) == (1, "timeout"), record.result
    assert "time bank" in record.result.detail
    assert record.result.turns < 400
