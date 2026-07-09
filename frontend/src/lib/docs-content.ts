/**
 * Documentation content map — the single load point for $lib/docs markdown.
 *
 * Universal (not server-only) so both the docs pages and the llms.txt
 * exports read the same source. Slug = path relative to $lib/docs, no
 * extension (e.g. `register`, `case-studies/wikimedia`).
 */
const modules = import.meta.glob('$lib/docs/**/*.md', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

export const docs = new Map<string, string>();
for (const [path, content] of Object.entries(modules)) {
	const slug = path.replace(/^.*\/docs\//, '').replace(/\.md$/, '');
	docs.set(slug, content);
}

export function get_title(content: string): string {
	const match = content.match(/^#\s+(.+)$/m);
	return match ? match[1].trim() : 'Untitled';
}
