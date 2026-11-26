import { get, websocketUrl } from '../api';
import type { End, Frame, Header, Line, MatchView } from '../types';

/**
 * A match as the viewer sees it: a header, a list of frames, and an end. A finished match
 * arrives whole; a live one over the websocket, a frame at a time. The viewer can't tell
 * the difference, so live and replay are one component.
 */
export class MatchFeed {
	header = $state<Header | null>(null);
	frames = $state.raw<Frame[]>([]);
	end = $state<End | null>(null);
	live = $state(false);
	error = $state('');
	#socket: WebSocket | null = null;

	async open(match: MatchView): Promise<void> {
		if (match.status === 'done') {
			for (const line of await get<Line[]>(`/api/matches/${match.id}/frames`)) this.#add(line);
			return;
		}
		if (match.status === 'void') {
			this.error = `This match was voided${match.void_reason ? `: ${match.void_reason}` : ''}.`;
			return;
		}
		this.live = true;
		const socket = new WebSocket(websocketUrl(`/ws/matches/${match.id}`));
		const pending: Frame[] = [];
		let scheduled = false;
		socket.onmessage = (event: MessageEvent<string>) => {
			const line = JSON.parse(event.data) as Line;
			if (line.type !== 'frame') return this.#add(line);
			// A late joiner gets hundreds of frames at once: add them in one update.
			pending.push(line);
			if (!scheduled) {
				scheduled = true;
				requestAnimationFrame(() => {
					this.frames = [...this.frames, ...pending.splice(0)];
					scheduled = false;
				});
			}
		};
		socket.onclose = (event) => {
			this.live = false;
			if (!this.end && event.code !== 1000) this.error = event.reason || 'The connection closed.';
		};
		this.#socket = socket;
	}

	close(): void {
		this.#socket?.close();
	}

	#add(line: Line): void {
		if (line.type === 'header') this.header = line;
		else if (line.type === 'frame') this.frames = [...this.frames, line];
		else this.end = line;
	}
}
