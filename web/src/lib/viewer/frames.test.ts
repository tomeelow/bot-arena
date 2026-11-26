import { describe, expect, it } from 'vitest';
import type { Frame, Header } from '../types';
import { advantage, biggestSwing, decodeMask, markers } from './frames';

const header = {
	unit_stats: { w: { cost: 50, hp: 10 }, s: { cost: 80, hp: 30 }, x: { cost: 30, hp: 5 } }
} as Header;

function frame(turn: number, partial: Partial<Frame>): Frame {
	return {
		type: 'frame',
		turn,
		units: [],
		cores: [400, 400],
		banks: [0, 0],
		deposits: [],
		visible: ['', ''],
		...partial
	};
}

describe('decodeMask', () => {
	it('reads bits least significant first, row-major, as frames.py writes them', () => {
		// cells 0, 3 and 9 set: byte 0 = 0b00001001, byte 1 = 0b00000010
		const mask = decodeMask(btoa(String.fromCharCode(0b1001, 0b10)), 12);
		expect([...mask]).toEqual([1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0]);
	});
});

describe('advantage', () => {
	it('is banks plus unit cost, seat 0 minus seat 1', () => {
		const f = frame(0, {
			banks: [100, 40],
			units: [
				[0, 1, 's', 0, 0, 30, 0],
				[1, 1, 'w', 1, 1, 10, 5]
			]
		});
		expect(advantage(header, f)).toBe(100 + 80 - (40 + 50));
	});
});

describe('markers', () => {
	it('finds lost units per seat and core damage', () => {
		const a = frame(0, {
			units: [
				[0, 1, 'w', 0, 0, 10, 0],
				[0, 2, 'w', 0, 1, 10, 0],
				[1, 1, 's', 5, 5, 30, 0]
			]
		});
		const b = frame(1, { units: [[1, 1, 's', 5, 5, 30, 0]], cores: [395, 400] });
		expect(markers([a, b])).toEqual([
			{ turn: 1, seat: 0, kind: 'unit_lost', count: 2 },
			{ turn: 1, seat: 0, kind: 'core_damaged', count: 5 }
		]);
	});

	it('does not mistake the same id on the other seat for a survivor', () => {
		const a = frame(0, { units: [[0, 1, 'w', 0, 0, 10, 0]] });
		const b = frame(1, { units: [[1, 1, 'w', 0, 0, 10, 0]] });
		expect(markers([a, b]).map((m) => [m.seat, m.kind])).toEqual([[0, 'unit_lost']]);
	});
});

describe('biggestSwing', () => {
	it('finds the window with the largest change, either way', () => {
		const series = [0, 0, 10, 10, -90, -90, -80];
		expect(biggestSwing(series, 2)).toEqual({ from: 2, to: 4, delta: -100 });
	});

	it('is null for a game that never moved', () => {
		expect(biggestSwing([5, 5, 5])).toBeNull();
	});
});
