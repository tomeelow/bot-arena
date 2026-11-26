import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { ANNOUNCER_STYLE_HASH } from '../vite.config';

describe('the CSP', () => {
	it("allows exactly the inline style of SvelteKit's route announcer", () => {
		const root = readFileSync(
			'node_modules/@sveltejs/kit/src/runtime/components/root.svelte',
			'utf8'
		);
		const style = /id="svelte-announcer"[^>]*style="([^"]*)"/.exec(root)?.[1];
		expect(style).toBeDefined();
		const hash = createHash('sha256').update(style!).digest('base64');
		expect(`sha256-${hash}`).toBe(ANNOUNCER_STYLE_HASH);
	});
});
