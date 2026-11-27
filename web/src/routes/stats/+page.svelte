<script lang="ts">
	import { get } from '#lib/api.js';
	import { duration, share } from '#lib/format.js';
	import type { Spread, UsageStats } from '#lib/types.js';

	let stats = $state<UsageStats | null>(null);
	let error = $state('');

	$effect(() => {
		get<UsageStats>('/api/stats')
			.then((s) => (stats = s))
			.catch((e: Error) => (error = e.message));
	});

	const days = $derived.by(() => {
		const rows: Record<string, { versions: number; matches: number }> = {};
		const row = (day: string) => (rows[day] ??= { versions: 0, matches: 0 });
		for (const { day, count } of stats?.versions_per_day ?? []) row(day).versions = count;
		for (const { day, count } of stats?.matches_per_day ?? []) row(day).matches = count;
		return Object.entries(rows).sort(([a], [b]) => b.localeCompare(a));
	});

	const hours = (s: Spread, key: 'p50' | 'p95') => duration(s[key] === null ? null : s[key] * 3600);
	const games = (s: Spread, key: 'p50' | 'p95') => (s[key] === null ? '–' : String(s[key]));
</script>

<svelte:head><title>Stats · Bot Arena</title></svelte:head>

<h1>Stats</h1>
<p class="muted">
	Counted from our own database, in aggregate. No trackers or analytics scripts run on this site.
	Players are GitHub accounts; the arena's built-in bots don't count.
</p>
{#if error}<p class="error">{error}</p>{/if}
{#if stats}
	<dl class="figures">
		<div>
			<dt>Bots submitted</dt>
			<dd>{stats.submitted_bots}</dd>
		</div>
		<div>
			<dt>Active players, last 7 days</dt>
			<dd>{stats.active_players_7d}</dd>
		</div>
		<div>
			<dt>Rated matches, last 30 days</dt>
			<dd>{stats.rated_matches}</dd>
		</div>
	</dl>
	<p class="muted">An active player uploaded a version or asked for a comparison.</p>

	<h2>How fast the ladder learns</h2>
	<table>
		<thead>
			<tr>
				<th></th><th class="num">Median</th><th class="num">95th percentile</th><th class="num">
					Versions
				</th>
			</tr>
		</thead>
		<tbody>
			<tr>
				<td>Upload to first rated match</td>
				<td class="num">{duration(stats.seconds_to_first_match.p50)}</td>
				<td class="num">{duration(stats.seconds_to_first_match.p95)}</td>
				<td class="num">{stats.seconds_to_first_match.n}</td>
			</tr>
			<tr>
				<td>Rated games until a rating is no longer provisional</td>
				<td class="num">{games(stats.games_to_converge, 'p50')}</td>
				<td class="num">{games(stats.games_to_converge, 'p95')}</td>
				<td class="num">{stats.converged_versions}</td>
			</tr>
			<tr>
				<td>Time from upload until then</td>
				<td class="num">{hours(stats.hours_to_converge, 'p50')}</td>
				<td class="num">{hours(stats.hours_to_converge, 'p95')}</td>
				<td class="num">{stats.converged_versions}</td>
			</tr>
		</tbody>
	</table>
	<p class="muted">{stats.unconverged_versions} versions are still provisional.</p>

	<h2>How rated matches ended badly</h2>
	<p class="muted">
		Share of the last 30 days' {stats.rated_matches} rated matches that a bot lost by breaking a rule
		of the sandbox. The rest ended in play.
	</p>
	<table>
		<thead><tr><th>Outcome</th><th class="num">Share</th></tr></thead>
		<tbody>
			{#each Object.entries(stats.sandbox_outcomes) as [outcome, fraction] (outcome)}
				<tr><td>{outcome.replaceAll('_', ' ')}</td><td class="num">{share(fraction)}</td></tr>
			{/each}
		</tbody>
	</table>

	<h2>By day</h2>
	{#if days.length}
		<table>
			<thead>
				<tr>
					<th>Day (UTC)</th><th class="num">Versions accepted</th><th class="num">Rated matches</th>
				</tr>
			</thead>
			<tbody>
				{#each days as [day, row] (day)}
					<tr>
						<td>{day}</td><td class="num">{row.versions}</td><td class="num">{row.matches}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{:else}
		<p class="muted">Nothing in the last 30 days yet.</p>
	{/if}
{:else if !error}
	<p class="muted">Loading…</p>
{/if}

<style>
	.figures {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 3rem;
		margin: 0;
	}
	.figures > div {
		padding: 1rem 1.25rem;
		background: var(--surface);
		border: 2px solid var(--line);
		border-radius: 4px;
	}
	dt {
		color: var(--muted);
		font-size: 0.8125rem;
		font-weight: 700;
	}
	dd {
		margin: 0;
		font-family: var(--display);
		font-size: 2.5rem;
		line-height: 1.1;
		color: var(--accent-2);
		font-variant-numeric: tabular-nums;
	}
</style>
