import { ApiError, get } from './api';
import type { Account } from './types';

/** Who is logged in, if anyone. The session cookie is HttpOnly, so we ask the API. */
class Session {
	account = $state<Account | null>(null);
	checked = $state(false);
	#loading: Promise<void> | null = null;
	#generation = 0; // bumped by logout, so a refresh that started before it can't undo it

	load(): Promise<void> {
		this.#loading ??= this.refresh();
		return this.#loading;
	}

	async refresh(): Promise<void> {
		const generation = this.#generation;
		try {
			const account = await get<Account>('/api/me');
			if (generation === this.#generation) this.account = account;
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
		const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
		if (!response.ok) throw new ApiError(response.status, 'Logging out failed; try again.');
		this.#generation += 1;
		this.account = null;
	}
}

export const session = new Session();
