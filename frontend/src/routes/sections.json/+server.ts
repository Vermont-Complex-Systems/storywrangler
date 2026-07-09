import { json } from '@sveltejs/kit';
import { get_guide_sections } from '$lib/server/llms';
import { get_openapi_spec, get_endpoint_sections } from '$lib/server/openapi-md';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ fetch }) => {
	const sections = get_guide_sections();
	const spec = await get_openapi_spec(fetch);
	if (spec) sections.push(...get_endpoint_sections(spec));
	return json(sections);
};
