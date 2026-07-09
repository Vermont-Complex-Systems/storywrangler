import use_cases from '$lib/docs/use_cases.json';
import { docs, get_title } from '$lib/docs-content';
import { nav } from '$lib/nav';

/**
 * Guide sections for the llms.txt / sections.json exports.
 *
 * Section order follows the sidebar (nav.ts); docs not linked in the nav are
 * appended alphabetically, so a new .md file always shows up. use_cases.json
 * holds per-slug discovery keywords surfaced by the MCP's list-sections.
 */
const nav_order = nav
	.flatMap((section) => section.items)
	.map((item) => item.href.replace(/^\//, ''))
	.filter((slug) => docs.has(slug));

/** Strip HTML comments (component placement markers) from llms output. */
function strip_markers(content: string): string {
	return content.replace(/<!--[\s\S]*?-->\n?/g, '');
}

export interface Section {
	title: string;
	slug: string;
	use_cases: string;
}

export function get_guide_sections(): Section[] {
	const unlisted = [...docs.keys()].filter((slug) => !nav_order.includes(slug)).sort();
	return [...nav_order, ...unlisted].map((slug) => ({
		title: get_title(docs.get(slug)!),
		slug,
		use_cases: (use_cases as Record<string, string>)[slug] ?? ''
	}));
}

export function get_guide_content(slug: string): string | undefined {
	const content = docs.get(slug);
	return content === undefined ? undefined : strip_markers(content);
}

export function get_all_guide_content(): string {
	return get_guide_sections()
		.map((s) => get_guide_content(s.slug))
		.join('\n\n---\n\n');
}
