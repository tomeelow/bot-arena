/** One stop on the tour. `target` names the element carrying `data-tour="<target>"`. */
export interface Step {
	route: '/' | '/practice' | '/ladder' | '/me';
	target: string | null;
	title: string;
	body: string;
	/** a button that presses the target for the user, then moves on */
	action?: string;
	/** how long to wait for the target to appear, for one the page builds late */
	wait?: number;
	/** shown while waiting */
	waiting?: string;
}

export const STEPS: Step[] = [
	{
		route: '/',
		target: 'nav',
		title: 'Find your way around',
		body: 'Ladder ranks every bot. Rules explains the game and has the starter kit. Practice lets you write and test a bot right here. Stats shows how the site is used, and My bots is where you upload yours.'
	},
	{
		route: '/',
		target: 'start',
		title: 'Start here',
		body: 'The quickest way in is to write a bot in your browser. Nothing to install, and nothing is sent to the server.'
	},
	{
		route: '/practice',
		target: 'editor',
		title: 'This is your bot',
		body: 'A Python class that gets what its units can see each turn and answers with orders. Edit it freely: it is saved in this browser only.'
	},
	{
		route: '/practice',
		target: 'setup',
		title: 'Choose an opponent',
		body: 'Pick one of the built-in bots to play against. The seed sets the map, so the same seed and the same code always replay the same match.'
	},
	{
		route: '/practice',
		target: 'run',
		title: 'Play a match',
		body: 'Press Run to start, or let the tour press it for you. The first run loads Python, which takes a few seconds.',
		action: 'Run it for me'
	},
	{
		route: '/practice',
		target: 'viewer',
		title: 'Watch it play',
		body: 'Both bots move at the same moment, every turn. Play, pause or drag through the turns; the arrow keys step one turn at a time.',
		wait: 60_000,
		waiting: 'Loading Python and starting the match…'
	},
	{
		route: '/practice',
		target: 'vision',
		title: 'See what each bot saw',
		body: 'Switch Vision to one bot and everything it could not see goes dark. That fog is all your bot ever gets to look at.'
	},
	{
		route: '/practice',
		target: 'status',
		title: 'Read the result',
		body: 'When the match ends, the result appears here: win, loss or draw, and why. Then you can download the replay or submit your code to the ladder.'
	},
	{
		route: '/ladder',
		target: 'ladder',
		title: 'The ladder',
		body: 'Uploaded bots play each other around the clock. The ranking says how sure it is about each bot, and new bots stay provisional until they have played enough.'
	},
	{
		route: '/me',
		target: 'account',
		title: 'Join the ladder',
		body: 'Log in with GitHub to upload a bot. It plays a short test match in a sandbox first, then joins the ladder.'
	},
	{
		route: '/me',
		target: null,
		title: 'That’s the tour',
		body: 'Take it again any time from the link at the bottom of every page. Good luck on the ladder.'
	}
];
