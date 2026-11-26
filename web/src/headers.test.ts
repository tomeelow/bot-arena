import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { headersFor, parseHeaders } from './headers';

const rules = parseHeaders(readFileSync('static/_headers', 'utf8'));

describe('the production headers', () => {
	it('forbid framing and sniffing on every page', () => {
		const page = headersFor(rules, '/ladder');
		expect(page.get('Content-Security-Policy')).toBe("frame-ancestors 'none'");
		expect(page.get('X-Frame-Options')).toBe('DENY');
		expect(page.get('X-Content-Type-Options')).toBe('nosniff');
	});

	it('let only the practice workers run WebAssembly, and only from this origin', () => {
		const worker = headersFor(rules, '/_app/immutable/workers/host.worker-abc.js');
		const policies = worker.get('Content-Security-Policy')?.split(', ') ?? [];
		expect(policies).toContain(
			"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'"
		);
		expect(headersFor(rules, '/practice').get('Content-Security-Policy')).not.toContain('wasm');
	});

	it('read patterns literally apart from the star', () => {
		const [rule] = parseHeaders('/a.b/*\n  X: 1\n');
		expect(rule?.pattern.test('/a.b/c/d')).toBe(true);
		expect(rule?.pattern.test('/aXb/c')).toBe(false);
		expect(() => parseHeaders('  X: 1\n')).toThrow();
	});
});
