// Phase 10 exit criterion: no third-party trackers. Every request every page makes, scripts,
// styles, fonts, images, Pyodide and API calls alike, goes to this site and nowhere else.
import { expect, test } from '@playwright/test';

const PAGES = ['/', '/ladder', '/rules', '/stats', '/me', '/admin', '/practice'];

test('every page only ever talks to its own origin', async ({ page, baseURL }) => {
	const origin = new URL(baseURL ?? '').origin;
	const elsewhere: string[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.protocol.startsWith('http') && url.origin !== origin) elsewhere.push(request.url());
	});
	for (const path of PAGES) {
		await page.goto(path);
		await page.waitForLoadState('networkidle');
	}
	await page.getByRole('button', { name: 'Run' }).click();
	await expect(page.getByRole('status', { name: 'Practice status' })).toContainText(
		/You win|You lose|Draw/,
		{
			timeout: 120_000
		}
	);
	expect(elsewhere).toEqual([]);
});
