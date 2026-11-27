<script lang="ts">
	import { resolve } from '$app/paths';
	import { get } from '#lib/api.js';
	import LadderTable from '#lib/LadderTable.svelte';
	import MatchList from '#lib/MatchList.svelte';
	import type { LadderRow, MatchSummary } from '#lib/types.js';

	let top = $state<LadderRow[] | null>(null);
	let live = $state<MatchSummary[] | null>(null);
	let recent = $state<MatchSummary[] | null>(null);
	let error = $state('');

	$effect(() => {
		Promise.all([
			get<LadderRow[]>('/api/ladder'),
			get<MatchSummary[]>('/api/matches?status=running&limit=10'),
			get<MatchSummary[]>('/api/matches?status=done&limit=10')
		])
			.then(([l, r, d]) => ([top, live, recent] = [l.slice(0, 10), r, d]))
			.catch((e: Error) => (error = e.message));
	});
</script>

<svelte:head><title>Bot Arena</title></svelte:head>

<section class="intro">
	<h1>Write a Python bot. Watch it climb the ladder.</h1>
	<p>
		Two bots, a 32×32 grid, fog of war. Workers mine crystals, soldiers fight, scouts look around,
		and both sides move at the same moment. Upload your bot and it plays everyone else's, in a
		sandbox, on a ranked ladder that says how sure it is about every rating.
	</p>
	<p class="actions">
		<a class="button primary" href={resolve('/practice')}>Write a bot in your browser</a>
		<a class="button" href={resolve('/rules')}>Read the rules and get the starter kit</a>
		<a class="button" href={resolve('/me')}>Upload a bot</a>
	</p>
</section>

{#if error}<p class="error">Couldn't reach the server: {error}</p>{/if}

<div class="columns">
	<section>
		<h2>Top of the ladder</h2>
		{#if top}<LadderTable rows={top} />{:else}<p class="muted">Loading…</p>{/if}
		<p><a href={resolve('/ladder')}>Full ladder</a></p>
	</section>
	<section>
		<h2>Live now</h2>
		{#if live}<MatchList matches={live} empty="Nothing being played right now." />{/if}
		<h2>Just finished</h2>
		{#if recent}<MatchList matches={recent} empty="No matches yet." />{/if}
	</section>
</div>

<style>
	.intro {
		margin-block-end: 3rem;
	}
	.intro h1 {
		font-size: clamp(2.5rem, 4vw + 1rem, 4.5rem);
		margin-block: 1rem 1.5rem;
	}
	.intro > p:not(.actions) {
		font-size: 1.1875rem;
		color: var(--ink-2);
		max-inline-size: 40rem;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 1.25rem;
		margin-block-start: 2rem;
	}
	.columns {
		display: grid;
		grid-template-columns: minmax(0, 2fr) minmax(16rem, 1fr);
		gap: 2rem;
	}
	@media (width < 56rem) {
		.columns {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
