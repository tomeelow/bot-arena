import type { Frame, Header, Seat } from '../types';

/** How many turns a swing is measured over when looking for where the game turned. */
export const SWING_WINDOW = 10;

/** One bit per cell, row-major, as frames.py writes it. */
export function decodeMask(base64: string, cells: number): Uint8Array {
	const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
	const out = new Uint8Array(cells);
	for (let i = 0; i < cells; i++) out[i] = (bytes[i >> 3] >> (i & 7)) & 1;
	return out;
}

/** Banked crystals plus what each side's living units cost, seat 0 minus seat 1. */
export function advantage(header: Header, frame: Frame): number {
	const worth = [frame.banks[0], frame.banks[1]];
	for (const [seat, , kind] of frame.units) worth[seat] += header.unit_stats[kind].cost;
	return worth[0] - worth[1];
}

export type MarkerKind = 'unit_lost' | 'core_damaged' | 'invalid_order';

export interface Marker {
	turn: number;
	seat: Seat;
	kind: MarkerKind;
	count: number;
}

/** Units lost and Core damage, read off consecutive frames. Marked at the turn they show. */
export function markers(frames: Frame[]): Marker[] {
	const out: Marker[] = [];
	for (let i = 1; i < frames.length; i++) {
		const before = frames[i - 1];
		const after = frames[i];
		const alive = new Set(after.units.map(([seat, id]) => `${seat}:${id}`));
		for (const seat of [0, 1] as const) {
			const lost = before.units.filter(([s, id]) => s === seat && !alive.has(`${s}:${id}`));
			if (lost.length) out.push({ turn: after.turn, seat, kind: 'unit_lost', count: lost.length });
			const damage = before.cores[seat] - after.cores[seat];
			if (damage > 0) out.push({ turn: after.turn, seat, kind: 'core_damaged', count: damage });
		}
	}
	return out;
}

export interface Swing {
	from: number;
	to: number;
	delta: number;
}

/** The largest change in advantage over SWING_WINDOW turns: where the game was decided. */
export function biggestSwing(series: number[], window = SWING_WINDOW): Swing | null {
	let best: Swing | null = null;
	for (let to = 1; to < series.length; to++) {
		const from = Math.max(0, to - window);
		const delta = series[to] - series[from];
		if (!best || Math.abs(delta) > Math.abs(best.delta)) best = { from, to, delta };
	}
	return best && best.delta !== 0 ? best : null;
}
