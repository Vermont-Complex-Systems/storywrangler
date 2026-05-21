import { env } from '$env/dynamic/public';
import type { PageServerLoad } from './$types';

const EMPTY_STATUS = {
	datasets: [],
	summary: { total: 0, healthy: 0, degraded: 0, unhealthy: 0 }
};

const EMPTY_HISTORY = { days: 90, since: '', history: [] as unknown[] };

export const load: PageServerLoad = async ({ fetch }) => {
	const apiUrl = env.PUBLIC_API_URL ?? 'http://localhost:3003';
	try {
		const [statusRes, historyRes] = await Promise.all([
			fetch(`${apiUrl}/health/status`),
			fetch(`${apiUrl}/health/status/history?days=90`)
		]);
		const status = statusRes.ok ? await statusRes.json() : EMPTY_STATUS;
		const history = historyRes.ok ? await historyRes.json() : EMPTY_HISTORY;
		return { status, history };
	} catch {
		return { status: EMPTY_STATUS, history: EMPTY_HISTORY };
	}
};
