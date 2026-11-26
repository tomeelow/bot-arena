import type { PyodideAPI } from 'pyodide';

/** Where a worker finds Pyodide and the Python sources: the site root, passed in by the page. */
export interface Assets {
	root: string;
}

interface Bundle {
	files: Record<string, string>;
	example: string;
}

/** The part of Emscripten's file system we use (its types don't ship with Pyodide's). */
interface FileSystem {
	mkdirTree(path: string): void;
	writeFile(path: string, data: string): void;
}

export const SITE_PACKAGES = '/arena';
export const BOT_PATH = '/practice/my_bot.py';

/** A Pyodide interpreter with the engine and starter kit importable, and the player's code
 * written where the harness loads it. */
export async function loadPython(assets: Assets, code: string): Promise<PyodideAPI> {
	const { loadPyodide } = (await import(
		/* @vite-ignore */ `${assets.root}pyodide/pyodide.mjs`
	)) as typeof import('pyodide');
	const [pyodide, bundle] = await Promise.all([
		loadPyodide({ indexURL: `${assets.root}pyodide/` }),
		fetch(`${assets.root}practice.json`).then((r) => r.json() as Promise<Bundle>)
	]);
	const fs = pyodide.FS as FileSystem;
	const write = (path: string, text: string) => {
		fs.mkdirTree(path.slice(0, path.lastIndexOf('/')));
		fs.writeFile(path, text);
	};
	for (const [path, text] of Object.entries(bundle.files)) write(`${SITE_PACKAGES}/${path}`, text);
	write(BOT_PATH, code);
	pyodide.runPython(`import sys; sys.path.insert(0, ${JSON.stringify(SITE_PACKAGES)})`);
	return pyodide;
}

export async function example(root: string): Promise<string> {
	const bundle = (await fetch(`${root}practice.json`).then((r) => r.json())) as Bundle;
	return bundle.example;
}

/** What JavaScript sees of arena/practice.py. Keep in step with it. */
export interface PracticeModule {
	Practice(botPath: string, opponent: string, seed: number, seat: number): Practice;
	PlayerBot(botPath: string): PlayerBot;
}

export interface Practice {
	header: { toJs(options: { dict_converter: typeof Object.fromEntries }): unknown };
	to_player(): string | undefined;
	wait_ms(): number;
	/** `undefined`, not null, for no reply: Pyodide turns null into JsNull, not None. */
	from_player(line: string | undefined, ms: number, problem: string, detail: string): void;
	take_frames(): string;
	finish(stderr: string): string;
	replay(): { toJs(): Uint8Array<ArrayBuffer> };
}

export interface PlayerBot {
	answer(line: string): string | undefined;
	error: string;
}

export function practiceModule(pyodide: PyodideAPI): PracticeModule {
	return pyodide.pyimport('arena.practice') as PracticeModule;
}
