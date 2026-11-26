/// <reference lib="webworker" />
// The host side of a practice match: the engine, the record and the built-in opponent, in
// Python (arena.practice.Practice). It never runs the player's code; that has its own worker.
import type { Header } from '../types';
import type { FromHost, ToHost } from './messages';
import { BOT_PATH, loadPython, practiceModule, type Practice } from './python';

let practice: Practice | null = null;
const post = (message: FromHost, transfer: Transferable[] = []) => postMessage(message, transfer);

/** Ask the player's bot for its next reply, or report the finished match. */
function advance(p: Practice, stderr: string) {
	const line = p.to_player();
	const frames = p.take_frames();
	if (line != null) {
		post({ type: 'ask', line, waitMs: p.wait_ms(), frames });
		return;
	}
	const summary = p.finish(stderr);
	const replay = p.replay().toJs();
	post({ type: 'done', frames, summary, replay }, [replay.buffer]);
}

onmessage = async (event: MessageEvent<ToHost>) => {
	const message = event.data;
	try {
		if (message.type === 'start') {
			const { setup } = message;
			const python = practiceModule(await loadPython(setup, setup.code));
			practice = python.Practice(BOT_PATH, `builtin:${setup.opponent}`, setup.seed, setup.seat);
			const header = practice.header.toJs({ dict_converter: Object.fromEntries }) as Header;
			post({ type: 'ready', header });
			advance(practice, '');
			return;
		}
		if (!practice) throw new Error('a reply arrived before the match started');
		practice.from_player(message.line ?? undefined, message.ms, message.problem, message.detail);
		advance(practice, message.stderr);
	} catch (e) {
		post({ type: 'error', message: e instanceof Error ? e.message : String(e) });
	}
};
