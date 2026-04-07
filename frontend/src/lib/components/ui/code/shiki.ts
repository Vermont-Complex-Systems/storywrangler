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

/** A preloaded highlighter instance (browser-only; null during SSR). */
export const highlighter: Promise<HighlighterCore | null> = browser
	? createHighlighterCore({
			themes: [
				import('@shikijs/themes/github-light-default'),
				import('@shikijs/themes/github-dark-default')
			],
			langs: Object.entries(bundledLanguages).map(([_, lang]) => lang),
			engine: createJavaScriptRegexEngine()
		})
	: Promise.resolve(null);
