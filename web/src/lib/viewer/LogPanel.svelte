<script lang="ts">
	import type { InvalidOrder } from '../types';

	interface Props {
		name: string;
		logs: [number, string][];
		invalid: InvalidOrder[];
		turn: number;
	}

	let { name, logs, invalid, turn }: Props = $props();
	// Everything this bot printed or got wrong, up to the turn on the scrubber.
	const lines = $derived(
		[
			...logs.map(([t, text]) => ({ turn: t, text, invalid: false })),
			...invalid.map((o) => ({ turn: o.turn, text: `invalid order: ${o.reason}`, invalid: true }))
		]
			.filter((line) => line.turn <= turn)
			.sort((a, b) => a.turn - b.turn)
	);
	let box: HTMLElement;

	$effect(() => {
		void lines;
		box.scrollTop = box.scrollHeight;
	});
</script>

<section aria-label="{name}: logs">
	<h3>{name} <small>logs, visible only to you</small></h3>
	<div class="log" bind:this={box} tabindex="-1">
		{#each lines as line, i (i)}
			<div class:current={line.turn === turn} class:invalid={line.invalid}>
				<span class="turn">{line.turn}</span><span class="text">{line.text}</span>
			</div>
		{:else}
			<p class="muted">Nothing yet.</p>
		{/each}
	</div>
</section>

<style>
	h3 {
		font-size: 0.95rem;
		margin: 0 0 0.25rem;
	}
	small {
		font-weight: normal;
		color: var(--muted);
	}
	.log {
		max-block-size: 14rem;
		overflow: auto;
		font-family: var(--mono);
		font-size: 0.8rem;
		background: var(--surface);
		border-radius: 4px;
		padding: 0.25rem 0.5rem;
	}
	.log > div {
		display: flex;
		gap: 0.5rem;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.turn {
		color: var(--muted);
		min-inline-size: 3ch;
		text-align: end;
	}
	.current {
		background: var(--highlight);
	}
	.invalid .text {
		color: var(--danger);
	}
</style>
