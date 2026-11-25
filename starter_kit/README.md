# Bot Arena starter kit

Write a bot in Python, play it against the built-in bots on your own machine, and watch what happened.

The game: two players, a 32×32 grid, fog of war. Workers mine crystals, soldiers fight, scouts look around. Destroy the enemy Core, or have the higher score after 400 turns. Both players' orders take effect at the same moment. The full rules, with a worked example for every tricky case, are in [docs/GAME_RULES.md](../docs/GAME_RULES.md).

## Set up

The kit isn't on PyPI yet. Clone the repository and use [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/tomeelow/bot-arena.git
```

```bash
cd bot-arena && uv sync --all-packages
```

## Your first match

```bash
uv run arena match starter_kit/examples/first_bot.py builtin:random --seed 1
```

That plays [`examples/first_bot.py`](examples/first_bot.py) against a bot that moves at random, and saves `replay.json.gz`. Copy the example and start changing it.

## Writing a bot

A bot is one `.py` file that defines exactly one subclass of `Bot`:

```python
from arena import Bot, Kind, Move, Observation, Order, Dir

class MyBot(Bot):
    def setup(self) -> None:
        ...  # optional, runs once: self.map, self.rules and self.rng are ready

    def act(self, obs: Observation) -> list[Order]:
        return [Move(u.id, Dir.E) for u in obs.units if u.kind is Kind.SCOUT]
```

`act` runs once a turn and returns your orders. One order per unit; a unit without one stays put.

| Order | Who | What it does |
|---|---|---|
| `Move(unit_id, dir)` | anyone | step N, E, S or W |
| `Mine(unit_id, dir)` | Worker | take 2 crystals from the deposit in that direction |
| `Unload(unit_id)` | Worker | bank your cargo (you must be next to your Core) |
| `Attack(unit_id, dir)` | Soldier | 5 damage to the enemy unit or Core in that direction |
| `Spawn(kind, dir)` | your Core | a new unit next to the Core (Worker 50, Soldier 80, Scout 30 crystals) |

**What you can see** (`obs`): the turn number, your bank, your Core's HP, all your units (`id`, `kind`, `pos`, `hp`, `cargo`), any enemy units and deposits your units can currently see, and the enemy Core's HP if it's in sight. Enemy units have no ids.

**What you always know:**
- `self.map`: walls, deposit sites, both Cores' positions, the map size.
- `self.rules`: the match parameters.
- `self.events`: last turn's events (an order rejected and why, a spawn that was blocked, a unit you lost).

**Your side is always the top-left.** Every bot sees the map as if it started in the top-left corner, whichever seat it really has. Directions are in that same frame, so you never have to think about which side you're on.

**Pathfinding:** `Grid(self.map)` knows the static map. `grid.distances(targets)` gives a distance field, and `grid.step_toward(pos, field, avoid=...)` gives the next step.

**Randomness:** use `self.rng`, not the `random` module. It's seeded by the match, so replays reproduce exactly.

## Debugging

- `print(...)` and `self.log(...)` go to your bot's log. Save it with `--logs logs.json`; nobody else ever sees it.
- `uv run arena show replay.json.gz --turn 120` prints the board at any turn.
- If your bot crashes, `arena match` prints its traceback.
- Invalid orders don't crash your bot. The unit holds still and the reason shows up in `self.events` on the next turn.

## Limits

Each turn has a **100 ms** thinking budget. Going over draws from a **10 s** time bank for the whole match; when the bank is empty, you lose. Locally these are only warnings. Ranked matches will enforce them.

A bot loses on the spot if it crashes, exits, or replies with something that isn't a valid order list.

## The built-in opponents

| Name | Plays |
|---|---|
| `builtin:random` | random orders: the floor |
| `builtin:greedy` | pure economy, never fights |
| `builtin:rush` | soldiers straight at your Core |
| `builtin:turtle` | economy behind a defensive ring |
| `builtin:scout` | scouts first, then counters what it saw |

Their source in [`src/arena/builtin/`](src/arena/builtin/) is meant to be read. To measure your bot against all of them, with each map played from both seats:

```bash
uv run arena tournament my_bot.py builtin:greedy builtin:rush builtin:turtle builtin:scout --seed-pairs 20
```
