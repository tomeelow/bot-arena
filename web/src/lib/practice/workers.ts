// Vite bundles each worker from these exact `new Worker(new URL(...))` expressions.

export const hostWorker = () =>
	new Worker(new URL('./host.worker.ts', import.meta.url), { type: 'module' });

export const playerWorker = () =>
	new Worker(new URL('./player.worker.ts', import.meta.url), { type: 'module' });
