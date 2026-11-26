<script lang="ts">
	import { resolve } from '$app/paths';
	import type { MatchSummary } from './types';

	let { matches, empty = 'None.' }: { matches: MatchSummary[]; empty?: string } = $props();

	function result(m: MatchSummary): string {
		if (m.status === 'running') return 'live';
		if (m.status !== 'done') return m.status;
		const who = m.winner_seat === null ? 'draw' : `${m.players[m.winner_seat]} won`;
		return `${who}, ${(m.reason ?? '').replaceAll('_', ' ')}`;
	}
</script>

<ul>
	{#each matches as m (m.id)}
		<li>
			<a href="{resolve('/match')}?id={m.id}">#{m.id}</a>
			{m.players.join(' vs ')}
			<span class="muted">· {m.kind} · {result(m)}</span>
		</li>
	{:else}
		<li class="muted">{empty}</li>
	{/each}
</ul>

<style>
	ul {
		padding-inline-start: 1.25rem;
	}
</style>
