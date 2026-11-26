<script lang="ts">
	import { probability } from './format';
	import { resolve } from '$app/paths';
	import type { LadderRow } from './types';

	let { rows }: { rows: LadderRow[] } = $props();
	// One scale for every interval bar, so they can be compared at a glance.
	const lo = $derived(Math.min(...rows.map((r) => r.low)));
	const hi = $derived(Math.max(...rows.map((r) => r.high)));
	const pct = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
</script>

<table>
	<thead>
		<tr>
			<th class="num">#</th>
			<th>Bot</th>
			<th class="num" title="μ − 3σ: what the ladder is sorted by">Rank score</th>
			<th>Skill, 95% range (μ ± 2σ)</th>
			<th class="num" title="P(this bot's skill is higher than the next one down)">
				Stronger than next
			</th>
			<th class="num">Games</th>
		</tr>
	</thead>
	<tbody>
		{#each rows as r (r.version_id)}
			<tr>
				<td class="num">{r.rank}</td>
				<td>
					<a href="{resolve('/bot')}?id={r.bot_id}">{r.owner}/{r.bot}</a>
					{#if r.provisional}<span class="badge" title="σ still above the threshold">
							provisional
						</span>{/if}
				</td>
				<td class="num">{r.score.toFixed(1)}</td>
				<td>
					<span class="range" title="{r.low.toFixed(1)} to {r.high.toFixed(1)}">
						<span
							class="bar"
							style:inset-inline-start="{pct(r.low)}%"
							style:inline-size="{pct(r.high) - pct(r.low)}%"
						></span>
						<span class="mu" style:inset-inline-start="{pct(r.mu)}%"></span>
					</span>
					<small class="muted">{r.mu.toFixed(1)} ± {(2 * r.sigma).toFixed(1)}</small>
				</td>
				<td class="num">{r.p_above_next === null ? '—' : probability(r.p_above_next)}</td>
				<td class="num">{r.games}</td>
			</tr>
		{:else}
			<tr><td colspan="6" class="muted">No rated bots yet.</td></tr>
		{/each}
	</tbody>
</table>

<style>
	.range {
		position: relative;
		display: inline-block;
		inline-size: 10rem;
		block-size: 0.6rem;
		background: var(--surface);
		border-radius: 3px;
		vertical-align: middle;
		margin-inline-end: 0.5rem;
	}
	.bar {
		position: absolute;
		inset-block: 0;
		background: var(--accent);
		opacity: 0.35;
		border-radius: 3px;
	}
	.mu {
		position: absolute;
		inset-block: -2px;
		inline-size: 2px;
		background: var(--accent);
	}
</style>
