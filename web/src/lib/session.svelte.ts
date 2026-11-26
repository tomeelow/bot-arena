import { ApiError, get } from './api';
import type { Account } from './types';

/** Who is logged in, if anyone. The session cookie is HttpOnly, so we ask the API. */
class Session {
	account = $state<Account | null>(null);
	checked = $state(false);
	#loading: Promise<void> | null = null;

	load(): Promise<void> {
		this.#loading ??= this.refresh();
		return this.#loading;
	}

	async refresh(): Promise<void> {
		try {
			this.account = await get<Account>('/api/me');
		} catch (e) {
			if (!(e instanceof ApiError && e.status === 401)) throw e;
			this.account = null;
		} finally {
			this.checked = true;
		}
	}

	owns(botId: number): boolean {
		return this.account?.bots.some((b) => b.id === botId) ?? false;
	}

	async logout(): Promise<void> {
		await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
		this.account = null;
	}
}

export const session = new Session();
