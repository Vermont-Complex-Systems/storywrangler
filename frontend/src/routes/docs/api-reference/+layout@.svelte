<script lang="ts">
	import { page } from '$app/state';
	import { SvelteMap } from 'svelte/reactivity';

	let { data, children } = $props();

	type Operation = Record<string, unknown>;

	const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete'];

	const METHOD_BADGE: Record<string, string> = {
		get: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
		post: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
		put: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
		patch: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
		delete: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
	};

	function slugify(method: string, path: string) {
		return `${method}-${path}`.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
	}

	const groups = $derived(
		(() => {
			const map = new SvelteMap<string, { method: string; path: string; op: Operation }[]>();
			for (const [path, methods] of Object.entries(
				(data.spec.paths ?? {}) as Record<string, Operation>
			)) {
				for (const method of HTTP_METHODS) {
					const op = methods[method] as Operation | undefined;
					if (!op) continue;
					const tags: string[] = (op.tags as string[]) ?? ['other'];
					for (const tag of tags) {
						if (!map.has(tag)) map.set(tag, []);
						map.get(tag)!.push({ method, path, op });
					}
				}
			}
			return map;
		})()
	);

	function isActive(tag: string, method: string, path: string) {
		return page.url.pathname === `/docs/api-reference/${tag}/${slugify(method, path)}`;
	}
</script>

<div class="flex h-[calc(100vh-3.5rem)]">
	<!-- Left nav sidebar -->
	<aside
		class="border-border/40 sticky top-14 h-[calc(100vh-3.5rem)] w-60 shrink-0 overflow-y-auto border-r pl-6 pr-4 py-8 max-lg:hidden"
	>
		<nav class="flex flex-col gap-6">
			<div>
				<p class="text-foreground mb-2 text-xs font-semibold tracking-wider uppercase">Overview</p>
				<ul class="flex flex-col gap-0.5">
					<li>
						<a
							href="/docs/api-reference"
							class={[
								'text-muted-foreground hover:text-foreground block rounded-md px-2 py-1.5 text-sm transition-colors',
								page.url.pathname === '/docs/api-reference' &&
									'bg-accent text-accent-foreground font-medium'
							]}
						>
							Introduction
						</a>
					</li>
				</ul>
			</div>

			{#each groups as [tag, endpoints] (tag)}
				<div>
					<p class="text-foreground mb-2 text-xs font-semibold tracking-wider uppercase">{tag}</p>
					<ul class="flex flex-col gap-0.5">
						{#each endpoints as { method, path, op } (`${method}:${path}`)}
							<li>
								<a
									href="/docs/api-reference/{tag}/{slugify(method, path)}"
									class={[
										'text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm transition-colors',
										isActive(tag, method, path) && 'bg-accent text-accent-foreground font-medium'
									]}
								>
									<span
										class="w-8 shrink-0 rounded px-1 py-0.5 text-center text-[10px] font-semibold uppercase {METHOD_BADGE[method]}"
									>
										{method}
									</span>
									<span class="truncate">{(op.summary as string) ?? path}</span>
								</a>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</nav>
	</aside>

	<!-- Scrollable content -->
	<div class="flex-1 overflow-y-auto">
		{@render children()}
	</div>
</div>
