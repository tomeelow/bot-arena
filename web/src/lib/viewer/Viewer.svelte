<script lang="ts">
	import { resolve } from '$app/paths';
	import type { End, Frame, Header, InvalidOrder, Seat } from '../types';
	import AdvantageGraph from './AdvantageGraph.svelte';
	import Board from './Board.svelte';
	import LogPanel from './LogPanel.svelte';
	import { advantage, biggestSwing, markers } from './frames';

	interface Owned {
		logs: [number, string][];
		invalid: InvalidOrder[];
	}

	interface Props {
		header: Header;
		/** grows while a match is live */
		frames: Frame[];
		end: End | null;
		live: boolean;
		/** per seat, present only for a seat whose bot belongs to the viewer */
		owned: [Owned | null, Owned | null];
	}

	let { header, frames, end, live, owned }: Props = $props();

	const SPEEDS = [1, 2, 5, 10, 20, 50];
	let index = $state(0);
	let playing = $state(false);
	let speed = $state(10);
	let vision = $state<'all' | '0' | '1'>('all');
	// While live, stay on the newest turn until the viewer moves away from it.
	let following = $state(true);

	const last = $derived(frames.length - 1);
	const frame = $derived(frames[Math.min(index, last)]);
	const names = $derived(
		header.players.map((p) => `${p.owner}/${p.bot} v${p.version}`) as [string, string]
	);
	const series = $derived(frames.map((f) => advantage(header, f)));
	const swing = $derived(end ? biggestSwing(series) : null);
	const events = $derived(markers(frames));
	const seat = $derived(vision === 'all' ? null : (Number(vision) as Seat));

	// Following a live match ends on its last frame, even one that lands after the socket closes.
	let wasLive = $state(false);
	$effect(() => {
		if (live) wasLive = true;
		if (following && wasLive) index = last;
	});

	$effect(() => {
		if (!playing) return;
		const timer = setInterval(() => {
			if (index >= last) {
				if (!live) playing = false;
				return;
			}
			index += 1;
		}, 1000 / speed);
		return () => clearInterval(timer);
	});

	function seek(turn: number) {
		index = Math.max(0, Math.min(last, turn));
		following = index === last;
	}

	function toggle() {
		if (live && following) {
			following = false; // pausing a live match stops on this turn
			playing = false;
			return;
		}
		if (!playing && index >= last && !live) index = 0;
		playing = !playing;
	}

	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (target.closest('input:not([type=range]), textarea, select, [contenteditable]')) return;
		if (target.closest('button, a') && (event.key === ' ' || event.key === 'Enter')) return;
		const keys: Record<string, () => void> = {
			' ': toggle,
			k: toggle,
			ArrowLeft: () => seek(index - 1),
			j: () => seek(index - 1),
			ArrowRight: () => seek(index + 1),
			l: () => seek(index + 1),
			Home: () => seek(0),
			End: () => seek(last),
			v: () => (vision = vision === 'all' ? '0' : vision === '0' ? '1' : 'all')
		};
		const action = keys[event.key];
		if (!action || (target instanceof HTMLInputElement && event.key.startsWith('Arrow'))) return;
		event.preventDefault();
		action();
	}

	function outcome(e: End): string {
		if (e.type === 'void') return 'Voided: the platform failed, so the match is not rated.';
		const who = e.winner === null ? 'Draw' : `${names[e.winner]} wins`;
		return `${who} (${e.reason.replaceAll('_', ' ')}, turn ${e.turns}).`;
	}
</script>

<svelte:window {onkeydown} />

