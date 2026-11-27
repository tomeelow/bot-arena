<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { MARGIN, place, spotlight, type Box } from './place';
	import { STEPS } from './steps';
	import { tour } from './state.svelte';

	const WAIT = 3000;
	const home = resolve('/');

	let dialog = $state<HTMLDialogElement>();
	let spot = $state<HTMLElement>();
	let card = $state<HTMLElement>();
	let primary = $state<HTMLButtonElement>();
	let lit = $state(false);
	let waiting = $state(false);
	// Transitions switch on once the first position is painted, so nothing glides in from 0,0.
	let placed = $state(false);

	const step = $derived(tour.index === null ? null : STEPS[tour.index]);
	const index = $derived(tour.index ?? 0);
	const last = $derived(index === STEPS.length - 1);

	$effect(() => tour.load());

	$effect(() => {
		if (!dialog) return;
		if (step && !dialog.open) {
			placed = false;
			dialog.showModal();
		} else if (!step && dialog.open) dialog.close();
	});

	$effect(() => {
		if (tour.index !== null) void tick().then(() => primary?.focus());
	});

	// Each step: open its page, wait for its target, then follow it every frame, so the
	// spotlight stays on it through scrolling, resizing and the page reflowing underneath.
	$effect(() => {
		const s = step;
		if (!s) return;
		const path = resolve(s.route);
		if (untrack(() => page.url.pathname) !== path) void goto(path, { reset: false });
		const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
		const started = performance.now();
		let target: Element | null = null;
		let scrolled = false;
		let painted = false;
		let frame = requestAnimationFrame(function follow() {
			if (s.target && !target?.isConnected) {
				target = document.querySelector(`[data-tour="${s.target}"]`);
				scrolled = false;
			}
			const r = target?.getBoundingClientRect();
			const box =
				r && r.width > 0 && r.height > 0 ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
			const view = { w: document.documentElement.clientWidth, h: innerHeight };
			if (box && !scrolled) {
				scrolled = true;
				reveal(box, view, reduce);
			}
			lit = box !== null;
			waiting = !box && s.target !== null && performance.now() - started < (s.wait ?? WAIT);
			layout(box, view);
			if (painted) placed = true;
			painted = true;
			frame = requestAnimationFrame(follow);
		});
		return () => cancelAnimationFrame(frame);
	});

	function reveal(box: Box, view: { w: number; h: number }, reduce: boolean) {
		if (box.y >= MARGIN && box.y + box.h <= view.h - MARGIN) return;
		const offset = box.h > view.h * 0.6 ? MARGIN * 2 : (view.h - box.h) / 2;
		scrollTo({ top: scrollY + box.y - offset, behavior: reduce ? 'instant' : 'smooth' });
	}

	// CSSOM writes, not style attributes: the CSP allows no inline styles.
	function layout(box: Box | null, view: { w: number; h: number }) {
		if (!spot || !card) return;
		const s = box && spotlight(box, view);
		if (s) {
			spot.style.translate = `${s.x}px ${s.y}px`;
			spot.style.width = `${s.w}px`;
			spot.style.height = `${s.h}px`;
		}
		const p = place(s, { w: card.offsetWidth, h: card.offsetHeight }, view);
		card.style.translate = `${p.x}px ${p.y}px`;
	}

	function act() {
		if (!step) return;
		document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)?.click();
		tour.go(index + 1);
	}
</script>

