<script lang="ts">
	import { ApiError, get } from '#lib/api.js';
	import { duration, share } from '#lib/format.js';
	import type { HealthReport } from '#lib/types.js';

	let report = $state<HealthReport | null>(null);
	let error = $state('');

	$effect(() => {
		get<HealthReport>('/api/admin/health')
			.then((r) => (report = r))
			.catch((e: Error) => {
				error =
					e instanceof ApiError && e.status === 401
						? 'Log in to see platform health.'
						: e instanceof ApiError && e.status === 403
							? 'Platform health is for admins only.'
							: e.message;
			});
	});
</script>

<svelte:head><title>Health · Bot Arena</title></svelte:head>

<h1>Platform health</h1>
{#if error}<p class="error">{error}</p>{/if}
{#if report}
	<h2>Alerts</h2>
	{#if report.alerts.length}
		<ul class="error">
			{#each report.alerts as alert (alert)}<li>{alert}</li>{/each}
		</ul>
	{:else}
		<p>None.</p>
	{/if}

	<h2>Last {report.window_h} hours</h2>
	<table>
		<tbody>
			<tr><td>Matches finished</td><td class="num">{report.matches_finished}</td></tr>
			<tr>
				<td>Platform errors (target 0)</td>
				<td class="num">{report.platform_errors} · {share(report.platform_error_rate)}</td>
			</tr>
			<tr><td>Leases expired (worker restarts)</td><td class="num">{report.lease_expired}</td></tr>
			<tr>
				<td>Match duration, median / 95th</td>
				<td class="num">
					{duration(report.match_seconds.p50)} / {duration(report.match_seconds.p95)}
				</td>
			</tr>
			<tr>
				<td>Queue wait, median / 95th</td>
				<td class="num">
					{duration(report.queue_wait_s.p50)} / {duration(report.queue_wait_s.p95)}
				</td>
			</tr>
			<tr>
				<td>Worker utilisation</td>
				<td class="num">
					{report.worker_utilisation === null ? '–' : share(report.worker_utilisation)}
				</td>
			</tr>
		</tbody>
	</table>

	<h2>Now</h2>
	<table>
		<tbody>
			<tr><td>Queued matches</td><td class="num">{report.queue_depth}</td></tr>
			<tr><td>Oldest queued</td><td class="num">{duration(report.oldest_queued_s)}</td></tr>
			<tr><td>Disk used</td><td class="num">{share(report.disk_used_fraction)}</td></tr>
		</tbody>
	</table>

	<h2>End reasons</h2>
	<table>
		<tbody>
			{#each Object.entries(report.end_reasons) as [reason, n] (reason)}
				<tr><td>{reason.replaceAll('_', ' ')}</td><td class="num">{n}</td></tr>
			{:else}
				<tr><td class="muted">No matches finished.</td></tr>
			{/each}
		</tbody>
	</table>
{:else if !error}
	<p class="muted">Loading…</p>
{/if}
