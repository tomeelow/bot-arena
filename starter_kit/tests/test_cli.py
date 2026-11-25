from pathlib import Path

from arena.cli import main

EXAMPLE = str(Path(__file__).parent.parent / "examples" / "first_bot.py")


def test_match_then_show(tmp_path, capsys):
    replay = tmp_path / "r.json.gz"
    logs = tmp_path / "logs.json"
    assert (
        main(
            [
                "match",
                EXAMPLE,
                "builtin:random",
                "--seed",
                "5",
                "--out",
                str(replay),
                "--logs",
                str(logs),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "seat 0" in out and "wins" in out
    assert replay.exists() and "workers" in logs.read_text()

    assert main(["show", str(replay), "--turn", "10"]) == 0
    board = capsys.readouterr().out
    assert "turn 10/400" in board and "C" in board and "c" in board


def test_tournament_prints_a_table(capsys):
    assert (
        main(["tournament", "builtin:rush", "builtin:greedy", "--seed-pairs", "1", "--jobs", "1"])
        == 0
    )
    out = capsys.readouterr().out
    assert "2 games" in out and "rush" in out


def test_unknown_bots_are_refused_before_anything_runs(capsys):
    assert main(["match", "builtin:rsh", "missing.py"]) == 2
    err = capsys.readouterr().err
    assert "no built-in bot 'rsh'" in err and "no such bot file: missing.py" in err


def test_show_refuses_a_broken_replay(tmp_path, capsys):
    import gzip

    bad = tmp_path / "bad.json.gz"
    bad.write_bytes(gzip.compress(b'{"format": 99}'))
    assert main(["show", str(bad)]) == 1
    assert "unsupported replay format" in capsys.readouterr().err
