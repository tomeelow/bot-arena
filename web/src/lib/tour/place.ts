export interface Box {
	x: number;
	y: number;
	w: number;
	h: number;
}

export const MARGIN = 16;
const PAD = 8;

/** The highlight around a target: padded, and clipped to the viewport so its ring stays visible. */
export function spotlight(target: Box, view: { w: number; h: number }): Box {
	const x = Math.max(PAD / 2, target.x - PAD);
	const y = Math.max(PAD / 2, target.y - PAD);
	const right = Math.min(view.w - PAD / 2, target.x + target.w + PAD);
	const bottom = Math.min(view.h - PAD / 2, target.y + target.h + PAD);
	return { x, y, w: Math.max(0, right - x), h: Math.max(0, bottom - y) };
}

/**
 * Where the card goes: below the spotlight, else above, else beside it, whichever first fits
 * without covering it. A target too big for any of those (taller than the screen) gets the card
 * pinned to the bottom. Centred when there is no spotlight. Always inside the viewport.
 */
export function place(
	spot: Box | null,
	card: { w: number; h: number },
	view: { w: number; h: number }
): { x: number; y: number } {
	const clampX = (x: number) => Math.max(MARGIN, Math.min(x, view.w - card.w - MARGIN));
	const clampY = (y: number) => Math.max(MARGIN, Math.min(y, view.h - card.h - MARGIN));
	if (!spot) return { x: clampX((view.w - card.w) / 2), y: clampY((view.h - card.h) / 2) };
	const below = spot.y + spot.h + MARGIN;
	if (below + card.h <= view.h - MARGIN) return { x: clampX(spot.x), y: below };
	const above = spot.y - MARGIN - card.h;
	if (above >= MARGIN) return { x: clampX(spot.x), y: above };
	const right = spot.x + spot.w + MARGIN;
	if (right + card.w <= view.w - MARGIN) return { x: right, y: clampY(spot.y) };
	const left = spot.x - MARGIN - card.w;
	if (left >= MARGIN) return { x: left, y: clampY(spot.y) };
	return { x: clampX(spot.x), y: clampY(view.h - card.h - MARGIN) };
}
