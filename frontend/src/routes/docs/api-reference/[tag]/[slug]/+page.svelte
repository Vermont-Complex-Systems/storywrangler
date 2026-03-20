<script lang="ts">
	import { page } from '$app/state';
	import * as Code from '$lib/components/ui/code';
	import { CopyButton } from '$lib/components/ui/copy-button';
	import Markdown from 'svelte-exmarkdown';
	import { gfmPlugin } from 'svelte-exmarkdown/gfm';

	const mdPlugins = [gfmPlugin()];

	let { data } = $props();

	type Operation = Record<string, unknown>;

	const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete'];

	const METHOD_BADGE: Record<string, string> = {
		get: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
		post: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
		put: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
		patch: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
		delete: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
	};

	// ── Tab state ──────────────────────────────────────────────
	let selectedLang = $state<'curl' | 'python'>('curl');
	let selectedStatus = $state('');
	let expandedFields = $state<Record<string, boolean>>({});

	// ── Helpers ────────────────────────────────────────────────
	function slugify(method: string, path: string) {
		return `${method}-${path}`.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
	}

	function resolveRef(ref: string): Operation {
		const parts = ref.replace('#/', '').split('/');
		let node: unknown = data.spec;
		for (const part of parts) node = (node as Record<string, unknown>)[part];
		return node as Operation;
	}

	function schema(s: unknown): Operation | null {
		if (!s) return null;
		const obj = s as Operation;
		if (obj.$ref) return resolveRef(obj.$ref as string);
		// Pydantic v2 wraps required nested models as allOf:[{$ref}] + description at wrapper level
		if (obj.allOf && Array.isArray(obj.allOf)) {
			const first = (obj.allOf as Operation[])[0];
			if (first?.$ref) {
				const resolved = resolveRef(first.$ref as string);
				// Wrapper description (from Field(description=...)) takes priority over class docstring
				return obj.description ? { ...resolved, description: obj.description } : resolved;
			}
		}
		return obj;
	}

	function toCurl(method: string, path: string, op: Operation): string {
		const base = 'http://localhost:8000';
		const lines: string[] = [`curl -X ${method.toUpperCase()} ${base}${path} \\`];
		if (['post', 'put', 'patch'].includes(method)) {
			lines.push(`  -H 'Authorization: Bearer <token>' \\`);
			lines.push(`  -H 'Content-Type: application/json' \\`);
			lines.push(`  -d '{}'`);
		}
		return lines.join('\n');
	}

	function toPython(method: string, path: string, op: Operation): string {
		const base = 'http://localhost:8000';
		const resolvedPath = path.replace(/\{([^}]+)\}/g, (_, p) => `<${p}>`);
		const queryParams = ((op.parameters as Operation[]) ?? []).filter((p) => p.in === 'query');
		const lines: string[] = ['import requests', ''];
		let hasPayload = false;
		if (op.requestBody) {
			const mediaType = ((op.requestBody as Operation).content as Operation)?.[
				'application/json'
			] as Operation;
			const s = schema(mediaType?.schema);
			const example = (s?.examples as unknown[])?.[0];
			if (example) {
				lines.push(`payload = ${JSON.stringify(example, null, 2)}`);
				lines.push('');
				hasPayload = true;
			}
		}
		lines.push(`response = requests.${method}(`);
		lines.push(`    "${base}${resolvedPath}",`);
		if (queryParams.length) {
			const pairs = queryParams.map((p) => `"${p.name}": "<value>"`).join(', ');
			lines.push(`    params={${pairs}},`);
		}
		if (hasPayload) lines.push('    json=payload,');
		lines.push(')');
		lines.push('print(response.json())');
		return lines.join('\n');
	}

	function statusColor(code: string): string {
		const n = parseInt(code);
		if (n >= 200 && n < 300)
			return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
		if (n >= 400 && n < 500)
			return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300';
		if (n >= 500) return 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300';
		return 'bg-muted text-foreground';
	}

	function needsAuth(op: Operation): boolean {
		const opSec = op.security as unknown[] | undefined;
		if (opSec !== undefined) return opSec.length > 0;
		const globalSec = data.spec.security as unknown[] | undefined;
		return (globalSec?.length ?? 0) > 0;
	}

	// ── All derived values — no {@const} in template needed ───
	const endpoint = $derived(
		(() => {
			const tag = page.params['tag'];
			const slug = page.params['slug'];
			if (!tag || !slug) return null;
			for (const [path, methods] of Object.entries(
				(data.spec.paths ?? {}) as Record<string, Operation>
			)) {
				for (const method of HTTP_METHODS) {
					const op = methods[method] as Operation | undefined;
					if (!op) continue;
					const tags: string[] = (op.tags as string[]) ?? ['other'];
					if (tags.includes(tag) && slugify(method, path) === slug) {
						return { method, path, op };
					}
				}
			}
			return null;
		})()
	);

	const bodyMediaType = $derived(
		endpoint?.op.requestBody
			? (((endpoint.op.requestBody as Operation).content as Operation)?.[
					'application/json'
				] as Operation) ?? null
			: null
	);

	const bodySchema = $derived(schema(bodyMediaType?.schema));

	const curlCode = $derived(endpoint ? toCurl(endpoint.method, endpoint.path, endpoint.op) : '');

	const pythonCode = $derived(
		endpoint ? toPython(endpoint.method, endpoint.path, endpoint.op) : ''
	);

	const pathParams = $derived(
		((endpoint?.op.parameters as Operation[]) ?? []).filter((p) => p.in === 'path')
	);

	const queryParams = $derived(
		((endpoint?.op.parameters as Operation[]) ?? []).filter((p) => p.in === 'query')
	);

	const responses = $derived((endpoint?.op.responses as Record<string, Operation>) ?? {});

	const statusCodes = $derived(Object.keys(responses));

	const currentResp = $derived(selectedStatus ? (responses[selectedStatus] ?? null) : null);

	const currentRespContent = $derived(
		(currentResp?.content as Record<string, Operation> | undefined)?.['application/json'] ?? null
	);

	const currentRespSchema = $derived(schema(currentRespContent?.schema));

	const currentRespExample = $derived(
		// openapi_extra sets example at media-type level; schema.example as fallback
		currentRespContent?.example ??
		currentRespSchema?.example ??
		(currentRespSchema?.examples as unknown[])?.[0] ??
		null
	);

	// Reset selected status when navigating between endpoints
	$effect(() => {
		if (!endpoint) return;
		const codes = Object.keys((endpoint.op.responses as Record<string, unknown>) ?? {});
		if (codes.length && !codes.includes(selectedStatus)) {
			selectedStatus = codes[0] ?? '';
		}
	});
