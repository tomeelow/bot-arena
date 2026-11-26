// The API lives on the same origin: in development Vite proxies to it (vite.config.ts).

export class ApiError extends Error {
	constructor(
		readonly status: number,
		message: string
	) {
		super(message);
	}
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, { credentials: 'same-origin', ...init });
	if (!response.ok) {
		let detail = response.statusText;
		try {
			const body = (await response.json()) as { detail?: unknown };
			if (typeof body.detail === 'string') detail = body.detail;
		} catch {
			// not JSON: keep the status text
		}
		throw new ApiError(response.status, detail);
	}
	return (await response.json()) as T;
}

export const get = <T>(path: string) => send<T>(path);

export const post = <T>(path: string, body: unknown) =>
	send<T>(path, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});

export const upload = <T>(path: string, file: Blob) =>
	send<T>(path, { method: 'POST', body: file });

/** The value, or null when the server says no (401/403/404): for owner-only data. */
export async function maybe<T>(path: string): Promise<T | null> {
	try {
		return await get<T>(path);
	} catch (e) {
		if (e instanceof ApiError && [401, 403, 404].includes(e.status)) return null;
		throw e;
	}
}

export function websocketUrl(path: string): string {
	const { protocol, host } = window.location;
	return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}${path}`;
}
