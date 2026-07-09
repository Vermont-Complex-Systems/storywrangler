<script lang="ts">
	// Skill files synced from .claude/skills via scripts/sync_agent_assets.py —
	// canonical source is that repo dir; never edit the copies here. Printed
	// verbatim so the exact SKILL.md is what you copy into an agent.
	const GH_BASE =
		'https://github.com/Vermont-Complex-Systems/storywrangler/blob/main/.claude/skills';

	const files = import.meta.glob('$lib/skills/*.md', {
		query: '?raw',
		import: 'default',
		eager: true
	}) as Record<string, string>;

	const skills = Object.entries(files)
		.map(([path, raw]) => ({
			name: path.split('/').pop()!.replace(/\.md$/, ''),
			raw: raw.trim()
		}))
		.sort((a, b) => a.name.localeCompare(b.name));

	let copied = $state<string | null>(null);
	async function copy(name: string, raw: string) {
		try {
			await navigator.clipboard.writeText(raw);
			copied = name;
			setTimeout(() => (copied = null), 1500);
		} catch {
			/* clipboard unavailable */
		}
	}
</script>

<div class="not-prose my-6 flex flex-col gap-3">
	{#each skills as s (s.name)}
		<div class="border-border overflow-hidden rounded-lg border">
			<!-- always-visible header: filename + GitHub + Copy -->
			<div class="bg-muted/40 flex items-center justify-between gap-3 px-4 py-2">
				<span class="text-muted-foreground truncate font-mono text-xs"
					>.claude/skills/{s.name}/SKILL.md</span
				>
				<div class="flex shrink-0 items-center gap-2">
					<a
						href="{GH_BASE}/{s.name}/SKILL.md"
						target="_blank"
						rel="noopener noreferrer"
						class="border-border text-muted-foreground hover:text-foreground bg-background rounded-md border px-2.5 py-1 text-xs no-underline transition-colors"
					>
						GitHub ↗
					</a>
					<button
						onclick={() => copy(s.name, s.raw)}
						class="border-border text-muted-foreground hover:text-foreground bg-background rounded-md border px-2.5 py-1 text-xs transition-colors"
					>
						{copied === s.name ? 'Copied ✓' : 'Copy'}
					</button>
				</div>
			</div>

			<!-- collapsed skill text -->
			<details class="border-border border-t">
				<summary
					class="text-muted-foreground hover:text-foreground flex cursor-pointer items-center gap-1.5 px-4 py-2 text-xs select-none"
				>
					<svg
						class="chev h-3.5 w-3.5 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="m9 18 6-6-6-6" />
					</svg>
					View skill content
				</summary>
				<pre
					class="text-muted-foreground border-border max-h-96 overflow-auto border-t px-4 py-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">{s.raw}</pre>
			</details>
		</div>
	{/each}
</div>

<style>
	summary {
		list-style: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	.chev {
		transition: transform 0.15s ease;
	}
	details[open] .chev {
		transform: rotate(90deg);
	}
</style>
