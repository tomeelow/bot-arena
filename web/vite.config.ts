import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

// src/csp.test.ts checks this still matches SvelteKit's announcer after an upgrade.
export const ANNOUNCER_STYLE_HASH = 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo=';

const API_PROXY = Object.fromEntries(
	['/api', '/auth', '/health', '/ws'].map((path) => [
		path,
		{ target: 'http://127.0.0.1:8000', ws: path === '/ws' }
	])
);

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter(),
			// Prerendered pages get this as a <meta> tag, with hashes added for SvelteKit's own
			// bootstrap script. Headers that a meta tag can't carry (frame-ancestors) are Phase 9's.
			csp: {
				mode: 'hash',
				directives: {
					'default-src': ['none'],
					'script-src': ['self'],
					// The one inline style allowed is SvelteKit's screen-reader route announcer.
					'style-src': ['self', 'unsafe-hashes', ANNOUNCER_STYLE_HASH],
					'img-src': ['self', 'data:'],
					'connect-src': ['self'],
					'font-src': ['self'],
					'manifest-src': ['self'],
					'base-uri': ['none'],
					'form-action': ['self'],
					'object-src': ['none']
				}
			}
		})
	],
	// `make dev-api` serves the API here; the browser sees one origin, as in production.
	server: { proxy: API_PROXY },
	preview: { proxy: API_PROXY },
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
