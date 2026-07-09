import { error } from '@sveltejs/kit';
import { get_guide_content } from '$lib/server/llms';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params }) => {
	const content = get_guide_content(params.slug);
	if (content === undefined) error(404, `No documentation section '${params.slug}'`);
	return new Response(content, {
		headers: { 'Content-Type': 'text/plain; charset=utf-8' }
	});
};
