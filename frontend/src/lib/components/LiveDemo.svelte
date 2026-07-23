<script lang="ts">
	import {
		scaleUtc,
		scaleLog,
		line as d3line,
		curveMonotoneX,
		extent,
		utcMonth,
		utcFormat
	} from 'd3';
	// Real, cached API responses — regenerate with scripts/fetch_demo_data.py.
	// Cached (not fetched at runtime) so the hero never depends on the backend;
	// the curl commands shown below are genuinely runnable.
	import registry from '$lib/data/demo-registry.json';
	import termdata from '$lib/data/demo-termseries.json';

	// Instrument-ready datasets (those with an endpoint_schema.type).
	const datasets = registry.filter((d) => d.type);

	// Two candidate terms compared, from /storywrangler/term-series/batch.
	// US convention: Republican red, Democrat blue.
	const COLORS: Record<string, string> = { Trump: 'text-red-500', Harris: 'text-blue-500' };
	const seriesSet = termdata.terms.map((t) => ({
		term: t.term,
		color: COLORS[t.term] ?? 'text-foreground',
		points: t.series.map((d) => ({ date: new Date(d.date), rank: d.rank }))
	}));
	const allPoints = seriesSet.flatMap((s) => s.points);
	const pointCount = seriesSet[0]?.points.length ?? 0;
	const termLabel = termdata.terms.map((t) => t.term).join(',');
	// Annotated events — semantic callouts (not derivable from the series alone).
	// Both are visible in the data: the election, and the Sep 2025 Charlie Kirk
	// spike (top_articles on 2025-09-10 confirm the driver).
	const events = [
		{ date: new Date('2024-11-06'), label: 'Nov 2024 · election' },
		{ date: new Date('2025-09-10'), label: 'Sep 2025 · Kirk' }
	];

	// Responsive width; fixed height. viewBox scales the drawing to the container.
	let width = $state(600);
	const height = 184;
	const margin = { top: 24, right: 18, bottom: 32, left: 36 };
	const ih = height - margin.top - margin.bottom;

	const innerWidth = $derived(width - margin.left - margin.right);
	const x = $derived(
		scaleUtc()
			.domain(extent(allPoints, (d) => d.date) as [Date, Date])
			.range([0, innerWidth])
	);

	// Log rank axis, inverted: rank 1 (most attention) at the top. Gridline rules
	// at powers of ten — the canonical Zipf/rank-frequency view.
	const ranks = allPoints.map((d) => d.rank);
	const rankMax = Math.max(...ranks);
	const yTop = Math.min(10, ...ranks);
	const y = scaleLog().domain([yTop, rankMax]).range([0, ih]);
	const yTicks = [1, 10, 100, 1000, 10000].filter((r) => r >= yTop && r <= rankMax);

	const paths = $derived(
		seriesSet.map((s) => ({
			term: s.term,
			color: s.color,
			d:
				d3line<{ date: Date; rank: number }>()
					.x((d) => x(d.date))
					.y((d) => y(d.rank))
					.curve(curveMonotoneX)(s.points) ?? ''
		}))
	);
	// Month-level x ticks; the year is printed only when it changes.
	const fmtMonth = utcFormat('%b');
	const fmtYear = utcFormat('%Y');
	const monthTick = utcMonth.every(3);
	const ticks = $derived(monthTick ? x.ticks(monthTick) : x.ticks(5));
</script>

<div
	class="not-prose my-8 overflow-hidden rounded-xl border border-border bg-muted/40 font-mono text-[13px] leading-relaxed"