<div class="viewer">
	<div class="top">
		<div class="board">
			{#if frame}
				<Board {header} {frame} vision={seat} />
			{:else}
				<p class="muted">Waiting for the first turn…</p>
			{/if}
		</div>
		<aside>
			<ol class="players">
				{#each header.players as p, i (p.seat)}
					<li class="seat{i}">
						<span class="dot"></span>
						<a href="{resolve('/bot')}?id={p.bot_id}">{p.owner}/{p.bot}</a>
						<small>v{p.version}</small>
						{#if frame}
							<dl>
								<dt>Core</dt>
								<dd>{frame.cores[i]}</dd>
								<dt>Bank</dt>
								<dd>{frame.banks[i]}</dd>
								<dt>Units</dt>
								<dd>{frame.units.filter((u) => u[0] === i).length}</dd>
							</dl>
						{/if}
					</li>
				{/each}
			</ol>
			<fieldset>
				<legend>Vision <kbd>v</kbd></legend>
				<label><input type="radio" bind:group={vision} value="all" /> Everything</label>
				{#each names as name, i (i)}
					<label>
						<input type="radio" bind:group={vision} value={String(i)} /> What {name} saw
					</label>
				{/each}
			</fieldset>
			<p class="status" role="status">
				{#if end}
					{outcome(end)}
				{:else if live}
					<span class="live">Live</span> turn {last < 0 ? 0 : frames[last].turn} of {header.max_turns}
				{/if}
			</p>
		</aside>
	</div>

	<div class="controls">
		<button type="button" onclick={toggle} aria-keyshortcuts="Space k">
			{playing || (live && following) ? 'Pause' : 'Play'}
		</button>
		<button
			type="button"
			onclick={() => seek(index - 1)}
			aria-label="Back one turn"
			aria-keyshortcuts="ArrowLeft j"
		>
			−1
		</button>
		<button
			type="button"
			onclick={() => seek(index + 1)}
			aria-label="Forward one turn"
			aria-keyshortcuts="ArrowRight l"
		>
			+1
		</button>
		<input
			type="range"
			min="0"
			max={Math.max(0, last)}
			value={index}
			oninput={(e) => seek(e.currentTarget.valueAsNumber)}
			aria-label="Turn"
			aria-valuetext="Turn {frame?.turn ?? 0}"
		/>
		<output>Turn {frame?.turn ?? 0}</output>
		<label>
			Speed
			<select bind:value={speed}>
				{#each SPEEDS as s (s)}<option value={s}>{s} turns/s</option>{/each}
			</select>
		</label>
		{#if live && !following}
			<button type="button" onclick={() => seek(last)}>Back to live</button>
		{/if}
	</div>
	<p class="keys muted">
		Keys: <kbd>Space</kbd> play/pause, <kbd>←</kbd>/<kbd>→</kbd> one turn, <kbd>Home</kbd>/<kbd>
			End
		</kbd>
		first/last, <kbd>v</kbd> vision.
	</p>

	{#if frames.length}
		<AdvantageGraph
			{series}
			maxTurns={end ? Math.max(1, last) : Math.max(header.max_turns, last)}
			turn={index}
			{swing}
			markers={events}
			invalid={[owned[0]?.invalid ?? null, owned[1]?.invalid ?? null]}
			{names}
			onseek={seek}
		/>
	{/if}

	{#if owned[0] || owned[1]}
		<div class="logs">
			{#each owned as mine, i (i)}
				{#if mine}
					<LogPanel
						name={names[i]}
						logs={mine.logs}
						invalid={mine.invalid}
						turn={frame?.turn ?? 0}
					/>
				{/if}
			{/each}
		</div>
	{/if}
</div>

<style>
	.viewer {
		display: grid;
		gap: 1rem;
	}
	.top {
		display: grid;
		grid-template-columns: minmax(0, 36rem) minmax(14rem, 1fr);
		gap: 1rem;
		align-items: start;
	}
	@media (width < 48rem) {
		.top {
			grid-template-columns: 1fr;
		}
	}
	.players {
		list-style: none;
		padding: 0;
		margin: 0 0 1rem;
		display: grid;
		gap: 0.75rem;
	}
	.dot {
		display: inline-block;
		inline-size: 0.7rem;
		block-size: 0.7rem;
		border-radius: 50%;
	}
	.seat0 .dot {
		background: var(--seat-0);
	}
	.seat1 .dot {
		background: var(--seat-1);
	}
	dl {
		display: grid;
		grid-template-columns: repeat(3, auto 1fr);
		gap: 0 0.5rem;
		margin: 0.25rem 0 0;
		font-size: 0.875rem;
		font-variant-numeric: tabular-nums;
	}
	dt {
		color: var(--muted);
	}
	dd {
		margin: 0;
	}
	fieldset {
		border: 1px solid var(--line);
		border-radius: 4px;
		display: grid;
		gap: 0.25rem;
	}
	.live {
		color: var(--danger);
		font-weight: 600;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.controls input[type='range'] {
		flex: 1 1 12rem;
	}
	output {
		font-variant-numeric: tabular-nums;
		min-inline-size: 8ch;
	}
	.keys {
		margin: 0;
		font-size: 0.8rem;
	}
	.logs {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 1rem;
	}
</style>
