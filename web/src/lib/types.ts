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

/** A player as the viewer's header has it: browser practice has no ladder ids. */
export type HeaderPlayer = Pick<Player, 'seat' | 'bot' | 'owner'> & Partial<Player>;

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
	players: HeaderPlayer[];
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

/** What only a bot's owner sees of a match: its logs and the orders the engine refused. */
export interface Owned {
	logs: [number, string][];
	invalid: InvalidOrder[];
}

export interface DayCount {
	day: string;
	count: number;
}

/** Median and 95th percentile of a sample of n values; null when n is 0. */
export interface Spread {
	n: number;
	p50: number | null;
	p95: number | null;
}

export interface UsageStats {
	submitted_bots: number;
	active_players_7d: number;
	versions_per_day: DayCount[];
	matches_per_day: DayCount[];
	converged_versions: number;
	unconverged_versions: number;
	games_to_converge: Spread;
	hours_to_converge: Spread;
	seconds_to_first_match: Spread;
	rated_matches: number;
	sandbox_outcomes: Record<string, number>;
}

export interface HealthReport {
	window_h: number;
	alerts: string[];
	matches_finished: number;
	platform_errors: number;
	lease_expired: number;
	platform_error_rate: number;
	end_reasons: Record<string, number>;
	match_seconds: Spread;
	queue_depth: number;
	oldest_queued_s: number | null;
	queue_wait_s: Spread;
	worker_utilisation: number | null;
	disk_used_fraction: number;
}
