"""Golden games replay to their recorded hashes on CPython. Pyodide runs the same check."""

from golden_check import check_all


def test_golden_games_replay_to_their_recorded_hashes():
    count, problems = check_all()
    assert count >= 3
    assert problems == []