</script>

{#if endpoint}
	<div class="grid grid-cols-[1fr_40%] min-h-full">
		<!-- ── Left: description + schema ───────────────────── -->
		<div class="min-w-0 overflow-hidden px-8 py-10 lg:px-14">
			<div class="max-w-2xl mx-auto">
			
			<h3 class="text-foreground mt-2 mb-1 text-xl font-semibold">
				{(endpoint.op.summary as string) ?? endpoint.path}
			</h3>
			{#if endpoint.op.description && endpoint.op.description !== endpoint.op.summary}
			<p class="text-muted-foreground mb-4 text-sm">{endpoint.op.description as string}</p>
			{/if}
			
			<div class="group font-mono text-sm mb-1 flex items-center gap-2">
				<span
					class="rounded px-1.5 py-0.5 text-xs font-semibold uppercase {METHOD_BADGE[
						endpoint.method
					]}"
				>
					{endpoint.method}
				</span>
				<span class="text-foreground">{endpoint.path}</span>
				<CopyButton
					text="https://api.storywrangler.uvm.edu{endpoint.path}"
					class="h-6 w-6 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity [&_svg]:h-3 [&_svg]:w-3"
				/>
			</div>

			<!-- Authorizations -->
			{#if needsAuth(endpoint.op)}
				<h4 class="mt-8 mb-0 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Authorizations</h4>
				<div class="mt-2 divide-y divide-border border-t border-border">
					<div class="py-4">
						<div class="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
							<span class="font-mono text-sm font-semibold text-foreground">Authorization</span>
							<code class="rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">string</code>
							<span class="text-xs font-medium text-red-600 dark:text-red-400">required</span>
						</div>
						<p class="mt-1 text-sm text-muted-foreground [&_p]:m-0 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:underline [&_a]:text-foreground">
							Bearer token. Pass as <code class="text-xs">Authorization: Bearer &lt;token&gt;</code> in the request header.
						</p>
					</div>
				</div>
			{/if}

			<!-- Path parameters -->
			{#if pathParams.length}
				<h4 class="mt-8 mb-0 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Path Parameters</h4>
				<div class="mt-2 divide-y divide-border border-t border-border">
					{#each pathParams as p (p.name)}
						<div class="py-4">
							<div class="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
								<span class="font-mono text-sm font-semibold text-foreground">{p.name as string}</span>
								{#if (p.schema as Operation)?.type}
									<code class="rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">{(p.schema as Operation).type as string}</code>
								{/if}
								{#if p.required}
									<span class="text-xs font-medium text-red-600 dark:text-red-400">required</span>
								{/if}
							</div>
							{#if p.description}
								<div class="mt-1 text-sm text-muted-foreground [&_p]:m-0 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:underline [&_a]:text-foreground"><Markdown md={p.description as string} plugins={mdPlugins} /></div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			<!-- Query parameters -->
			{#if queryParams.length}
				<h4 class="mt-8 mb-0 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Query Parameters</h4>
				<div class="mt-2 divide-y divide-border border-t border-border">
					{#each queryParams as p (p.name)}
						<div class="py-4">
							<div class="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
								<span class="font-mono text-sm font-semibold text-foreground">{p.name as string}</span>
								{#if (p.schema as Operation)?.type}
									<code class="rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">{(p.schema as Operation).type as string}</code>
								{/if}
								{#if p.required}
									<span class="text-xs font-medium text-red-600 dark:text-red-400">required</span>
								{/if}
							</div>
							{#if p.description}
								<div class="mt-1 text-sm text-muted-foreground [&_p]:m-0 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:underline [&_a]:text-foreground"><Markdown md={p.description as string} plugins={mdPlugins} /></div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			<!-- Request body (POST/PUT/PATCH) -->
			{#if bodySchema?.properties}
				<h4 class="mt-8 mb-0 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Request</h4>
				<div class="mt-2 divide-y divide-border border-t border-border">
					{#each Object.entries(bodySchema.properties as Record<string, unknown>) as [name, prop] (name)}
						{@const ps = schema(prop)}
						{@const typeLabel = ps?.type ?? (ps?.anyOf ? 'any' : ps?.properties ? 'object' : '—')}
						<div class="py-4">
							<div class="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
								<span class="font-mono text-sm font-semibold text-foreground">{name}</span>
								<code class="rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">{typeLabel}</code>
								{#if (bodySchema.required as string[])?.includes(name)}
									<span class="text-xs font-medium text-red-600 dark:text-red-400">required</span>
								{/if}
							</div>
							{#if ps?.description}
								<div class="mt-1 text-sm text-muted-foreground [&_p]:m-0 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:underline [&_a]:text-foreground"><Markdown md={ps.description as string} plugins={mdPlugins} /></div>
							{/if}
						<!-- Nested sub-fields: collapsible toggle -->
						{#if ps?.properties}
							{@const subCount = Object.keys(ps.properties as object).length}
							{@const isExpanded = expandedFields[name] ?? false}
							<button
								onclick={() => (expandedFields[name] = !isExpanded)}
								class="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
							>
								<span class="font-mono">{isExpanded ? '\u00d7' : '+'}</span>
								<span>{isExpanded ? `Hide ${subCount} properties` : `Show ${subCount} properties`}</span>
							</button>
							{#if isExpanded}
								<div class="mt-2 border-l-2 border-border pl-4">
									<table class="w-full text-sm">
										<thead>
											<tr class="border-b border-border">
												<th class="py-2 pr-3 text-left font-medium text-muted-foreground">Name</th>
												<th class="py-2 pr-3 text-left font-medium text-muted-foreground">Type</th>
												<th class="py-2 pr-3 text-left font-medium text-muted-foreground">Req</th>
												<th class="py-2 text-left font-medium text-muted-foreground">Description</th>
											</tr>
										</thead>
										<tbody class="divide-y divide-border">
											{#each Object.entries(ps.properties as Record<string, unknown>) as [subName, subProp] (subName)}
												{@const sps = schema(subProp)}
												{@const subType = sps?.type ?? (sps?.anyOf ? 'any' : sps?.properties ? 'object' : '\u2014')}
												<tr class="align-top">
													<td class="py-2.5 pr-3 font-mono font-semibold text-foreground">{subName}</td>
													<td class="py-2.5 pr-3">
														<code class="rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">{subType}</code>
													</td>
													<td class="py-2.5 pr-3 text-red-600 dark:text-red-400">
														{(ps.required as string[])?.includes(subName) ? '\u2713' : ''}
													</td>
													<td class="py-2.5 text-muted-foreground [&_p]:m-0 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:underline [&_a]:text-foreground">
														{#if sps?.description}
															<Markdown md={sps.description as string} plugins={mdPlugins} />
														{/if}
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{/if}
						{/if}
						</div>
					{/each}
				</div>
			{/if}
			</div><!-- /max-w-2xl -->
		</div>

		<!-- ── Right: code cards ─────────────────────────────── -->
		<div
			class="border-border/40 min-w-0 overflow-hidden border-l px-8 py-10 flex flex-col gap-4"
		>
			<!-- Card 1: Request sample -->
			<div class="overflow-hidden rounded-lg border-[3px] border-[#292929] shadow-[5px_5px_0px_#888] bg-[#f9f9f9] dark:bg-zinc-900 dark:border-zinc-500 dark:shadow-[5px_5px_0px_#333]">
				<div class="border-b-[3px] border-[#292929] dark:border-zinc-500 bg-[#f0f0f0] dark:bg-zinc-800 flex items-center gap-0.5 px-3 py-2">
					<button
						onclick={() => (selectedLang = 'curl')}
						class={[
							'rounded px-2 py-1 text-xs font-medium transition-colors',
							selectedLang === 'curl'
								? 'bg-background text-foreground shadow-sm'
								: 'text-muted-foreground hover:text-foreground'
						]}
					>
						curl
					</button>
					<button
						onclick={() => (selectedLang = 'python')}
						class={[
							'rounded px-2 py-1 text-xs font-medium transition-colors',
							selectedLang === 'python'
								? 'bg-background text-foreground shadow-sm'
								: 'text-muted-foreground hover:text-foreground'
						]}
					>
						python
					</button>
				</div>
				<Code.Root
					code={selectedLang === 'curl' ? curlCode : pythonCode}
					lang={selectedLang === 'curl' ? 'bash' : 'python'}
					class="rounded-none border-0"
				>
					<Code.CopyButton />
				</Code.Root>
			</div>

			<!-- Card 2: Response -->
			{#if statusCodes.length}
				<div class="overflow-hidden rounded-lg border-[3px] border-[#292929] shadow-[5px_5px_0px_#888] bg-[#f9f9f9] dark:bg-zinc-900 dark:border-zinc-500 dark:shadow-[5px_5px_0px_#333]">
					<div class="border-b-[3px] border-[#292929] dark:border-zinc-500 bg-[#f0f0f0] dark:bg-zinc-800 flex items-center gap-0.5 px-3 py-2">
						{#each statusCodes as code (code)}
							<button
								onclick={() => (selectedStatus = code)}
								class={[
									'rounded px-2 py-1 text-xs font-semibold transition-colors',
									selectedStatus === code
										? statusColor(code)
										: 'text-muted-foreground hover:text-foreground'
								]}
							>
								{code}
							</button>
						{/each}
					</div>
					<div class="px-4 py-3">
						<p class="text-muted-foreground text-xs">
							{(currentResp?.description as string) ?? ''}
						</p>
						{#if currentRespExample}
							<div class="mt-2">
								<Code.Root
									code={JSON.stringify(currentRespExample, null, 2)}
									lang="json"
									class="border-0"
								>
									<Code.CopyButton />
								</Code.Root>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="px-10 py-8 text-muted-foreground text-sm">Endpoint not found.</div>
{/if}
