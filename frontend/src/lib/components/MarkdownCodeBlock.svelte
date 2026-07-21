<script lang="ts">
	import type { Snippet } from 'svelte';
	import * as Code from '$lib/components/ui/code';
	import type { SupportedLanguage } from '$lib/components/ui/code/shiki';

	// Rendered by svelte-exmarkdown for every markdown <pre>. MarkdownDoc's
	// rehype plugin stamps data-code/data-lang on fenced code blocks; a <pre>
	// without them (raw HTML in markdown) falls through to a plain <pre>.
	let {
		'data-code': code,
		'data-lang': lang = '',
		children,
		...rest
	}: {
		'data-code'?: string;
		'data-lang'?: string;
		children?: Snippet;
		[key: string]: unknown;
	} = $props();

	// Grammars bundled in $lib/components/ui/code/shiki.ts. Anything else
	// (plain fences, ascii trees, unknown langs) renders as plain text.
	const highlightable = new Set([
		'bash',
		'diff',
		'javascript',
		'json',
		'python',
		'http',
		'sql',
		'svelte',
		'typescript'
	]);
	const aliases: Record<string, string> = {
		js: 'javascript',
		ts: 'typescript',
		py: 'python',
		sh: 'bash',
		shell: 'bash',
		zsh: 'bash'
	};

	const resolvedLang = $derived.by((): SupportedLanguage => {
		const l = aliases[lang] ?? lang;
		return highlightable.has(l) ? (l as SupportedLanguage) : 'text';
	});

	// Line numbers for real code; hidden for shell commands and plain text,
	// matching the homepage's bash usage.
	const hideLines = $derived(resolvedLang === 'bash' || resolvedLang === 'text');
</script>

{#if code !== undefined}
	<Code.Root {code} lang={resolvedLang} {hideLines} class="my-6">
		<Code.CopyButton />
	</Code.Root>
{:else}
	<pre {...rest}>{@render children?.()}</pre>
{/if}
