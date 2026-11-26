<script lang="ts">
	import { resolve } from '$app/paths';
	import { ApiError, upload } from '#lib/api.js';
	import Editor from '#lib/practice/Editor.svelte';
	import { example } from '#lib/practice/python.js';
	import { PracticeRun } from '#lib/practice/run.svelte.js';
	import { session } from '#lib/session.svelte.js';
	import type { Owned } from '#lib/types.js';
	import Viewer from '#lib/viewer/Viewer.svelte';

	const OPPONENTS = ['random', 'greedy', 'rush', 'turtle', 'scout'];
	const SAVED = 'practice-code'; // kept in this browser only, never sent anywhere
	const root = resolve('/');

	let code = $state('');
	let opponent = $state('random');
	let seat = $state<0 | 1>(0);
	let seed = $state(randomSeed());
	let run = $state<PracticeRun | null>(null);
	let target = $state(0);
	let submitted = $state('');

	$effect(() => {
		const saved = localStorage.getItem(SAVED);
		if (saved) code = saved;
		else void example(root).then((text) => (code = text));
	});

	$effect(() => {
		if (code) localStorage.setItem(SAVED, code);
	});

	$effect(() => () => run?.stop());

	function randomSeed() {
		return Math.floor(Math.random() * 1_000_000);
	}

	function play() {
		run?.stop();
		run = new PracticeRun({ root, code, opponent, seed, seat });
	}

	async function open(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (file) code = await file.text();
	}

	async function reset() {
		code = await example(root);
	}

	function download() {
		if (!run?.replay) return;
		const url = URL.createObjectURL(new Blob([run.replay], { type: 'application/gzip' }));
		const link = document.createElement('a');
		link.href = url;
		link.download = `practice-${opponent}-seed${seed}.json.gz`;
		link.click();
		URL.revokeObjectURL(url);
	}

	async function submit() {
		submitted = '';
		try {
			await upload(`/api/bots/${target}/versions`, new Blob([code], { type: 'text/x-python' }));
			submitted = 'Uploaded. It plays a short test match first, then joins the ladder.';
		} catch (e) {
			submitted = e instanceof ApiError ? e.message : 'Upload failed.';
		}
	}

	const result = $derived.by(() => {
		const end = run?.summary?.end;
		if (!end || end.type !== 'end') return '';
		const reason = end.reason.replaceAll('_', ' ');
		if (end.winner === null) return `Draw (${reason}, turn ${end.turns}).`;
		return `${end.winner === seat ? 'You win' : 'You lose'} (${reason}, turn ${end.turns}).`;
	});
	const owned = $derived.by(() => {
		const summary = run?.summary;
		const mine = summary ? { logs: summary.logs, invalid: summary.invalid } : null;
		const both: [Owned | null, Owned | null] = seat === 0 ? [mine, null] : [null, mine];
		return both;
	});
</script>

<svelte:head><title>Practice · Bot Arena</title></svelte:head>

<h1>Practice</h1>
<p class="muted">
	Write a bot here and play it against the built-in bots, right in your browser. Nothing is
	installed and nothing is sent to the server: your code runs on your machine, in Python compiled to
	WebAssembly. Practice is <strong>unrated</strong>, and its <strong>timing is indicative</strong>:
	your computer isn't the ladder's.
</p>

<div class="layout">
	<section aria-label="Your bot">
		<Editor bind:value={code} label="Your bot's Python code" />
		<p class="row">
			<label>Open a file <input type="file" accept=".py,text/x-python" onchange={open} /></label>
			<button type="button" class="link" onclick={reset}>Start again from the example</button>
		</p>
	</section>

	<section aria-label="Match">
		<form
			class="setup"
			onsubmit={(e) => {
				e.preventDefault();
				play();
			}}
		>
			<label>
				Opponent
				<select bind:value={opponent}>
					{#each OPPONENTS as name (name)}<option value={name}>{name}</option>{/each}
				</select>
			</label>
			<label>
				You play seat
				<select bind:value={seat}>
					<option value={0}>0</option>
					<option value={1}>1</option>
				</select>
			</label>
			<label>
				Seed <input type="number" min="0" bind:value={seed} />
			</label>
			<button type="button" class="link" onclick={() => (seed = randomSeed())}>New seed</button>
			<button type="submit">
				{run && run.status !== 'done' && run.status !== 'failed' ? 'Restart' : 'Run'}
			</button>
		</form>

		<p role="status" class="status" aria-label="Practice status">
			{#if !run}
				Press Run to play. The first run loads Python, which takes a few seconds.
			{:else if run.status === 'loading'}
				Loading Python…
			{:else if run.status === 'playing'}
				Playing turn {run.frames.length ? run.frames[run.frames.length - 1].turn : 0}…
			{:else if run.status === 'done'}
				{result}
				{#if run.summary?.detail}<span class="error">{run.summary.detail}</span>{/if}
			{:else}
				<span class="error">Practice failed: {run.error}</span>
			{/if}
		</p>

		{#if run?.stderr}
			<pre class="error">{run.stderr}</pre>
		{/if}
		{#if run?.summary?.warnings.length}
			<ul class="muted">
				{#each run.summary.warnings as warning (warning)}<li>{warning}</li>{/each}
			</ul>
		{/if}

		{#if run?.status === 'done'}
			<p class="row">
				<button type="button" onclick={download}>Download replay</button>
				<span class="muted">Replay it locally with <code>arena show</code>.</span>
			</p>
			<div class="submit">
				<h2>Submit to the ladder</h2>
				{#if session.account?.bots.length}
					<label>
						As a new version of
						<select bind:value={target}>
							{#each session.account.bots as bot (bot.id)}<option value={bot.id}>
									{bot.name}
								</option>{/each}
						</select>
					</label>
					<button type="button" onclick={submit} disabled={!target}>Submit</button>
					{#if submitted}<p role="status">{submitted}</p>{/if}
				{:else if session.account}
					<p>
						<a href={resolve('/me')}>Create a bot</a> first, then submit this code as its first version.
					</p>
				{:else}
					<p>
						<a href="/auth/github/login" rel="external">Log in with GitHub</a> to submit this code.
					</p>
				{/if}
			</div>
		{/if}
	</section>
</div>

{#if run?.header}
	<Viewer
		header={run.header}
		frames={run.frames}
		end={run.summary?.end ?? null}
		live={run.status === 'playing' || run.status === 'loading'}
		{owned}
	/>
{/if}

<style>
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 3fr) minmax(16rem, 2fr);
		gap: 1.5rem;
		margin-block-end: 1.5rem;
	}
	@media (width < 56rem) {
		.layout {
			grid-template-columns: 1fr;
		}
	}
	.row,
	.setup {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: center;
	}
	input[type='number'] {
		inline-size: 7rem;
	}
	.status {
		min-block-size: 3rem;
	}
	.submit {
		border-block-start: 1px solid var(--line);
		margin-block-start: 1rem;
	}
	.submit h2 {
		font-size: 1rem;
	}
</style>
