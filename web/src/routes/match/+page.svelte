<script lang="ts">
	import { page } from '$app/state';
	import { get, maybe } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';
	import type { InvalidOrder, MatchView } from '#lib/types.js';
	import { MatchFeed } from '#lib/viewer/feed.svelte.js';
	import Viewer from '#lib/viewer/Viewer.svelte';

	interface Owned {
		logs: [number, string][];
		invalid: InvalidOrder[];
	}

	let match = $state<MatchView | null>(null);
	let feed = $state<MatchFeed | null>(null);
	let owned = $state<[Owned | null, Owned | null]>([null, null]);
	let error = $state('');

	$effect(() => {
		const id = Number(page.url.searchParams.get('id'));
		const current = new MatchFeed();
		feed = current;
		get<MatchView>(`/api/matches/${id}`)
			.then((m) => {
				match = m;
				return current.open(m);
			})
			.catch((e: Error) => (error = e.message));
		return () => current.close();
	});

	// Logs and refused orders are the owner's alone, and exist once the match is finished.
	$effect(() => {
		if (!match || !feed?.end || !session.checked) return;
		const id = match.id;
		void Promise.all(
			match.players.map(async (p) =>
				session.owns(p.bot_id)
					? {
							logs: (await maybe<[number, string][]>(`/api/matches/${id}/logs/${p.seat}`)) ?? [],
							invalid: (await maybe<InvalidOrder[]>(`/api/matches/${id}/invalid/${p.seat}`)) ?? []
						}
					: null
			)
		).then((o) => (owned = o as [Owned | null, Owned | null]));
	});
</script>

<svelte:head><title>Match {match?.id ?? ''} · Bot Arena</title></svelte:head>

{#if match}
	<h1>
		Match #{match.id}
		<small class="muted">{match.kind} · seed {match.seed} · engine {match.engine_version}</small>
	</h1>
{/if}
{#if error || feed?.error}<p class="error">{error || feed?.error}</p>{/if}
{#if feed?.header}
	<Viewer header={feed.header} frames={feed.frames} end={feed.end} live={feed.live} {owned} />
{:else if match?.status === 'queued'}
	<p class="muted">This match is queued. It will play here as soon as a worker picks it up.</p>
{:else if !error}
	<p class="muted">Loading…</p>
{/if}

<style>
	small {
		font-size: 0.9rem;
		font-weight: normal;
	}
</style>
