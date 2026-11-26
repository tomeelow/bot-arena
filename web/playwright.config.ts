import { defineConfig, devices } from '@playwright/test';

const PORT = 4174;

export default defineConfig({
	testDir: 'tests/e2e',
	timeout: 180_000,
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	reporter: process.env.CI ? 'line' : 'list',
	use: { baseURL: `http://localhost:${PORT}` },
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: {
		// The production build, as a static host would serve it. No API: practice needs none.
		command: `npm run build && npm run preview -- --port ${PORT} --strictPort`,
		url: `http://localhost:${PORT}/practice`,
		reuseExistingServer: !process.env.CI,
		timeout: 180_000
	}
});
