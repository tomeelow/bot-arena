<script lang="ts">
	import type { InvalidOrder } from '../types';
	import type { Marker, Swing } from './frames';

	interface Props {
		series: number[];
		maxTurns: number;
		turn: number;
		swing: Swing | null;
		markers: Marker[];
		/** owner only: each seat's refused orders, when this viewer owns that seat */
		invalid: [InvalidOrder[] | null, InvalidOrder[] | null];
		names: [string, string];
		onseek: (turn: number) => void;
	}

	let { series, maxTurns, turn, swing, markers, invalid, names, onseek }: Props = $props();

	const W = 800;
	const H = 160;
	const LANE = 10; // height of one row of event marks under the graph
	const top = $derived(Math.max(1, ...series.map(Math.abs)));
	const x = (t: number) => (t / maxTurns) * W;
	const y = (v: number) => H / 2 - (v / top) * (H / 2 - 4);
	const path = $derived(series.map((v, t) => `${t ? 'L' : 'M'}${x(t)},${y(v)}`).join(''));
	const lanes = $derived(
		[0, 1].flatMap((seat) => [
			{ seat, kind: 'unit_lost', label: `${names[seat]}: units lost` },
			{ seat, kind: 'core_damaged', label: `${names[seat]}: Core damaged` },
			...(invalid[seat]
				? [{ seat, kind: 'invalid_order', label: `${names[seat]}: invalid orders` }]
				: [])
		])
	);
	const marks = $derived([
		...markers,
		...[0, 1].flatMap((seat) => perTurn(invalid[seat] ?? [], seat))
	]);

	function perTurn(orders: InvalidOrder[], seat: number) {
		const counts: Record<number, number> = {};
		for (const o of orders) counts[o.turn] = (counts[o.turn] ?? 0) + 1;
		return Object.entries(counts).map(([turn, count]) => ({
			turn: Number(turn),
			seat,
			kind: 'invalid_order',
			count
		}));
	}

	function seek(event: PointerEvent) {
		const svg = event.currentTarget as SVGSVGElement;
		const box = svg.getBoundingClientRect();
		const t = Math.round(((event.clientX - box.left) / box.width) * maxTurns);
		onseek(Math.max(0, Math.min(series.length - 1, t)));
	}
</script>

<figure>
	<figcaption>
		Advantage: banked crystals plus unit value, {names[0]} above the line, {names[1]} below.
		{#if swing}
			<button type="button" class="link" onclick={() => onseek(swing.from)}>
				Biggest swing: turns {swing.from}–{swing.to} ({swing.delta > 0 ? '+' : ''}{swing.delta})
			</button>
		{/if}
	</figcaption>
	<svg
		viewBox="0 0 {W} {H + LANE * lanes.length}"
		preserveAspectRatio="none"
		onpointerdown={seek}
		role="presentation"
	>
		{#if swing}
			<rect class="swing" x={x(swing.from)} y="0" width={x(swing.to) - x(swing.from)} height={H} />
		{/if}
		<line class="axis" x1="0" x2={W} y1={H / 2} y2={H / 2} />
		<path class="line" d={path} />
		{#each lanes as lane, i (`${lane.seat}-${lane.kind}`)}
			{#each marks.filter((m) => m.seat === lane.seat && m.kind === lane.kind) as m (m.turn)}
				<rect
					class="mark {lane.kind} seat{lane.seat}"
					x={x(m.turn) - 1}
					y={H + i * LANE + 2}
					width="2"
					height={LANE - 4}
				>
					<title>{lane.label}, turn {m.turn}{m.count > 1 ? ` (${m.count})` : ''}</title>
				</rect>
			{/each}
		{/each}
		<line class="cursor" x1={x(turn)} x2={x(turn)} y1="0" y2={H + LANE * lanes.length} />
	</svg>
	<ul class="legend">
		{#each lanes as lane (`${lane.seat}-${lane.kind}`)}
			<li><span class="swatch {lane.kind} seat{lane.seat}"></span>{lane.label}</li>
		{/each}
	</ul>
</figure>

<style>
	figure {
		margin: 0;
	}
	figcaption {
		font-size: 0.875rem;
		color: var(--muted);
		margin-block-end: 0.25rem;
	}
	svg {
		display: block;
		inline-size: 100%;
		block-size: 12rem;
		cursor: crosshair;
		background: var(--surface);
		border-radius: 4px;
	}
	.axis {
		stroke: var(--line);
		vector-effect: non-scaling-stroke;
	}
	.line {
		fill: none;
		stroke: var(--ink);
		stroke-width: 1.5;
		vector-effect: non-scaling-stroke;
	}
	.swing {
		fill: var(--highlight);
	}
	.cursor {
		stroke: var(--accent);
		stroke-width: 2;
		vector-effect: non-scaling-stroke;
	}
	.mark.seat0,
	.swatch.seat0 {
		fill: var(--seat-0);
		background: var(--seat-0);
	}
	.mark.seat1,
	.swatch.seat1 {
		fill: var(--seat-1);
		background: var(--seat-1);
	}
	.mark.core_damaged,
	.swatch.core_damaged {
		opacity: 0.6;
	}
	.mark.invalid_order,
	.swatch.invalid_order {
		fill: var(--danger);
		background: var(--danger);
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		list-style: none;
		padding: 0;
		margin: 0.25rem 0 0;
		font-size: 0.8rem;
		color: var(--muted);
	}
	.swatch {
		display: inline-block;
		inline-size: 0.6rem;
		block-size: 0.6rem;
		margin-inline-end: 0.3rem;
		border-radius: 2px;
	}
</style>
