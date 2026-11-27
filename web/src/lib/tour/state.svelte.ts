import { STEPS } from './steps';

const SEEN = 'tour-seen'; // kept in this browser only, never sent anywhere

/** Which tour step is showing, if any, and whether this browser has been through the tour. */
class Tour {
	index = $state<number | null>(null);
	seen = $state(true);

	load(): void {
		this.seen = localStorage.getItem(SEEN) !== null;
	}

	start(): void {
		this.index = 0;
	}

	go(index: number): void {
		this.index = Math.max(0, Math.min(STEPS.length - 1, index));
	}

	stop(): void {
		this.index = null;
		this.seen = true;
		localStorage.setItem(SEEN, '1');
	}
}

export const tour = new Tour();
