<script lang="ts">
	import { probability } from '#lib/format.js';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { get, post } from '#lib/api.js';
	import MatchList from '#lib/MatchList.svelte';
	import RatingChart from '#lib/RatingChart.svelte';
	import { session } from '#lib/session.svelte.js';
	import type { BotView, ComparisonView, RatingPoint } from '#lib/types.js';

	let bot = $state<BotView | null>(null);
	let points = $state<RatingPoint[]>([]);
	let error = $state('');
	let challenger = $state(0);
	let incumbent = $state(0);
	let seedPairs = $state(10);
	let comparison = $state<ComparisonView | null>(null);
	let compareError = $state('');

	const mine = $derived(bot !== null && session.owns(bot.id));
	// Versions that passed validation: a new version retires the last one, but both can be compared.
	const COMPARABLE = ['active', 'retired'];
	const comparable = $derived(bot?.versions.filter((v) => COMPARABLE.includes(v.status)) ?? []);

	$effect(() => {
		const id = Number(page.url.searchParams.get('id'));
		Promise.all([get<BotView>(`/api/bots/${id}`), get<RatingPoint[]>(`/api/bots/${id}/history`)])
			.then(([b, h]) => {
				[bot, points] = [b, h];
				const [newest, previous] = b.versions.filter((v) => COMPARABLE.includes(v.status));
				challenger = newest?.id ?? 0;
				incumbent = previous?.id ?? 0;
			})
			.catch((e: Error) => (error = e.message));
	});

	// A comparison's games are played by the workers: check back until they are all in.
	$effect(() => {
		if (!comparison || comparison.pending === 0) return;
		const id = comparison.id;
		const timer = setTimeout(() => {
			get<ComparisonView>(`/api/compare/${id}`)
				.then((c) => (comparison = c))
				.catch((e: Error) => (compareError = e.message));
		}, 5000);
		return () => clearTimeout(timer);
	});

	async function compare(event: SubmitEvent) {
		event.preventDefault();
		compareError = '';
		try {
			comparison = await post<ComparisonView>('/api/compare', {
				challenger,
				incumbent,
				seed_pairs: seedPairs
			});
		} catch (e) {
			compareError = (e as Error).message;
		}
	}

	const percent = (p: number) => `${Math.round(p * 100)}%`;
	const fixed = (v: number | null) => (v === null ? '—' : v.toFixed(1));
	const name = (id: number) => `v${bot?.versions.find((v) => v.id === id)?.n ?? '?'}`;
</script>

<svelte:head><title>{bot ? `${bot.owner}/${bot.name}` : 'Bot'} · Bot Arena</title></svelte:head>

{#if error}<p class="error">{error}</p>{/if}
{#if bot}
	<h1>{bot.owner}/{bot.name}</h1>

	<h2>Rating history</h2>
	{#if points.length}
		<RatingChart {points} versions={bot.versions} />
	{:else}
		<p class="muted">No rated games yet.</p>
	{/if}

	<h2>Versions</h2>
	<table>
		<thead>
			<tr>
				<th>Version</th><th>Status</th><th class="num">μ</th><th class="num">σ</th><th class="num">
					Games
				</th>
			</tr>
		</thead>
		<tbody>
			{#each bot.versions as v (v.id)}
				<tr>
					<td>v{v.n}</td>
					<td>{v.status}</td>
					<td class="num">{fixed(v.mu)}</td>
					<td class="num">{fixed(v.sigma)}</td>
					<td class="num">{v.games}</td>
				</tr>
				{#if v.error}
					<tr><td colspan="5"><pre class="error">{v.error}</pre></td></tr>
				{/if}
			{/each}
		</tbody>
	</table>

	{#if mine && comparable.length > 1}
		<h2>Compare two versions</h2>
		<p class="muted">
			Both versions play the same seeds, each from both seats, so the map and the seat cancel out.
		</p>
		<form onsubmit={compare}>
			<label>
				Challenger
				<select bind:value={challenger}>
					{#each comparable as v (v.id)}<option value={v.id}>v{v.n}</option>{/each}
				</select>
			</label>
			<label>
				against
				<select bind:value={incumbent}>
					{#each comparable as v (v.id)}<option value={v.id}>v{v.n}</option>{/each}
				</select>
			</label>
			<label>
				Seeds
				<input type="number" min="1" max="20" bind:value={seedPairs} />
			</label>
			<button type="submit" disabled={challenger === incumbent}>Compare</button>
		</form>
		{#if compareError}<p class="error">{compareError}</p>{/if}
		{#if comparison}
			<p role="status">
				{name(comparison.challenger)} against {name(comparison.incumbent)}:
				{comparison.wins} won, {comparison.draws} drawn, {comparison.losses} lost{#if comparison.pending},
					{comparison.pending} still to play{/if}. Score {percent(comparison.score)} (95% interval {percent(
					comparison.low
				)}–{percent(comparison.high)}).
				<strong>
					{probability(comparison.p_better)} confident that {name(comparison.challenger)} is the better
					version.
				</strong>
			</p>
			{#if comparison.lost.length}
				<p>
					Games it lost:
					{#each comparison.lost as id (id)}<a href="{resolve('/match')}?id={id}">#{id}</a>
					{/each}
				</p>
			{/if}
		{/if}
	{/if}

	<h2>Recent matches</h2>
	<MatchList matches={bot.recent_matches} empty="No matches yet." />
{:else if !error}
	<p class="muted">Loading…</p>
{/if}

<style>
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: end;
	}
	input[type='number'] {
		inline-size: 5rem;
	}
	pre {
		margin: 0;
	}
</style>
