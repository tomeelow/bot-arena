<script lang="ts">
	import { page } from '$app/state';
	import { get, maybe } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';
	import type { InvalidOrder, MatchView, Owned } from '#lib/types.js';
	import { MatchFeed } from '#lib/viewer/feed.svelte.js';
	import Viewer from '#lib/viewer/Viewer.svelte';

	let match = $state<MatchView | null>(null);
	let feed = $state<MatchFeed | null>(null);
	let owned = $state<[Owned | null, Owned | null]>([null, null]);
	let error = $state('');

	$effect(() => {
		const id = Number(page.url.searchParams.get('id'));
		const current = new MatchFeed();
		let disposed = false; // navigating to another match reuses this page: drop late answers
		[feed, match, error] = [current, null, ''];
		get<MatchView>(`/api/matches/${id}`)
			.then((m) => {
				if (disposed) return;
				match = m;
				return current.open(m);
			})
			.catch((e: Error) => !disposed && (error = e.message));
		return () => {
			disposed = true;
			current.close();
		};
	});

	// Logs and refused orders are the owner's alone, and exist once the match is finished.
	$effect(() => {
		owned = [null, null]; // never keep one match's or one user's private data for another
		if (!match || !feed?.end || !session.checked) return;
		const id = match.id;
		let current = true;
		void Promise.all(
			match.players.map(async (p) =>
				session.owns(p.bot_id)
					? {
							logs: (await maybe<[number, string][]>(`/api/matches/${id}/logs/${p.seat}`)) ?? [],
							invalid: (await maybe<InvalidOrder[]>(`/api/matches/${id}/invalid/${p.seat}`)) ?? []
						}
					: null
			)
		)
			.then((o) => current && (owned = o as [Owned | null, Owned | null]))
			.catch((e: Error) => current && (error = `Couldn't load your bot's logs: ${e.message}`));
		return () => (current = false);
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
	/* the subtitle sits inside the h1, so it must undo the display face and its RGB split */
	small {
		display: block;
		margin-block-start: 0.5rem;
		font-family: var(--body);
		font-size: 0.9375rem;
		font-weight: 700;
		text-transform: none;
		text-shadow: none;
		color: var(--muted);
	}
</style>
