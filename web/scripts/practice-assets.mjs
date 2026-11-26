// Static files browser practice loads (Phase 8), copied in before every dev or build run so
// they always match this checkout:
//   static/pyodide/       the pinned Pyodide runtime, served from our own origin
//   static/practice.json  the engine and starter-kit sources, plus the example bot
// Both are build output and gitignored. Only the Python sources ship, never platform code.
import {
	copyFileSync,
	mkdirSync,
	readdirSync,
	readFileSync,
	statSync,
	writeFileSync
} from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(web, '..');
const PYODIDE_FILES = [
	'pyodide.mjs',
	'pyodide.asm.mjs',
	'pyodide.asm.wasm',
	'python_stdlib.zip',
	'pyodide-lock.json'
];

const pyodideOut = join(web, 'static', 'pyodide');
mkdirSync(pyodideOut, { recursive: true });
for (const name of PYODIDE_FILES) {
	copyFileSync(join(web, 'node_modules', 'pyodide', name), join(pyodideOut, name));
}

/** @type {Record<string, string>} */
const files = {};
for (const [source, name] of [
	[join(repo, 'engine', 'src', 'arena_engine'), 'arena_engine'],
	[join(repo, 'starter_kit', 'src', 'arena'), 'arena']
]) {
	/** @param {string} dir */
	const walk = (dir) => {
		for (const entry of readdirSync(dir).sort()) {
			const path = join(dir, entry);
			if (statSync(path).isDirectory()) {
				if (entry !== '__pycache__') walk(path);
			} else if (entry.endsWith('.py') || entry.endsWith('.toml')) {
				files[`${name}/${relative(source, path)}`] = readFileSync(path, 'utf8');
			}
		}
	};
	walk(source);
}
const example = readFileSync(join(repo, 'starter_kit', 'examples', 'first_bot.py'), 'utf8');
writeFileSync(join(web, 'static', 'practice.json'), JSON.stringify({ files, example }));
console.log(`practice assets: ${Object.keys(files).length} Python files, Pyodide runtime`);
