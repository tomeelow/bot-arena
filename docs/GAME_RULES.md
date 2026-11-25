# Game Rules — v1 (draft)

**Engine version:** 0.1.0 · **Status:** draft. The numbers can be tuned until the Phase 2 balance report. After that the rules are frozen as engine `1.0.0`, and later changes bump the engine version and start a new ladder season.

This document is the specification. `engine/` implements it, and `engine/tests/test_rules.py` contains a test for every worked example below. If this document and the engine disagree, that's a bug in one of them, and it has to be decided which.

---

## 1. Overview

Two players. Each controls a **Core** and the units it spawns. Both submit their orders at the same time each turn, and the engine resolves them together. You see only what your units can see. To win, destroy the enemy Core, or have the higher score when the turn limit is reached.

## 2. The map

- A grid of **32 × 32** cells. `(0, 0)` is the top-left corner, `x` grows to the right and `y` grows downwards.
- Every cell is **open**, a **wall**, a **crystal deposit**, or a **Core**. Units can only stand on open cells. Walls, deposits and Cores block movement.
- Maps are generated from the match seed and are **180° rotationally symmetric**: cell `(x, y)` mirrors `(31 − x, 31 − y)`. Walls, deposits (with their starting amounts) and the two Cores are mirror images, so neither seat has a better map.
- The map is always connected: every open cell can reach both Cores, and every deposit has at least one reachable open neighbour.
- **What's public from turn 0:** the size, all walls, every deposit's position, and both Cores' positions. The enemy Core's position follows from yours by symmetry anyway. Units, deposit amounts and the enemy's Core HP are hidden by fog (§6).

### Your view is seat-relative

Each bot sees the map as if it were seat 0, with its own Core towards the top-left. For seat 1, every position is rotated 180° and every direction flipped (N↔S, E↔W), both in what it sees and in the orders it sends. The two seats are therefore exactly equivalent: the same bot plays the same game from either seat.

### Generation (summary)

1. 10% of cell pairs become walls.
2. Seat 0's Core goes at a random cell with `3 ≤ x < 8` and `3 ≤ y < 8`. Seat 1's Core goes at the mirrored cell.
3. Walls and deposits are kept out of a radius of 2 around each Core.
4. Each side gets **2 home deposits** within distance 3–5 of its Core and **5 field deposits** elsewhere in its half. Each deposit holds **150–300 crystals**, in steps of 10. Everything is mirrored.
5. If the Cores aren't connected, or a deposit can't be reached, generation draws again. Any open cells that can't be reached become walls.

Distances in these rules are integer **squared** Euclidean distances, `dx² + dy²`. "Within radius r" means `dx² + dy² ≤ r²`. "Adjacent" means one step N, E, S or W (no diagonals).

## 3. Cores and units

|  | Cost | HP | Vision (r²) | Attack | Carry |
|---|---|---|---|---|---|
| **Core** | — | 400 | 25 | — | — |
| **Worker** | 50 | 10 | 8 | — | 10 |
| **Soldier** | 80 | 30 | 8 | 5 | — |
| **Scout** | 30 | 5 | 49 | — | — |

- Each player starts with **100 crystals banked** and **2 Workers** next to its Core: one to the east and one to the south (seat-relative).
- At most **40 living units** per player.
- **Workers** mine crystals (2 per turn) from an adjacent deposit into their cargo (up to 10), then unload the cargo at their own Core.
- **Soldiers** attack an adjacent enemy unit or Core.
- **Scouts** are cheap and fragile and see far. Information is what you buy with them.
- Units have ids. Your units are numbered 1, 2, 3, … in the order they were spawned, and ids are never reused. **Enemy units have no id in your view.**

## 4. Orders

Each turn, a bot returns a list of orders. Every unit takes at most one order, and a unit without one holds still. The Core can spawn at most once per turn.

| Order | Who | Valid when (checked against the start-of-turn state) |
|---|---|---|
| `move(unit, dir)` | any unit | The target cell is on the map and is not a wall, deposit or Core |
| `mine(unit, dir)` | Worker | The target cell is a deposit with crystals left, and the Worker's cargo isn't full |
| `attack(unit, dir)` | Soldier | The target cell holds an enemy unit or the enemy Core |
| `unload(unit)` | Worker | The Worker carries crystals and is adjacent to its own Core |
| `spawn(kind, dir)` | Core | The target cell is on the map and not a wall, deposit or Core; you can afford it; you have fewer than 40 units |

`dir` is one of `N`, `E`, `S`, `W`, in your seat-relative frame.

