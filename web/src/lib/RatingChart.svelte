<script lang="ts">
	import type { RatingPoint, VersionView } from './types';

	let { points, versions }: { points: RatingPoint[]; versions: VersionView[] } = $props();

	const W = 800;
	const H = 220;
	const PAD = 24;
	const lo = $derived(Math.min(...points.map((p) => p.mu - 2 * p.sigma)));
	const hi = $derived(Math.max(...points.map((p) => p.mu + 2 * p.sigma)));
	const x = (i: number) => PAD + (i / Math.max(1, points.length - 1)) * (W - 2 * PAD);
	const y = (v: number) => H - PAD - ((v - lo) / (hi - lo || 1)) * (H - 2 * PAD);
	const number = (id: number) => versions.find((v) => v.id === id)?.n ?? '?';

	// One band and one line per version: a new version starts again with full uncertainty.
	const runs = $derived(
		[...new Set(points.map((p) => p.version_id))].map((id) => {
			const at = points.flatMap((p, i) => (p.version_id === id ? [[i, p] as const] : []));
			const upper = at.map(([i, p]) => `${x(i)},${y(p.mu + 2 * p.sigma)}`);
			const lower = at.map(([i, p]) => `${x(i)},${y(p.mu - 2 * p.sigma)}`).reverse();
			return {
				id,
				band: `M${[...upper, ...lower].join('L')}Z`,
				line: `M${at.map(([i, p]) => `${x(i)},${y(p.mu)}`).join('L')}`,
				last: at[at.length - 1]
			};
		})
	);
</script>

<figure>
	<svg viewBox="0 0 {W} {H}" role="img" aria-label="Rating after each rated game, μ with a 2σ band">
		<text x={PAD} y="14" class="tick">{hi.toFixed(0)}</text>
		<text x={PAD} y={H - 6} class="tick">{lo.toFixed(0)}</text>
		{#each runs as run (run.id)}
			<path class="band" d={run.band} />
			<path class="line" d={run.line} />
			<text x={x(run.last[0]) - 4} y={y(run.last[1].mu) - 8} class="label">v{number(run.id)}</text>
		{/each}
	</svg>
	<figcaption class="muted">
		μ after each rated game, with the shaded band at μ ± 2σ. The band narrows as the platform
		becomes more sure; it is the uncertainty, not noise.
	</figcaption>
</figure>

<style>
	figure {
		margin: 0;
	}
	svg {
		inline-size: 100%;
		block-size: auto;
		background: var(--surface);
		border-radius: 4px;
	}
	.band {
		fill: var(--accent);
		opacity: 0.18;
	}
	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2;
	}
	.tick,
	.label {
		fill: var(--muted);
		font-size: 12px;
	}
	.label {
		text-anchor: end;
	}
	figcaption {
		font-size: 0.85rem;
	}
</style>
