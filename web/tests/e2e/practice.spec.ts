// Phase 8 exit criteria: browser practice records the replay the CLI records for the same
// seed and bots, and a hung bot is stopped and reported without freezing the page.
import { expect, test, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';

const REPO = join(import.meta.dirname, '..', '..', '..');
const EXAMPLE = 'starter_kit/examples/first_bot.py';
const FINISHED = /You win|You lose|Draw/;

interface Replay {
	players: { seat: number; bot: string; code_sha256: string }[];
	turns: { orders: unknown; ms: unknown }[];
	[key: string]: unknown;
}

/** A replay minus what may differ: thinking times, and where the bot file lived. */
function canonical(path: string) {
	const replay = JSON.parse(gunzipSync(readFileSync(path)).toString()) as Replay;
	return {
		...replay,
		players: replay.players.map(({ seat, code_sha256 }) => ({ seat, code_sha256 })),
		turns: replay.turns.map(({ orders }) => ({ orders }))
	};
}

async function practise(
	page: Page,
	code: string | null,
	opponent: string,
	seat: number,
	seed: number
) {
	await page.goto('/practice');
	if (code !== null) await page.evaluate((c) => localStorage.setItem('practice-code', c), code);
	else await page.evaluate(() => localStorage.removeItem('practice-code'));
	await page.reload();
	await expect(page.getByRole('textbox', { name: "Your bot's Python code" })).toContainText(
		code === null ? 'class FirstBot' : 'class '
	);
	await page.getByLabel('Opponent').selectOption(opponent);
	await page.getByLabel('You play seat').selectOption(String(seat));
	await page.getByLabel('Seed').fill(String(seed));
	await page.getByRole('button', { name: 'Run' }).click();
}

for (const [opponent, seat, seed] of [
	['random', 0, 1],
	['greedy', 1, 7]
] as const) {
	test(`a practice match against ${opponent} from seat ${seat} replays as the CLI's`, async ({
		page
	}) => {
		await practise(page, null, opponent, seat, seed);
		await expect(page.getByRole('status', { name: 'Practice status' })).toContainText(FINISHED, {
			timeout: 150_000
		});
		const download = page.waitForEvent('download');
		await page.getByRole('button', { name: 'Download replay' }).click();
		const dir = mkdtempSync(join(tmpdir(), 'practice-'));
		const browser = join(dir, 'browser.json.gz');
		await (await download).saveAs(browser);

		const cli = join(dir, 'cli.json.gz');
		const bots = seat === 0 ? [EXAMPLE, `builtin:${opponent}`] : [`builtin:${opponent}`, EXAMPLE];
		execFileSync('uv', ['run', 'arena', 'match', ...bots, '--seed', String(seed), '--out', cli], {
			cwd: REPO,
			stdio: 'ignore'
		});
		expect(canonical(browser)).toEqual(canonical(cli));
	});
}

test('a hung bot is stopped and loses on time, and the page keeps responding', async ({ page }) => {
	const stuck =
		'from arena import Bot\n\n\nclass Stuck(Bot):\n    def act(self, obs):\n        while True:\n            pass\n';
	await practise(page, stuck, 'random', 0, 1);
	await expect(page.getByRole('status', { name: 'Practice status' })).toContainText('Playing', {
		timeout: 60_000
	});
	// While the bot spins, the page's own event loop must keep running on time.
	const longestStall = await page.evaluate(async () => {
		let last = performance.now();
		let worst = 0;
		const timer = setInterval(() => {
			const now = performance.now();
			worst = Math.max(worst, now - last);
			last = now;
		}, 50);
		await new Promise((r) => setTimeout(r, 3000));
		clearInterval(timer);
		return worst;
	});
	expect(longestStall).toBeLessThan(500);
	await expect(page.getByRole('status', { name: 'Practice status' })).toContainText(
		'You lose (timeout, turn 0)',
		{
			timeout: 30_000
		}
	);
	await expect(page.getByRole('status', { name: 'Practice status' })).toContainText(
		'no reply within 10000 ms'
	);
});
