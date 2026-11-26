import { describe, expect, it } from 'vitest';
import { proxy } from './proxy';

const env = { ORIGIN: 'https://arena-api.example.org', ORIGIN_SECRET: 's3cret' };

function capture() {
	const seen: { request?: Request; init?: RequestInit } = {};
	const send = (input: RequestInfo | URL, init?: RequestInit) => {
		seen.request = input as Request;
		seen.init = init;
		return Promise.resolve(new Response(null, { status: 302, headers: { location: '/' } }));
	};
	return { seen, send };
}

describe('the Pages proxy', () => {
	it('sends the request to the VM with the shared secret, replacing any the client sent', async () => {
		const { seen, send } = capture();
		const request = new Request('https://bot-arena.pages.dev/api/bots?x=1', {
			method: 'POST',
			headers: { cookie: 'session=abc', 'X-Arena-Origin': 'forged' },
			body: '{"name":"mine"}'
		});
		const response = await proxy({ request, env }, send);
		expect(seen.request?.url).toBe('https://arena-api.example.org/api/bots?x=1');
		expect(seen.request?.method).toBe('POST');
		expect(seen.request?.headers.get('X-Arena-Origin')).toBe('s3cret');
		expect(seen.request?.headers.get('cookie')).toBe('session=abc');
		expect(await seen.request?.text()).toBe('{"name":"mine"}');
		expect(seen.init?.redirect).toBe('manual');
		expect(response.status).toBe(302);
	});

	it('keeps the websocket upgrade', async () => {
		const { seen, send } = capture();
		const request = new Request('https://bot-arena.pages.dev/ws/matches/7', {
			headers: { upgrade: 'websocket' }
		});
		await proxy({ request, env }, send);
		expect(seen.request?.url).toBe('https://arena-api.example.org/ws/matches/7');
		expect(seen.request?.headers.get('upgrade')).toBe('websocket');
	});
});
