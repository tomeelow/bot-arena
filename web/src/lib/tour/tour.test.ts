import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, it } from 'vitest';
import { MARGIN, place, spotlight, type Box } from './place';
import { STEPS } from './steps';

const SRC = join(import.meta.dirname, '..', '..');

function sources(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return sources(path);
		return entry.name.endsWith('.svelte') ? [readFileSync(path, 'utf8')] : [];
	});
}

it('points every step at exactly one element in the source, on a page that exists', () => {
	const all = sources(SRC).join('\n');
	for (const step of STEPS) {
		const page = join(SRC, 'routes', step.route, '+page.svelte');
		expect(() => readFileSync(page), step.route).not.toThrow();
		if (step.target === null) continue;
		const marks = all.split(`data-tour="${step.target}"`).length - 1;
		expect(marks, step.target).toBe(1);
	}
});

const VIEW = { w: 1280, h: 800 };
const CARD = { w: 400, h: 220 };

function overlaps(a: Box, b: Box) {
	return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function inside({ x, y }: { x: number; y: number }, view = VIEW, card = CARD) {
	return (
		x >= MARGIN && y >= MARGIN && x + card.w <= view.w - MARGIN && y + card.h <= view.h - MARGIN
	);
}

it('puts the card beside the spotlight, never over it, when there is room', () => {
	const targets: Box[] = [
		{ x: 20, y: 20, w: 600, h: 40 }, // the nav, top left
		{ x: 900, y: 700, w: 120, h: 44 }, // a button near the bottom right
		{ x: 40, y: 150, w: 640, h: 600 }, // the board: no room above or below, room to the right
		{ x: 600, y: 150, w: 640, h: 600 } // the same, room only to the left
	];
	for (const target of targets) {
		const spot = spotlight(target, VIEW);
		const at = place(spot, CARD, VIEW);
		expect(inside(at), JSON.stringify(target)).toBe(true);
		expect(overlaps({ ...at, ...CARD }, spot), JSON.stringify(target)).toBe(false);
	}
});

it('keeps the card on screen for a target bigger than the screen, and with none', () => {
	const phone = { w: 390, h: 844 };
	const card = { w: 358, h: 260 };
	const huge = spotlight({ x: 0, y: -200, w: 390, h: 2000 }, phone);
	expect(inside(place(huge, card, phone), phone, card)).toBe(true);
	expect(inside(place(null, card, phone), phone, card)).toBe(true);
});

it('clips the spotlight to the viewport', () => {
	const spot = spotlight({ x: -50, y: 700, w: 400, h: 400 }, VIEW);
	expect(spot.x).toBeGreaterThanOrEqual(0);
	expect(spot.y + spot.h).toBeLessThanOrEqual(VIEW.h);
});
