import { get_all_guide_content } from '$lib/server/llms';
import { get_openapi_spec, get_tags, render_tag_markdown } from '$lib/server/openapi-md';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
	const parts = ['# Storywrangler Documentation', get_all_guide_content()];
	const spec = await get_openapi_spec(fetch);
	if (spec) {
		for (const tag of get_tags(spec)) {
			const md = render_tag_markdown(spec, tag);
			if (md) parts.push(md);
		}
	}
	return new Response(parts.join('\n\n---\n\n'), {
		headers: { 'Content-Type': 'text/plain; charset=utf-8' }
	});
};
