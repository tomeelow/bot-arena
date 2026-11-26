<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { session } from '#lib/session.svelte.js';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const links = [
		[resolve('/'), 'Home'],
		[resolve('/ladder'), 'Ladder'],
		[resolve('/rules'), 'Rules & starter kit'],
		[resolve('/me'), 'My bots']
	] as const;

	$effect(() => {
		void session.load();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<meta name="color-scheme" content="light dark" />
</svelte:head>

<header>
	<nav aria-label="Main">
		<a class="brand" href={resolve('/')}>Bot Arena</a>
		<ul>
			{#each links as [href, label] (href)}
				<li>
					<a {href} aria-current={page.url.pathname === href ? 'page' : undefined}>{label}</a>
				</li>
			{/each}
		</ul>
		<span class="account">
			{#if session.account}
				{session.account.handle}
				<button type="button" class="link" onclick={() => session.logout()}>Log out</button>
			{:else if session.checked}
				<a href="/auth/github/login" rel="external">Log in with GitHub</a>
			{/if}
		</span>
	</nav>
</header>

<main>
	{@render children()}
</main>

<footer class="muted">
	Engine 1.0.0 · <a href="https://github.com/tomeelow/bot-arena">Source</a> · No trackers: we keep a GitHub
	id and handle, nothing else.
</footer>

<style>
	header {
		border-block-end: 1px solid var(--line);
	}
	nav {
		max-inline-size: 72rem;
		margin-inline: auto;
		padding: 0.75rem 1rem;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1.5rem;
	}
	.brand {
		font-weight: 700;
		color: var(--ink);
		text-decoration: none;
	}
	ul {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	[aria-current='page'] {
		font-weight: 600;
		text-decoration: none;
	}
	.account {
		margin-inline-start: auto;
	}
	main {
		max-inline-size: 72rem;
		margin-inline: auto;
		padding: 1rem;
	}
	footer {
		max-inline-size: 72rem;
		margin: 3rem auto 1rem;
		padding: 0 1rem;
		font-size: 0.85rem;
	}
</style>
