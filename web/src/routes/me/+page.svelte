<script lang="ts">
	import { resolve } from '$app/paths';
	import { get, post, upload } from '#lib/api.js';
	import { session } from '#lib/session.svelte.js';
	import type { BotView } from '#lib/types.js';

	let bots = $state<BotView[]>([]);
	let name = $state('');
	let message = $state('');
	let error = $state('');

	async function reload() {
		const account = session.account;
		bots = account
			? await Promise.all(account.bots.map((b) => get<BotView>(`/api/bots/${b.id}`)))
			: [];
	}

	$effect(() => {
		session
			.load()
			.then(reload)
			.catch((e: Error) => (error = `Couldn't load your bots: ${e.message}. Reload to try again.`));
	});

	async function act(work: () => Promise<string>) {
		[message, error] = ['', ''];
		try {
			message = await work();
			await session.refresh();
			await reload();
		} catch (e) {
			error = (e as Error).message;
		}
	}

	function create(event: SubmitEvent) {
		event.preventDefault();
		void act(async () => {
			await post('/api/bots', { name });
			const created = name;
			name = '';
			return `Created ${created}. Now upload its first version.`;
		});
	}

	function send(event: SubmitEvent, bot: BotView) {
		event.preventDefault();
		const form = event.currentTarget as HTMLFormElement;
		const file = new FormData(form).get('code');
		if (!(file instanceof File) || file.size === 0) return;
		void act(async () => {
			await upload(`/api/bots/${bot.id}/versions`, file);
			form.reset();
			return `Uploaded ${file.name}. It plays a short test match first; refresh in a minute.`;
		});
	}
</script>

<svelte:head><title>My bots · Bot Arena</title></svelte:head>

<h1>My bots</h1>
{#if !session.checked}
	<p class="muted">Loading…</p>
{:else if !session.account}
	<p>
		<a href="/auth/github/login" rel="external">Log in with GitHub</a> to upload bots. We keep your GitHub
		id and handle, nothing else.
	</p>
{:else}
	{#if message}<p role="status">{message}</p>{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#each bots as bot (bot.id)}
		<section>
			<h2><a href="{resolve('/bot')}?id={bot.id}">{bot.name}</a></h2>
			<ul>
				{#each bot.versions as v (v.id)}
					<li>
						v{v.n}: <strong>{v.status}</strong>
						{#if v.status === 'pending'}<span class="muted">(playing its test match)</span>{/if}
						{#if v.error}<pre class="error">{v.error}</pre>{/if}
					</li>
				{:else}
					<li class="muted">No versions yet.</li>
				{/each}
			</ul>
			<form onsubmit={(e) => send(e, bot)}>
				<label>
					New version <input type="file" name="code" accept=".py,text/x-python" required />
				</label>
				<button type="submit">Upload</button>
			</form>
		</section>
	{/each}

	<section>
		<h2>New bot</h2>
		<form onsubmit={create}>
			<label>
				Name
				<input bind:value={name} required maxlength="40" pattern="[A-Za-z0-9_\-]+" />
			</label>
			<button type="submit">Create</button>
		</form>
		<p class="muted">
			Letters, digits, - and _. Your code stays private: nobody else can see or download it.
		</p>
	</section>
{/if}

<style>
	section {
		border-block-end: 1px solid var(--line);
		padding-block-end: 1rem;
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: center;
	}
</style>
