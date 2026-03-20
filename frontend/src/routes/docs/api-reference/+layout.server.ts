import { env } from '$env/dynamic/public';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch }) => {
	const apiUrl = env.PUBLIC_API_URL ?? 'http://localhost:8000';
	const res = await fetch(`${apiUrl}/openapi.json`);
	const spec = await res.json();
	return { spec };
};
