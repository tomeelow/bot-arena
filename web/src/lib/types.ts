// What the API sends (server/src/arena_server/schemas.py and frames.py). Keep in step with it.

export interface LadderRow {
	rank: number;
	version_id: number;
	bot_id: number;
	bot: string;
	owner: string;
	mu: number;
	sigma: number;
	score: number;
	low: number;
	high: number;
	games: number;
	provisional: boolean;
	p_above_next: number | null;
}

export interface VersionView {
	id: number;
	n: number;
	status: string;
	mu: number | null;
	sigma: number | null;
	games: number;
	error: string | null;
}

export interface MatchSummary {
	id: number;
	kind: string;
	status: string;
	players: string[];
	winner_seat: number | null;
	reason: string | null;
}

export interface BotView {
	id: number;
	name: string;
	owner: string;
	versions: VersionView[];
	recent_matches: MatchSummary[];
}

export interface Account {
	handle: string;
	bots: { id: number; name: string }[];
}

export interface RatingPoint {
	match_id: number;
	version_id: number;
	mu: number;
	sigma: number;
}

export interface ComparisonView {
	id: number;
	challenger: number;
	incumbent: number;
	wins: number;
	draws: number;
	losses: number;
	pending: number;
	score: number;
	low: number;
	high: number;
	p_better: number;
	lost: number[];
}

export interface Player {
	seat: number;
	version_id: number;
	bot_id: number;
	bot: string;
	owner: string;
	version: number;
}

export interface MatchView {
	id: number;
	kind: string;
	status: string;
	seed: number;
	engine_version: string;
	players: Player[];
	result: { winner_seat: number | null; reason: string; turns: number } | null;
	void_reason: string | null;
}

export type Seat = 0 | 1;
export type UnitKind = 'w' | 's' | 'x';
/** seat, id, kind, x, y, hp, cargo */
export type UnitRow = [Seat, number, UnitKind, number, number, number, number];

export interface Header {
	type: 'header';
	width: number;
	height: number;
	max_turns: number;
	walls: [number, number][];
	cores: [number, number][];
	core_hp: number;
	unit_stats: Record<UnitKind, { cost: number; hp: number }>;
	players: Player[];
}

export interface Frame {
	type: 'frame';
	turn: number;
	units: UnitRow[];
	cores: [number, number];
	banks: [number, number];
	deposits: [number, number, number][];
	/** per seat: which cells it saw, as a base64 row-major bitmap */
	visible: [string, string];
}

export type End =
	{ type: 'end'; winner: Seat | null; reason: string; turns: number } | { type: 'void' };

export type Line = Header | Frame | End;

export interface InvalidOrder {
	turn: number;
	reason: string;
}
