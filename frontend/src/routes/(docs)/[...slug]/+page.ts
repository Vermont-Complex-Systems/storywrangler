import { error } from '@sveltejs/kit';
import { docs } from '$lib/docs-content';
import type { PageLoad } from './$types';

// Renders any $lib/docs markdown file at its slug URL. Pages needing embedded
// components (design, register, manifesto, specification, wikimedia case
// study) keep explicit routes, which take precedence over this catch-all.
export const load: PageLoad = ({ params }) => {
	const md = docs.get(params.slug);
	if (md === undefined) error(404, 'Not found');
	return { md };
};
