import type { Header } from '../types';

// What the page and the two practice workers say to each other. Protocol lines between the
// host and the player's bot are the same JSON lines the CLI and the ranked jail use.

export interface Setup {
	root: string;
	code: string;
	opponent: string;
	seed: number;
	seat: 0 | 1;
}

export type ToHost =
	| { type: 'start'; setup: Setup }
	| {
			type: 'reply';
			line: string | null;
			ms: number;
			problem: string;
			detail: string;
			stderr: string;
	  };

export type FromHost =
	| { type: 'ready'; header: Header }
	| { type: 'ask'; line: string; waitMs: number; frames: string }
	| { type: 'done'; frames: string; summary: string; replay: Uint8Array<ArrayBuffer> }
	| { type: 'error'; message: string };

export type ToPlayer =
	{ type: 'start'; root: string; code: string } | { type: 'line'; line: string };

export type FromPlayer =
	{ type: 'ready' } | { type: 'reply'; line: string | null; ms: number; error: string };
