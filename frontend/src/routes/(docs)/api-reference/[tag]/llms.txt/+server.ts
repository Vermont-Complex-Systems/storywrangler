import { error } from '@sveltejs/kit';
import { get_openapi_spec, render_tag_markdown } from '$lib/server/openapi-md';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, fetch }) => {
	const spec = await get_openapi_spec(fetch);
	if (!spec) error(503, 'Backend API unavailable — endpoint reference cannot be rendered');
	const md = render_tag_markdown(spec, params.tag);
	if (md === undefined) error(404, `No API tag '${params.tag}'`);
	return new Response(md, {
		headers: { 'Content-Type': 'text/plain; charset=utf-8' }
	});
};
