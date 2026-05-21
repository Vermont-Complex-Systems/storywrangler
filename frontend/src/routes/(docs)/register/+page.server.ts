import { env } from '$env/dynamic/public';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const apiUrl = env.PUBLIC_API_URL ?? 'http://localhost:3003';
	try {
		const res = await fetch(`${apiUrl}/registry/domains`);
		const { domains } = await res.json();
		return { domains: domains as string[] };
	} catch {
		return { domains: [] as string[] };
	}
};
