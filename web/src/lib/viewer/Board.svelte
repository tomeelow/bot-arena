<script lang="ts">
	import type { Frame, Header, Seat } from '../types';
	import { decodeMask } from './frames';

	interface Props {
		header: Header;
		frame: Frame;
		/** null: everything; a seat: only what that bot saw */
		vision: Seat | null;
	}

	let { header, frame, vision }: Props = $props();
	let canvas: HTMLCanvasElement;
	let width = $state(0);

	const walls = $derived(new Set(header.walls.map(([x, y]) => y * header.width + x)));
	const seen = $derived(
		vision === null ? null : decodeMask(frame.visible[vision], header.width * header.height)
	);

	let probe: HTMLElement;

	function colors() {
		// Custom properties come back as written (light-dark(...)), which a canvas can't use:
		// let the browser resolve each one through a real colour property.
		const read = (name: string) => {
			probe.style.color = `var(${name})`;
			return getComputedStyle(probe).color;
		};
		return {
			floor: read('--board-floor'),
			wall: read('--board-wall'),
			fog: read('--board-fog'),
			crystal: read('--board-crystal'),
			seats: [read('--seat-0'), read('--seat-1')],
			ink: read('--ink')
		};
	}

	$effect(() => {
		const ctx = canvas.getContext('2d');
		if (!ctx || width === 0) return;
		const { width: w, height: h } = header;
		const dpr = window.devicePixelRatio || 1;
		const cell = width / w;
		canvas.width = Math.round(width * dpr);
		canvas.height = Math.round(cell * h * dpr);
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		const c = colors();
		const visible = (x: number, y: number) => seen === null || seen[y * w + x] === 1;

		ctx.fillStyle = c.floor;
		ctx.fillRect(0, 0, cell * w, cell * h);
		ctx.fillStyle = c.wall;
		for (const i of walls) ctx.fillRect((i % w) * cell, Math.floor(i / w) * cell, cell, cell);

		for (const [x, y, amount] of frame.deposits) {
			ctx.globalAlpha = amount > 0 ? 1 : 0.25;
			ctx.fillStyle = c.crystal;
			ctx.beginPath();
			ctx.moveTo((x + 0.5) * cell, (y + 0.1) * cell);
			ctx.lineTo((x + 0.9) * cell, (y + 0.5) * cell);
			ctx.lineTo((x + 0.5) * cell, (y + 0.9) * cell);
			ctx.lineTo((x + 0.1) * cell, (y + 0.5) * cell);
			ctx.fill();
		}
		ctx.globalAlpha = 1;

		header.cores.forEach(([x, y], seat) => {
			ctx.fillStyle = c.seats[seat];
			ctx.fillRect(x * cell + 1, y * cell + 1, cell - 2, cell - 2);
			const hp = frame.cores[seat] / header.core_hp;
			ctx.fillStyle = c.ink;
			ctx.fillRect(x * cell, (y + 1) * cell - 3, cell * hp, 2);
		});

		for (const [seat, , kind, x, y, hp] of frame.units) {
			if (vision !== null && seat !== vision && !visible(x, y)) continue;
			const cx = (x + 0.5) * cell;
			const cy = (y + 0.5) * cell;
			const r = cell * 0.38;
			ctx.fillStyle = c.seats[seat];
			ctx.beginPath();
			if (kind === 'w') ctx.arc(cx, cy, r * 0.8, 0, Math.PI * 2);
			else if (kind === 's') ctx.rect(cx - r, cy - r, r * 2, r * 2);
			else {
				ctx.moveTo(cx, cy - r);
				ctx.lineTo(cx + r, cy + r);
				ctx.lineTo(cx - r, cy + r);
			}
			ctx.fill();
			const full = header.unit_stats[kind].hp;
			if (hp < full) {
				ctx.fillStyle = c.ink;
				ctx.fillRect(x * cell + 2, y * cell + 1, (cell - 4) * (hp / full), 2);
			}
		}

		if (seen) {
			ctx.fillStyle = c.fog;
			for (let y = 0; y < h; y++)
				for (let x = 0; x < w; x++)
					if (!visible(x, y)) ctx.fillRect(x * cell, y * cell, cell, cell);
		}
	});
</script>

<div class="board" bind:clientWidth={width}>
	<span class="probe" bind:this={probe}></span>
	<canvas bind:this={canvas}>
		Turn {frame.turn}: {frame.units.length} units on the board, Core HP {frame.cores[0]} and {frame
			.cores[1]}.
	</canvas>
</div>

<style>
	.board {
		inline-size: 100%;
	}
	.probe {
		display: none;
	}
	canvas {
		display: block;
		inline-size: 100%;
		block-size: auto;
		border-radius: 4px;
	}
</style>