{#if !tour.seen && tour.index === null && page.url.pathname === home}
	<aside class="invite" aria-label="Tour">
		<p><strong>New here?</strong> A short tour shows you around and plays your first match.</p>
		<p class="buttons">
			<button type="button" class="link" onclick={() => tour.stop()}>No thanks</button>
			<button type="button" class="primary" onclick={() => tour.start()}>Show me around</button>
		</p>
	</aside>
{/if}

<dialog
	bind:this={dialog}
	class:lit
	aria-labelledby="tour-title"
	onclose={() => {
		if (tour.index !== null) tour.stop();
	}}
>
	<div class="spot" class:lit class:placed bind:this={spot} data-testid="tour-spot"></div>
	<div class="card" class:placed bind:this={card} data-testid="tour-card">
		{#if step}
			{#key index}
				<div class="content">
					<p class="count">{index + 1} of {STEPS.length}</p>
					<h2 id="tour-title">{step.title}</h2>
					<p aria-live="polite">{waiting && step.waiting ? step.waiting : step.body}</p>
					<p class="buttons">
						{#if !last}
							<button type="button" class="link" onclick={() => tour.stop()}>Skip tour</button>
						{/if}
						{#if index > 0}
							<button type="button" onclick={() => tour.go(index - 1)}>Back</button>
						{/if}
						{#if step.action}
							<button type="button" onclick={() => tour.go(index + 1)}>Next</button>
							<button type="button" class="primary" bind:this={primary} onclick={act}>
								{step.action}
							</button>
						{:else}
							<button
								type="button"
								class="primary"
								bind:this={primary}
								onclick={() => (last ? tour.stop() : tour.go(index + 1))}
							>
								{last ? 'Done' : 'Next'}
							</button>
						{/if}
					</p>
				</div>
			{/key}
		{/if}
	</div>
</dialog>

<style>
	dialog {
		position: fixed;
		inset: 0;
		inline-size: 100%;
		block-size: 100%;
		max-inline-size: none;
		max-block-size: none;
		margin: 0;
		padding: 0;
		border: 0;
		background: none;
		color: var(--ink);
		overflow: hidden;
	}
	dialog::backdrop {
		background: none;
	}
	/* no target to light: dim the whole page instead */
	dialog:not(.lit)::backdrop {
		background: var(--scrim);
	}

	.spot {
		position: absolute;
		inset: 0 auto auto 0;
		border-radius: 6px;
		box-shadow:
			0 0 0 3px var(--accent),
			0 0 0 200vmax var(--scrim);
		opacity: 0;
		pointer-events: none;
	}
	.spot.lit {
		opacity: 1;
	}
	.spot::after {
		content: '';
		position: absolute;
		inset: -10px;
		border: 2px solid var(--accent-2);
		border-radius: 10px;
		animation: breathe 1.8s ease-in-out infinite;
	}
	/* Width and height glide too: one fixed element in the top layer, so no page reflow. */
	.spot.placed {
		transition:
			translate 450ms var(--glide),
			width 450ms var(--glide),
			height 450ms var(--glide),
			opacity 200ms ease-out;
	}

	.card {
		position: absolute;
		inset: 0 auto auto 0;
		inline-size: min(25rem, 100vw - 2rem);
		box-sizing: border-box;
		padding: 1.25rem 1.25rem 1rem;
		background: var(--surface);
		border: 2px solid var(--ink);
		border-radius: 4px;
		box-shadow: var(--press-up);
	}
	.card.placed {
		transition: translate 450ms var(--glide);
	}
	.content {
		animation: rise 300ms ease-out;
	}
	.count {
		margin: 0;
		color: var(--muted);
		font-size: 0.875rem;
	}
	h2 {
		margin: 0.25rem 0 0.5rem;
		font-size: 1.375rem;
	}
	.content > p:not(.count, .buttons) {
		margin: 0 0 1.25rem;
		color: var(--ink-2);
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: flex-end;
		gap: 0.75rem;
		margin: 0;
	}
	.buttons .link {
		margin-inline-end: auto;
	}

	.invite {
		position: fixed;
		inset: auto 1rem 1rem auto;
		z-index: 1;
		inline-size: min(23rem, 100vw - 2rem);
		box-sizing: border-box;
		padding: 1rem 1.25rem;
		background: var(--surface);
		border: 2px solid var(--ink);
		border-radius: 4px;
		box-shadow: var(--press-up);
		animation: rise 400ms ease-out 500ms backwards;
	}
	.invite p {
		margin: 0 0 1rem;
	}
	.invite .buttons {
		margin: 0;
	}

	@keyframes breathe {
		0%,
		100% {
			opacity: 0;
		}
		50% {
			opacity: 1;
		}
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(0.5rem);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.spot.placed,
		.card.placed {
			transition: none;
		}
		.spot::after {
			animation: none;
			opacity: 1;
		}
		.content,
		.invite {
			animation: none;
		}
	}
</style>
