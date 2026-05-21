<script lang="ts">
	import { SvelteMap, SvelteSet, SvelteDate } from 'svelte/reactivity';

	let { data } = $props();

	const datasetDays = $derived.by(() => {
		const map = new SvelteMap<
			string,
			SvelteMap<string, { status: string; avg_latency_ms: number | null; check_count: number }>
		>();
		for (const row of data.history?.history ?? []) {
			const key = `${row.domain}/${row.dataset_id}`;
			if (!map.has(key)) map.set(key, new SvelteMap());
			map.get(key)!.set(row.day?.slice(0, 10), row);
		}
		return map;
	});

	const days = $derived.by(() => {
		const result: string[] = [];
		const now = new SvelteDate();
		for (let i = 89; i >= 0; i--) {
			const d = new SvelteDate(now);
			d.setDate(d.getDate() - i);
			result.push(d.toISOString().slice(0, 10));
		}
		return result;
	});

	const datasetKeys = $derived.by(() => {
		const keys = new SvelteSet<string>();
		for (const ds of data.status?.datasets ?? []) {
			keys.add(`${ds.domain}/${ds.dataset_id}`);
		}
		for (const key of datasetDays.keys()) {
			keys.add(key);
		}
		return [...keys].sort();
	});

	function uptimePercent(dayMap: SvelteMap<string, any> | undefined): string {
		if (!dayMap || dayMap.size === 0) return '—';
		let healthy = 0;
		let total = 0;
		for (const cell of dayMap.values()) {
			total++;
			if (cell.status === 'healthy') healthy++;
		}
		if (total === 0) return '—';
		const pct = (healthy / total) * 100;
		return pct === 100 ? '100%' : `${pct.toFixed(1)}%`;
	}

	function statusColor(status: string | undefined): string {
		switch (status) {
			case 'healthy':
				return 'bg-green-500';
			case 'degraded':
				return 'bg-yellow-500';
			case 'unhealthy':
				return 'bg-red-500';
			default:
				return 'bg-zinc-200 dark:bg-zinc-700';
		}
	}

	const banner = $derived.by(() => {
		const s = data.status?.summary;
		if (!s || s.total === 0) return { text: 'No datasets monitored', classes: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400' };
		if (s.unhealthy > 0) return { text: `${s.unhealthy} dataset${s.unhealthy > 1 ? 's' : ''} unreachable`, classes: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-800' };
		if (s.degraded > 0) return { text: `${s.degraded} dataset${s.degraded > 1 ? 's' : ''} with high latency`, classes: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950 dark:text-yellow-300 dark:border-yellow-800' };
		return { text: 'All systems operational', classes: 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300 dark:border-green-800' };
	});

	function formatLatency(ms: number | null): string {
		if (ms === null) return '—';
		if (ms < 1000) return `${Math.round(ms)}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	}

	function currentStatus(key: string) {
		return (data.status?.datasets ?? []).find(
			(ds: any) => `${ds.domain}/${ds.dataset_id}` === key
		);
	}
</script>

<h1>Dataset health</h1>

<p>
	Every registered dataset is probed approximately every 15 minutes with a lightweight read test.
	Green means accessible and responsive. Yellow indicates high latency (over 10s). Red means data
	files are missing or unreadable. Gray means no probe ran that day.
</p>

<div class="not-prose my-6 rounded-lg border px-4 py-3 text-sm font-medium {banner.classes}">
	{banner.text}
</div>

{#if datasetKeys.length === 0}
	<p class="text-muted-foreground">
		No health check data yet. Probes will begin shortly after the server starts.
	</p>
{:else}
	<div class="not-prose space-y-4 my-6">
		{#each datasetKeys as key (key)}
			{@const dayMap = datasetDays.get(key)}
			{@const current = currentStatus(key)}
			<div class="rounded-lg border border-border p-4">
				<div class="flex items-center justify-between mb-3">
					<div class="flex items-center gap-2">
						{#if current}
							<span class="h-2.5 w-2.5 rounded-full {statusColor(current.status)}"></span>
						{/if}
						<span class="text-sm font-medium font-mono">{key}</span>
						{#if current?.error}
							<span class="text-xs text-red-600 dark:text-red-400 ml-2">{current.error}</span>
						{/if}
					</div>
					<span class="text-xs text-muted-foreground">
						{uptimePercent(dayMap)} uptime
					</span>
				</div>
				<div class="flex gap-px items-end">
					{#each days as day (day)}
						{@const cell = dayMap?.get(day)}
						<div
							class="flex-1 h-8 rounded-[2px] {statusColor(cell?.status)} transition-opacity hover:opacity-70"
							title="{day}: {cell?.status ?? 'no data'}{cell?.avg_latency_ms != null ? ` (${formatLatency(cell.avg_latency_ms)})` : ''}{cell?.check_count ? ` — ${cell.check_count} checks` : ''}"
						></div>
					{/each}
				</div>
				<div class="flex justify-between mt-1.5 text-[10px] text-muted-foreground">
					<span>90 days ago</span>
					<span>Today</span>
				</div>
			</div>
		{/each}
	</div>
{/if}
