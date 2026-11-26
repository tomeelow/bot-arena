// Phase 7 exit criterion: a bot named like an exploit, with logs to match, renders as text.
import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import LadderTable from './LadderTable.svelte';
import MatchList from './MatchList.svelte';
import LogPanel from './viewer/LogPanel.svelte';
import type { LadderRow, MatchSummary } from './types';

const EVIL = '<img src=x onerror=alert(1)>';
const SCRIPT = '</pre><script>alert(2)</script>';

function noMarkup(body: string) {
	expect(body).not.toContain('<img');
	expect(body).not.toContain('<script');
	expect(body).toContain('&lt;img src=x onerror=alert(1)>');
}

describe('hostile names and logs', () => {
	it('render as text on the ladder', () => {
		const row: LadderRow = {
			rank: 1,
			version_id: 1,
			bot_id: 1,
			bot: EVIL,
			owner: EVIL,
			mu: 25,
			sigma: 2,
			score: 19,
			low: 21,
			high: 29,
			games: 10,
			provisional: false,
			p_above_next: null
		};
		noMarkup(render(LadderTable, { props: { rows: [row] } }).body);
	});

	it('render as text in match lists', () => {
		const match: MatchSummary = {
			id: 1,
			kind: 'ranked',
			status: 'done',
			players: [EVIL, 'bob/b'],
			winner_seat: 0,
			reason: 'core_destroyed'
		};
		noMarkup(render(MatchList, { props: { matches: [match] } }).body);
	});

	it('render as text in the owner log panel', () => {
		const props = {
			name: EVIL,
			logs: [[0, EVIL] as [number, string], [1, SCRIPT] as [number, string]],
			invalid: [{ turn: 1, reason: EVIL }],
			turn: 5
		};
		const body = render(LogPanel, { props }).body;
		noMarkup(body);
		expect(body).toContain('&lt;/pre>&lt;script>');
	});
});
