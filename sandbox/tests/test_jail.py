"""The jail in normal play: same game as running in-process, real CPU accounting, and the
isolation flags every bot gets. Runs inside the sandbox image."""

from pathlib import Path

from arena.limits import Limits
from arena.runner import run_match
from arena_sandbox import JailConfig, bwrap_argv, ranked_match

ADVERSARIAL = Path(__file__).parent.parent / "adversarial"


def test_a_jailed_match_plays_exactly_like_an_in_process_one():
    jailed = ranked_match(("builtin:scout", "builtin:turtle"), seed=8)
    local = run_match(("builtin:scout", "builtin:turtle"), seed=8)
    assert jailed.orders == local.orders
    assert jailed.result == local.result


def test_a_player_bot_file_runs_in_the_jail_with_its_logs(tmp_path):
    bot = tmp_path / "mine.py"
    bot.write_text(
        "from arena import Bot\n\n"
        "class Mine(Bot):\n"
        "    def act(self, obs):\n"
        "        print('hello from turn', obs.turn)\n"
        "        return []\n"
    )
    record = ranked_match((str(bot), "builtin:random"), seed=2)
    assert record.logs[0][1] == (1, "hello from turn 1\n")


def test_thinking_time_is_the_bots_cpu_time():
    record = ranked_match((str(ADVERSARIAL / "cpu_hog.py"), "builtin:greedy"), seed=1)
    assert record.result.reason == "timeout" and "time bank" in record.result.detail
    assert all(280 <= ms[0] <= 600 for ms in record.think_ms)
    assert 30 <= len(record.think_ms) <= 60  # 10 s bank / ~200 ms overrun per turn


def test_every_bot_gets_the_same_isolation():
    config = JailConfig.from_env()
    argv = bwrap_argv("/uploads/abc.py", config, Limits.load())
    for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
        assert flag in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--uid") + 1] == "65534"
    assert ["--ro-bind", "/uploads/abc.py", "/bot/main.py"] in [
        argv[i : i + 3] for i in range(len(argv))
    ]
    assert argv[0].startswith("/")  # no PATH lookup: the jail starts with no environment
    assert argv[argv.index("--remount-ro") + 1] == "/"
    assert argv.index("--remount-ro") > max(i for i, a in enumerate(argv) if a == "--ro-bind")
    binds = [argv[i + 1] for i, a in enumerate(argv) if a in ("--bind", "--ro-bind")]
    assert binds == ["/usr", str(config.venv), "/uploads/abc.py"]  # nothing else of the host
    assert "--bind" not in argv  # nothing writable
