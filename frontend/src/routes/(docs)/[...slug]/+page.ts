import { error } from '@sveltejs/kit';
import { docs } from '$lib/docs-content';
import type { PageLoad } from './$types';

// Renders any $lib/docs markdown file at its slug URL. Docs that embed
// components do so with `<!-- Name -->` markers (registered in
// docs-components.ts), so they flow through this catch-all too — no per-doc
// route files. Only api-reference and status keep explicit routes.
export const load: PageLoad = ({ params }) => {
	const md = docs.get(params.slug);
	if (md === undefined) error(404, 'Not found');
	return { md };
};
