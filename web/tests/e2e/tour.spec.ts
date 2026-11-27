// The onboarding tour: offered once on the home page, it walks every stop with the spotlight on
// the thing it describes, plays a practice match for the player, and runs under the production
// CSP (it positions through the CSSOM, which the CSP allows, never through inline styles).
import { expect, test, type Page } from '@playwright/test';

/** The spotlight surrounds the part of its target that is on screen (it keeps 4px clear of the edges). */
async function lit(page: Page, target: string, timeout = 10_000) {
	const spot = page.getByTestId('tour-spot');
	await expect(spot).toHaveCSS('opacity', '1', { timeout });
	await expect
		.poll(
			async () => {
				const view = page.viewportSize();
				const s = await spot.boundingBox();
				const t = await page.locator(`[data-tour="${target}"]`).boundingBox();
				if (!view || !s || !t) return 'missing';
				const top = Math.max(t.y, 4);
				const bottom = Math.min(t.y + t.height, view.height - 4);
				const around =
					s.x <= t.x + 1 &&
					s.x + s.width >= t.x + t.width - 1 &&
					s.y <= top + 1 &&
					s.y + s.height >= bottom - 1;
				return around ? 'around' : JSON.stringify({ spot: s, target: t });
			},
			{ message: `spotlight on ${target}`, timeout }
		)
		.toBe('around');
}

function watchForProblems(page: Page) {
	const problems: string[] = [];
	page.on('console', (m) => {
		if (m.text().includes('Content Security Policy')) problems.push(m.text());
	});
	page.on('pageerror', (e) => problems.push(e.message));
	return problems;
}

test('the tour is offered once, walks every stop and plays a match', async ({ page }) => {
	const problems = watchForProblems(page);
	await page.goto('/');
	await page.getByRole('button', { name: 'Show me around' }).click();
	const tour = page.getByRole('dialog');
	const heading = tour.getByRole('heading');

	for (const [title, target] of [
		['Find your way around', 'nav'],
		['Start here', 'start'],
		['This is your bot', 'editor'],
		['Choose an opponent', 'setup']
	]) {
		await expect(heading).toHaveText(title);
		await lit(page, target);
		await expect(tour.getByRole('button', { name: 'Next' })).toBeFocused();
		await page.keyboard.press('Enter');
	}
	await expect(page).toHaveURL(/\/practice$/);

	await expect(heading).toHaveText('Play a match');
	await lit(page, 'run');
	await tour.getByRole('button', { name: 'Run it for me' }).click();
	await expect(heading).toHaveText('Watch it play');
	await lit(page, 'viewer', 90_000);
	await expect(page.getByRole('status', { name: 'Practice status' })).not.toContainText(
		'Press Run'
	);

	for (const [title, target, path] of [
		['See what each bot saw', 'vision', /\/practice$/],
		['Read the result', 'status', /\/practice$/],
		['The ladder', 'ladder', /\/ladder$/],
		['Join the ladder', 'account', /\/me$/]
	] as const) {
		await tour.getByRole('button', { name: 'Next' }).click();
		await expect(heading).toHaveText(title);
		await expect(page).toHaveURL(path);
		await lit(page, target);
	}

	await tour.getByRole('button', { name: 'Next' }).click();
	await expect(heading).toHaveText('That’s the tour');
	await tour.getByRole('button', { name: 'Done' }).click();
	await expect(tour).toBeHidden();

	await page.goto('/');
	await expect(page.getByRole('button', { name: 'Take the tour' })).toBeVisible();
	expect(await page.evaluate(() => localStorage.getItem('tour-seen'))).toBe('1');
	await expect(page.getByRole('button', { name: 'Show me around' })).toHaveCount(0);
	expect(problems).toEqual([]);
});

test('Escape ends the tour, and the footer link starts it again', async ({ page }) => {
	const problems = watchForProblems(page);
	await page.goto('/ladder');
	await page.getByRole('button', { name: 'Take the tour' }).click();
	const tour = page.getByRole('dialog');
	await expect(tour.getByRole('heading')).toHaveText('Find your way around');
	await expect(page).toHaveURL(/\/$/);
	await lit(page, 'nav');
	await page.keyboard.press('Enter');
	await expect(tour.getByRole('heading')).toHaveText('Start here');
	await tour.getByRole('button', { name: 'Back' }).click();
	await expect(tour.getByRole('heading')).toHaveText('Find your way around');
	await page.keyboard.press('Escape');
	await expect(tour).toBeHidden();
	await expect(page.getByRole('button', { name: 'Show me around' })).toHaveCount(0);
	expect(problems).toEqual([]);
});
