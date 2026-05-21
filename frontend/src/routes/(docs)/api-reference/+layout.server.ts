import { env } from '$env/dynamic/public';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch }) => {
	const apiUrl = env.PUBLIC_API_URL ?? 'http://localhost:3003';
	try {
		const [specRes, registryRes] = await Promise.all([
			fetch(`${apiUrl}/openapi.json`),
			fetch(`${apiUrl}/registry/`),
		]);
		const spec = await specRes.json();
		const registry = registryRes.ok ? await registryRes.json() : { datasets: [] };
		return { spec, datasets: registry.datasets ?? [] };
	} catch {
		return {
			spec: { info: { title: 'API Reference', description: 'Backend unavailable.' }, paths: {} },
			datasets: [],
		};
	}
};
