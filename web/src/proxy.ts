/** The Cloudflare Pages Function behind /api, /auth and /ws (functions/). The site and the
 * API share one origin, as the SameSite session cookie requires, while Pages serves every
 * static file: the VM's free egress (1 GB a month) carries API traffic only (ADR-010). */
export interface ProxyEnv {
	ORIGIN: string; // https://<the VM's free subdomain>
	ORIGIN_SECRET: string; // the VM's Caddy refuses requests without it
}

export function proxy(
	{ request, env }: { request: Request; env: ProxyEnv },
	send: typeof fetch = fetch
): Promise<Response> {
	const url = new URL(request.url);
	const upstream = new Request(new URL(url.pathname + url.search, env.ORIGIN), request);
	upstream.headers.set('X-Arena-Origin', env.ORIGIN_SECRET);
	// The API's redirects (login, logout) go back to the browser as they are.
	return send(upstream, { redirect: 'manual' });
}
