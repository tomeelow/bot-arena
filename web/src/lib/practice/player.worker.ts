/// <reference lib="webworker" />
// The player's own bot, alone in this worker, behind the same harness the CLI runs. If it
// hangs, the page terminates this worker; nothing else waits on it.
import type { FromPlayer, ToPlayer } from './messages';
import { BOT_PATH, loadPython, practiceModule, type PlayerBot } from './python';

let bot: PlayerBot | null = null;
const post = (message: FromPlayer) => postMessage(message);

onmessage = async (event: MessageEvent<ToPlayer>) => {
	const message = event.data;
	if (message.type === 'start') {
		bot = practiceModule(await loadPython(message, message.code)).PlayerBot(BOT_PATH);
		post({ type: 'ready' });
		return;
	}
	if (!bot) throw new Error('a line arrived before the bot loaded');
	const start = performance.now();
	const line = bot.answer(message.line);
	const ms = performance.now() - start;
	post({ type: 'reply', line: line ?? null, ms, error: line == null ? bot.error : '' });
};