>
	<!-- title bar -->
	<div class="flex items-center gap-2 border-b border-border px-4 py-2.5">
		<span class="flex gap-1.5" aria-hidden="true">
			<span class="h-2.5 w-2.5 rounded-full bg-red-400/70"></span>
			<span class="h-2.5 w-2.5 rounded-full bg-yellow-400/70"></span>
			<span class="h-2.5 w-2.5 rounded-full bg-green-400/70"></span>
		</span>
		<span class="text-muted-foreground text-xs">storywrangler</span>
	</div>

	<div class="space-y-4 px-4 py-4">
		<!-- step 1 — list what's in the catalog (catalog/domain/dataset_id) -->
		<div>
			<p class="text-foreground break-all">
				<span class="text-green-500">$</span> curl -s https://api.storywrangler.uvm.edu/registry/
			</p>
			<div class="mt-2 space-y-1">
				{#each datasets as d (d.domain + '/' + d.dataset_id)}
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
						<span class="text-muted-foreground">{d.catalog}/{d.domain}/{d.dataset_id}</span>
						<span
							class="rounded px-1.5 py-0.5 text-[11px] {d.type === 'time-series'
								? 'bg-orange-100 text-orange-600 dark:bg-orange-950 dark:text-orange-300'
								: 'bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-300'}">{d.type}</span
						>
					</div>
				{/each}
				<div class="text-muted-foreground/60">… and more</div>
			</div>
		</div>

		<!-- step 2 — pull two terms' trajectories, then plot them -->
		<div>
			<p class="text-foreground break-all">
				<span class="text-green-500">$</span> curl -s <span class="text-orange-500"
					>'…/storywrangler/term-series/batch?domain=wikimedia&dataset=ngrams&entity={termdata.entity}&types={termLabel}'</span
				>
			</p>
			<p class="text-muted-foreground mt-1">
				&lbrace; "results": &lbrace; "Trump": [ … {pointCount} pts ], "Harris": [ … ] &rbrace; &rbrace;
			</p>

			<!-- legend -->
			<div class="mt-3 flex items-center gap-4 text-xs">
				{#each seriesSet as s (s.term)}
					<span class="flex items-center gap-1.5">
						<span class="h-2 w-2 rounded-full {s.color}" style="background: currentColor"></span>
						<span class="text-muted-foreground">{s.term}</span>
					</span>
				{/each}
				<span class="text-muted-foreground/70 ml-auto">en.wikipedia · rank (log)</span>
			</div>

			<div class="mt-1" bind:clientWidth={width}>
				<svg
					viewBox="0 0 {width} {height}"
					class="w-full"
					role="img"
					aria-label="Wikipedia rank of the terms Trump and Harris over time on a log axis, both reaching their best rank at the November 2024 US election"
				>
					<g transform="translate({margin.left},{margin.top})">
						<!-- axis direction cue: up = lower rank = more attention -->
						<text
							x="-8"
							y="-12"
							text-anchor="start"
							fill="currentColor"
							class="text-muted-foreground/80 text-[10px]"
						>
							↑ more attention
						</text>

						<!-- y gridline rules (rank, log) + labels -->
						{#each yTicks as r (r)}
							<line
								x1="0"
								y1={y(r)}
								x2={innerWidth}
								y2={y(r)}
								class="stroke-border opacity-60"
								stroke-width="1"
							/>
							<text
								x="-8"
								y={y(r) + 3}
								text-anchor="end"
								fill="currentColor"
								class="text-muted-foreground text-[10px]"
							>
								{r}
							</text>
						{/each}

						<!-- x baseline + month/year ticks (year only when it changes) -->
						<line x1="0" y1={ih} x2={innerWidth} y2={ih} class="stroke-border" stroke-width="1" />
						{#each ticks as t, i (t.valueOf())}
							<line x1={x(t)} y1={ih} x2={x(t)} y2={ih + 3} class="stroke-border" stroke-width="1" />
							<text
								x={x(t)}
								y={ih + 14}
								text-anchor="middle"
								fill="currentColor"
								class="text-muted-foreground text-[10px]"
							>
								{fmtMonth(t)}
							</text>
							{#if i === 0 || t.getUTCFullYear() !== ticks[i - 1].getUTCFullYear()}
								<text
									x={x(t)}
									y={ih + 25}
									text-anchor="middle"
									fill="currentColor"
									class="text-muted-foreground/70 text-[10px] font-medium"
								>
									{fmtYear(t)}
								</text>
							{/if}
						{/each}

						<!-- event markers (labels extend right; events are left-to-right ordered) -->
						{#each events as e (e.label)}
							<line
								x1={x(e.date)}
								y1="0"
								x2={x(e.date)}
								y2={ih}
								class="stroke-border"
								stroke-width="1"
								stroke-dasharray="3 3"
							/>
							<text
								x={x(e.date) + 6}
								y="8"
								text-anchor="start"
								fill="currentColor"
								class="text-muted-foreground text-[10px]"
							>
								{e.label}
							</text>
						{/each}

						<!-- one line per term -->
						{#each paths as p (p.term)}
							<path
								d={p.d}
								fill="none"
								stroke="currentColor"
								class={p.color}
								stroke-width="1.5"
								stroke-linejoin="round"
								stroke-linecap="round"
							/>
						{/each}
					</g>
				</svg>
			</div>
		</div>
	</div>
</div>