**Invalid orders.** An order that breaks a rule above is ignored, and its unit holds still. So is any order for a unit that doesn't exist, any unit given more than one order (*all* of that unit's orders are ignored), and more than one `spawn` in a turn (*all* spawns are ignored). Each ignored order is reported privately to its sender as an `invalid_order` event with a reason. The opponent never learns about it.

## 5. Turn resolution

All orders take effect at the same moment, in this fixed sequence of phases. **No phase depends on seat order.** Whenever two orders compete for the same thing, a symmetric rule decides: either the thing is split evenly, or nobody gets it.

### Phase 1 — Attacks
Every valid attack hits the target cell's occupant **at its start-of-turn position**, so moving away this turn doesn't dodge a hit. All damage is applied at once. Damage from several attackers stacks.

> **Example: both die.** Two Soldiers on 5 HP are adjacent and attack each other. Both take 5 damage and both die. Neither "strikes first".
>
> **Example: no dodging.** A Worker moves away from an attacking Soldier. It still takes the damage, and then moves (if it survives).

### Phase 2 — Deaths
Units with HP ≤ 0 are removed, and any orders they were given are cancelled. Crystals carried by a dead Worker are lost. A unit's owner receives a private `unit_lost` event. A Core at HP ≤ 0 is destroyed.

### Phase 3 — Moves
Every surviving unit with a valid `move` heads for its target cell.

1. **Contest.** If two or more units target the same cell, none of them moves.
2. **Swap.** If two units target each other's cells, neither moves: units can't pass through each other.
3. **Blocked.** If a unit's target cell holds a unit that ends up not moving (it had no move, or was blocked itself), the mover is blocked too. Repeat until nothing changes.
4. Everyone else moves. A cell vacated this turn, including by a unit that died in phase 2, can be entered.

> **Example: chain.** A wants B's cell, and B moves to an empty cell. Both move.
>
> **Example: blocked chain.** A wants B's cell, and B holds still. A stays.
>
> **Example: ring.** Three or more units each move into the next one's cell, in a closed loop. They all move: nobody passes through anybody.

### Phase 4 — Mining and unloading
- Each Worker mining a deposit asks for `min(2, cargo space left)`. If the deposit holds enough for everyone, everyone gets what they asked for. If not, each of the *n* miners gets `min(request, floor(amount / n))`, and any remainder stays in the deposit.
- Unloading moves the Worker's whole cargo into its player's bank.

> **Example: shared deposit.** A deposit holds 3 crystals, and two Workers (from either seat) each ask for 2. Each gets 1, and 1 stays in the deposit.

### Phase 5 — Spawns
A valid `spawn` places a new unit on the target cell if that cell is free **after** the moves. The unit gets the next id and full HP, and its cost is deducted. If the cell is occupied, the spawn fails, nothing is spent, and the player receives a private `spawn_blocked` event. If both Cores spawn into the same cell, both fail.

> **Example: spawn blocked.** Your Core spawns east while one of your units moves into that cell. The move happens, the spawn fails, and your crystals are kept.

### Phase 6 — End of turn
The turn counter advances, and the game checks whether it has ended (§7).

## 6. Fog of war

A cell is **visible** to you if it lies within the vision radius of one of your living units or of your Core. Each turn you see:

- your own bank, your Core's HP, and every one of your units (id, kind, position, HP, cargo);
- each enemy unit on a visible cell (kind, position and HP, **but no id and no cargo**);
- the enemy Core's HP, if its cell is visible;
- the current amount in each visible deposit;
- your own private events from the previous turn (`invalid_order`, `spawn_blocked`, `unit_lost`).

Nothing else gets through. You never see the enemy's bank, unit count, spawn count, invalid orders, or anything on a cell you can't see. The engine's tests check this: two games that differ only in what you can't see must give you identical observations.

## 7. Ending and scoring

- If a Core is destroyed, its owner loses. If both Cores fall on the same turn, the game is a **draw**.
- Otherwise the game ends after turn **400**. The higher **score** wins, and equal scores are a draw. A player's score is banked crystals, plus crystals carried by their Workers, plus the spawn cost of every living unit they own.

## 8. Invariants (always true, always tested)

- At most one unit stands on any cell, and never on a wall, deposit or Core.
- Crystals are conserved: deposits + cargo + banks + crystals spent on spawns + crystals lost with dead Workers = the total at turn 0.
- The same seed and the same orders give the same game, on every runtime (CPython and Pyodide), whatever the hash seed.
- Swapping seats gives the mirror image of the same game.
