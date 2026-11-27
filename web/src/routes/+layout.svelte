<script lang="ts">
	import '@fontsource/bungee';
	import '@fontsource-variable/chivo';
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { session } from '#lib/session.svelte.js';
	import Tour from '#lib/tour/Tour.svelte';
	import { tour } from '#lib/tour/state.svelte.js';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const links = [
		[resolve('/'), 'Home'],
		[resolve('/ladder'), 'Ladder'],
		[resolve('/rules'), 'Rules & starter kit'],
		[resolve('/practice'), 'Practice'],
		[resolve('/stats'), 'Stats'],
		[resolve('/me'), 'My bots']
	] as const;

	$effect(() => {
		void session.load();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<meta name="color-scheme" content="dark" />
</svelte:head>

<header>
	<nav aria-label="Main">
		<a class="brand" href={resolve('/')}>Bot Arena</a>
		<ul data-tour="nav">
			{#each links as [href, label] (href)}
				<li>
					<a {href} aria-current={page.url.pathname === href ? 'page' : undefined}>{label}</a>
				</li>
			{/each}
		</ul>
		<span class="account" data-tour="account">
			{#if session.account}
				{session.account.handle}
				<button type="button" class="link" onclick={() => session.logout()}>Log out</button>
			{:else if session.checked}
				<a class="button" href="/auth/github/login" rel="external">Log in with GitHub</a>
			{/if}
		</span>
	</nav>
</header>

<main>
	{@render children()}
</main>

<footer class="muted">
	Engine 1.0.0 · <a href="https://github.com/tomeelow/bot-arena">Source</a> ·
	<button type="button" class="link" onclick={() => tour.start()}>Take the tour</button> · No trackers:
	we keep a GitHub id and handle, nothing else.
</footer>

<Tour />

<style>
	header {
		border-block-end: 1px solid var(--line);
	}
	nav {
		max-inline-size: 72rem;
		margin-inline: auto;
		padding: 0.9rem 1rem;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem 2rem;
	}
	.brand {
		font-family: var(--display);
		font-size: 1.2rem;
		text-transform: uppercase;
		color: var(--ink);
		text-decoration: none;
	}
	ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.25rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	ul a {
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--ink-2);
		text-decoration: none;
	}
	ul a:hover {
		color: var(--ink);
		text-decoration: underline 2px var(--accent-2);
	}
	[aria-current='page'] {
		color: var(--ink);
		text-decoration: underline 2px var(--accent);
	}
	.account {
		margin-inline-start: auto;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-weight: 700;
	}
	main {
		max-inline-size: 72rem;
		margin-inline: auto;
		padding: 2rem 1rem;
	}
	footer {
		max-inline-size: 72rem;
		margin: 4rem auto 0;
		padding: 1.5rem 1rem 2rem;
		border-block-start: 1px solid var(--line);
		font-size: 0.875rem;
	}
</style>
