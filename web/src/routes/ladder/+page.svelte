<script lang="ts">
	import { get } from '#lib/api.js';
	import LadderTable from '#lib/LadderTable.svelte';
	import type { LadderRow } from '#lib/types.js';

	let rows = $state<LadderRow[] | null>(null);
	let error = $state('');

	$effect(() => {
		get<LadderRow[]>('/api/ladder')
			.then((r) => (rows = r))
			.catch((e: Error) => (error = e.message));
	});
</script>

<svelte:head><title>Ladder · Bot Arena</title></svelte:head>

<h1>Ladder</h1>
<p class="muted">
	Bots are ranked by a cautious score, μ − 3σ, so a bot only rises once the platform is sure of it.
	The bar shows the range its true skill is 95% likely to be in. “Stronger than next” is the
	probability that a bot's skill is higher than the one ranked below it; that is about skill, not
	about who wins the next game, which is closer to a coin toss.
</p>
{#if error}<p class="error">{error}</p>{/if}
{#if rows}<LadderTable {rows} />{:else if !error}<p class="muted">Loading…</p>{/if}
