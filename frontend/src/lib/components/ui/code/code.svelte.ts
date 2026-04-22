import { Context } from 'runed';
import type { ReadableBoxedValues, WritableBoxedValues } from 'svelte-toolbelt';
import type { CodeRootProps } from '$lib/components/ui/code/types';
import { getHighlighter } from '$lib/components/ui/code/shiki';
import type { HighlighterCore } from 'shiki';

type CodeOverflowStateProps = WritableBoxedValues<{
	collapsed: boolean;
}>;

class CodeOverflowState {
	constructor(readonly opts: CodeOverflowStateProps) {
		this.toggleCollapsed = this.toggleCollapsed.bind(this);
	}

	toggleCollapsed() {
		this.opts.collapsed.current = !this.opts.collapsed.current;
	}

	get collapsed() {
		return this.opts.collapsed.current;
	}
}

type CodeRootStateProps = ReadableBoxedValues<{
	code: string;
	lang: NonNullable<CodeRootProps['lang']>;
	hideLines: boolean;
	highlight: CodeRootProps['highlight'];
}>;

class CodeRootState {
	highlighter: HighlighterCore | null = $state(null);

	constructor(
		readonly opts: CodeRootStateProps,
		readonly overflow?: CodeOverflowState
	) {
		getHighlighter(this.opts.lang.current).then((hl) => (this.highlighter = hl));
	}

	highlight(code: string) {
		return this.highlighter?.codeToHtml(code, {
			lang: this.opts.lang.current,
			themes: {
				light: 'github-light-default',
				dark: 'github-dark-default'
			},
			transformers: [
				{
					pre: (el) => {
						el.properties.style = '';

						if (!this.opts.hideLines.current) {
							el.properties.class += ' line-numbers';
						}

						return el;
					},
					line: (node, line) => {
						if (within(line, this.opts.highlight.current)) {
							node.properties.class = node.properties.class + ' line--highlighted';
						}

						return node;
					}
				}
			]
		});
	}

	get code() {
		return this.opts.code.current;
	}

	/** Plain-text fallback matching shiki's DOM structure, used during SSR and before shiki loads. */
	get fallback() {
		const escaped = this.code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
		const lines = escaped
			.split('\n')
			.map((l) => `<span class="line">${l}</span>`)
			.join('\n');
		const cls = this.opts.hideLines.current ? 'shiki' : 'shiki line-numbers';
		return `<pre class="${cls}"><code>${lines}</code></pre>`;
	}

	highlighted = $derived(this.highlight(this.code) ?? this.fallback);
}

function within(num: number, range: CodeRootProps['highlight']) {
	if (!range) return false;

	let within = false;

	for (const r of range) {
		if (typeof r === 'number') {
			if (num === r) {
				within = true;
				break;
			}
			continue;
		}

		if (r[0] <= num && num <= r[1]) {
			within = true;
			break;
		}
	}

	return within;
}

class CodeCopyButtonState {
	constructor(readonly root: CodeRootState) {}

	get code() {
		return this.root.opts.code.current;
	}
}

const overflowCtx = new Context<CodeOverflowState>('code-overflow-state');

const ctx = new Context<CodeRootState>('code-root-state');

export function useCodeOverflow(props: CodeOverflowStateProps) {
	return overflowCtx.set(new CodeOverflowState(props));
}

export function useCode(props: CodeRootStateProps) {
	return ctx.set(new CodeRootState(props, overflowCtx.getOr(undefined)));
}

export function useCodeCopyButton() {
	return new CodeCopyButtonState(ctx.get());
}
