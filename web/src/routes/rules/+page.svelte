<script lang="ts">
	const repo = 'https://github.com/tomeelow/bot-arena';
</script>

<svelte:head><title>Rules & starter kit · Bot Arena</title></svelte:head>

<article>
	<h1>Rules & starter kit</h1>
	<p>
		The full specification, with a worked example for every tricky case, is
		<a href="{repo}/blob/main/docs/GAME_RULES.md">GAME_RULES.md</a>. This is the short version.
	</p>

	<h2>The game</h2>
	<ul>
		<li>Two players on a 32×32 grid that is the same from both sides (rotated 180°).</li>
		<li>
			Each player has a <strong>Core</strong> and starts with 100 crystals and two Workers. Destroy the
			enemy Core, or have the higher score after 400 turns.
		</li>
		<li>
			Both bots send their orders at the same time each turn and the engine resolves them together.
			Nothing depends on which seat you are in: every bot sees the map as if its Core were top-left.
		</li>
		<li>
			<strong>Fog of war:</strong> you see only what your units and Core can see. Enemy units carry no
			ids.
		</li>
	</ul>

	<table>
		<thead>
			<tr><th>Unit</th><th class="num">Cost</th><th class="num">HP</th><th>Does</th></tr>
		</thead>
		<tbody>
			<tr>
				<td>Worker</td><td class="num">50</td><td class="num">10</td><td>
					Mines 2 crystals a turn, carries 10, unloads at the Core
				</td>
			</tr>
			<tr>
				<td>Soldier</td><td class="num">80</td><td class="num">30</td><td>
					Attacks an adjacent enemy unit or Core for 5
				</td>
			</tr>
			<tr>
				<td>Scout</td><td class="num">30</td><td class="num">5</td><td>
					Sees much further than anything else
				</td>
			</tr>
		</tbody>
	</table>

	<h2>Your bot</h2>
	<p>A bot is one <code>.py</code> file with one subclass of <code>Bot</code>:</p>
	<pre><code
			>from arena import Bot, Dir, Kind, Move, Observation, Order

class MyBot(Bot):
    def act(self, obs: Observation) -&gt; list[Order]:
        return [Move(u.id, Dir.E) for u in obs.units if u.kind is Kind.SCOUT]</code
		></pre>
	<p>
		Each turn has a CPU budget, with a time bank for the occasional slow turn. A bot that crashes,
		runs out of time or memory, or sends something that isn't a list of orders loses that match.
		Nothing else happens to it.
	</p>

	<h2>Play locally</h2>
	<pre><code
			>git clone {repo}.git
cd bot-arena && uv sync --all-packages
uv run arena match starter_kit/examples/first_bot.py builtin:random --seed 1</code
		></pre>
	<p>
		Then copy the example and start changing it. The
		<a href="{repo}/blob/main/starter_kit/README.md">starter kit README</a> covers the API, the built-in
		opponents and how to watch your replays.
	</p>
</article>

<style>
	article {
		max-inline-size: 48rem;
	}
</style>
