import type { End, Frame, Header, InvalidOrder } from '../types';
import type { FromHost, FromPlayer, Setup, ToHost, ToPlayer } from './messages';
import { hostWorker, playerWorker } from './workers';

export interface Summary {
	end: End;
	detail: string;
	logs: [number, string][];
	invalid: InvalidOrder[];
	warnings: string[];
}

/**
 * One practice match: a host worker (engine and built-in opponent) and the player's bot in a
 * worker of its own. This class only carries protocol lines between them and keeps time; a
 * bot that doesn't answer within the backstop has its worker terminated and loses on time,
 * as in the CLI. The page never waits on the player's code, so a hung bot can't freeze it.
 */
export class PracticeRun {
	status = $state<'loading' | 'playing' | 'done' | 'failed'>('loading');
	header = $state<Header | null>(null);
	frames = $state.raw<Frame[]>([]);
	summary = $state<Summary | null>(null);
	error = $state('');
	stderr = $state('');
	replay: Uint8Array<ArrayBuffer> | null = null;

	#host = hostWorker();
	#player = playerWorker();
	#playerReady = false;
	#asked: { line: string; waitMs: number } | null = null;
	#timer: ReturnType<typeof setTimeout> | undefined;

	constructor(readonly setup: Setup) {
		this.#host.onmessage = (e: MessageEvent<FromHost>) => this.#fromHost(e.data);
		this.#player.onmessage = (e: MessageEvent<FromPlayer>) => this.#fromPlayer(e.data);
		this.#host.onerror = this.#player.onerror = (e) => this.#fail(e.message);
		this.#toPlayer({ type: 'start', root: setup.root, code: setup.code });
		this.#toHost({ type: 'start', setup });
	}

	stop(): void {
		clearTimeout(this.#timer);
		this.#host.terminate();
		this.#player.terminate();
	}

	#fromHost(message: FromHost): void {
		switch (message.type) {
			case 'ready':
				this.header = message.header;
				return;
			case 'ask':
				this.#addFrames(message.frames);
				this.#asked = { line: message.line, waitMs: message.waitMs };
				this.#send();
				return;
			case 'done':
				this.#addFrames(message.frames);
				this.summary = JSON.parse(message.summary) as Summary;
				this.replay = message.replay;
				this.status = 'done';
				this.stop();
				return;
			case 'error':
				this.#fail(message.message);
		}
	}

	#fromPlayer(message: FromPlayer): void {
		if (message.type === 'ready') {
			this.#playerReady = true;
			this.#send();
			return;
		}
		clearTimeout(this.#timer);
		const crashed = message.line === null;
		if (crashed) this.stderr = message.error;
		this.#toHost({
			type: 'reply',
			line: message.line,
			ms: message.ms,
			problem: crashed ? 'crash' : '',
			detail: crashed ? 'the bot raised an exception' : '',
			stderr: message.error
		});
	}

	/** The player's next line, once its Python has loaded: loading is never thinking time. */
	#send(): void {
		if (!this.#playerReady || !this.#asked) return;
		const { line, waitMs } = this.#asked;
		this.#asked = null;
		this.status = 'playing';
		this.#toPlayer({ type: 'line', line });
		this.#timer = setTimeout(() => {
			this.#player.terminate();
			this.#toHost({
				type: 'reply',
				line: null,
				ms: waitMs,
				problem: 'timeout',
				detail: `no reply within ${waitMs.toFixed(0)} ms`,
				stderr: ''
			});
		}, waitMs);
	}

	#addFrames(json: string): void {
		const fresh = JSON.parse(json) as Frame[];
		if (fresh.length) this.frames = [...this.frames, ...fresh];
	}

	#fail(message: string): void {
		this.error = message;
		this.status = 'failed';
		this.stop();
	}

	#toHost(message: ToHost): void {
		this.#host.postMessage(message);
	}

	#toPlayer(message: ToPlayer): void {
		this.#player.postMessage(message);
	}
}
