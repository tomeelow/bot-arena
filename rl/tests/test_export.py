"""The exported bundle is an ordinary bot: one file, under the upload cap, that the harness
loads and that plays the same game as the network it was exported from."""

import ast
import tomllib
from pathlib import Path

import numpy as np
from arena.harness import load_bot
from arena.runner import run_match
from arena_rl import boss, ppo
from arena_rl.boss import BossBot, Net
from arena_rl.env import play
from arena_rl.export import bundle

# The server's own setting, read from its file: rl/ doesn't install the server package.
SERVER_SETTINGS = Path(__file__).parents[2] / "server/src/arena_server/settings.toml"
UPLOAD_MAX_BYTES = tomllib.loads(SERVER_SETTINGS.read_text())["api"]["upload_max_bytes"]


def test_the_bundle_plays_like_its_weights_and_fits_the_upload_cap(tmp_path):
    params = ppo.init(64, np.random.default_rng(0))
    path = tmp_path / "boss.py"
    path.write_text(bundle(params))
    assert path.stat().st_size <= UPLOAD_MAX_BYTES
    record = run_match((str(path), "builtin:rush"), 5)
    assert record.result.reason in ("core_destroyed", "turn_limit")
    result, state = play((BossBot(Net(ppo.to_layers(params))), load_bot("builtin:rush")()), 5)
    assert (result, state) == (record.result, record.final_state)


def test_the_boss_imports_only_what_every_jailed_bot_has():
    """No numpy in the shipped bot: the jail offers the standard library and the starter
    kit, and adding a module there is a sandbox change (CLAUDE.md, "Ask before acting")."""
    tree = ast.parse(Path(boss.__file__).read_text())
    modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert {m.split(".")[0] for m in modules} <= {"arena", "math", "collections"}
