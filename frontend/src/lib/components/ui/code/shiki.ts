// Follows the best practices established in https://shiki.matsu.io/guide/best-performance
import { browser } from '$app/environment';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';
import { createHighlighterCore } from 'shiki/core';
import type { HighlighterCore } from 'shiki';

const bundledLanguages = {
	bash: () => import('@shikijs/langs/bash'),
	diff: () => import('@shikijs/langs/diff'),
	javascript: () => import('@shikijs/langs/javascript'),
	json: () => import('@shikijs/langs/json'),
	python: () => import('@shikijs/langs/python'),
	http: () => import('@shikijs/langs/http'),
	sql: () => import('@shikijs/langs/sql'),
	svelte: () => import('@shikijs/langs/svelte'),
	typescript: () => import('@shikijs/langs/typescript')
};

/** The languages configured for the highlighter */
export type SupportedLanguage = keyof typeof bundledLanguages;

let _highlighter: HighlighterCore | null = null;

/**
 * Load the highlighter core (no language grammars yet).
 * Returns null during SSR — the fallback plain-text <pre> is used instead.
 */
async function initHighlighter(): Promise<HighlighterCore | null> {
	if (!browser) return null;
	if (_highlighter) return _highlighter;
	_highlighter = await createHighlighterCore({
		themes: [
			import('@shikijs/themes/github-light-default'),
			import('@shikijs/themes/github-dark-default')
		],
		langs: [],
		engine: createJavaScriptRegexEngine()
	});
	return _highlighter;
}

const _coreReady = initHighlighter();

/**
 * Ensure a language grammar is loaded, then return the highlighter.
 * Languages are loaded on demand — only the ones actually used on the page.
 */
export async function getHighlighter(lang: SupportedLanguage): Promise<HighlighterCore | null> {
	const hl = await _coreReady;
	if (!hl) return null;
	if (!hl.getLoadedLanguages().includes(lang)) {
		const loader = bundledLanguages[lang];
		if (loader) await hl.loadLanguage(await loader());
	}
	return hl;
}
