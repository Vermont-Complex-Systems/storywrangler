import { env } from '$env/dynamic/public';

/**
 * Live endpoint-reference sections rendered from the backend's openapi.json.
 *
 * The backend enriches its spec with response schemas, examples, and
 * x-performance / x-frontend-notes extensions (see backend
 * app/routers/openapi_docs.py). This module turns each OpenAPI tag into a
 * markdown section at slug `api-reference/{tag}`, fetched at request time so
 * the reference can never drift from the deployed API.
 */

const CACHE_TTL_MS = 5 * 60 * 1000;
const EXCLUDED_TAGS = new Set(['admin', 'untagged']);

let cached: { spec: OpenApiSpec; at: number } | null = null;

interface OpenApiSpec {
	paths?: Record<string, Record<string, Operation>>;
}

interface Operation {
	tags?: string[];
	summary?: string;
	description?: string;
	parameters?: Parameter[];
	responses?: Record<string, ResponseObject>;
	'x-performance'?: Record<string, string>;
	'x-frontend-notes'?: Record<string, string>;
	'x-powered-by'?: string;
}

interface Parameter {
	name: string;
	in: string;
	required?: boolean;
	description?: string;
	schema?: JsonSchema;
}

interface ResponseObject {
	description?: string;
	content?: Record<string, { schema?: JsonSchema; example?: unknown; examples?: Record<string, { summary?: string; value?: unknown }> }>;
}

interface JsonSchema {
	type?: string;
	description?: string;
	format?: string;
	default?: unknown;
	properties?: Record<string, JsonSchema>;
	items?: JsonSchema;
	additionalProperties?: JsonSchema | boolean;
	anyOf?: JsonSchema[];
}

export async function get_openapi_spec(fetch_fn: typeof fetch): Promise<OpenApiSpec | null> {
	if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.spec;
	const apiUrl = env.PUBLIC_API_URL ?? 'http://localhost:3003';
	try {
		const res = await fetch_fn(`${apiUrl}/openapi.json`);
		if (!res.ok) return null;
		const spec = (await res.json()) as OpenApiSpec;
		cached = { spec, at: Date.now() };
		return spec;
	} catch {
		return null;
	}
}

function operations_by_tag(spec: OpenApiSpec): Map<string, Array<{ method: string; path: string; op: Operation }>> {
	const by_tag = new Map<string, Array<{ method: string; path: string; op: Operation }>>();
	for (const [path, methods] of Object.entries(spec.paths ?? {})) {
		for (const [method, op] of Object.entries(methods)) {
			for (const tag of op.tags ?? ['untagged']) {
				if (EXCLUDED_TAGS.has(tag)) continue;
				if (!by_tag.has(tag)) by_tag.set(tag, []);
				by_tag.get(tag)!.push({ method: method.toUpperCase(), path, op });
			}
		}
	}
	return by_tag;
}

export function get_endpoint_sections(spec: OpenApiSpec): Array<{ title: string; slug: string; use_cases: string }> {
	return [...operations_by_tag(spec).entries()].map(([tag, ops]) => ({
		title: `API reference: ${tag}`,
		slug: `api-reference/${tag}`,
		use_cases: ops
			.map(({ op }) => op.summary)
			.filter(Boolean)
			.join(', ')
	}));
}

function schema_type(schema: JsonSchema): string {
	// ' or ' rather than ' | ': these strings land inside markdown table cells.
	if (schema.anyOf) return schema.anyOf.map(schema_type).join(' or ');
	if (schema.type === 'array' && schema.items) return `array of ${schema_type(schema.items)}`;
	return schema.type ?? 'object';
}

/** Render a response schema's property descriptions as a nested bullet list. */
function schema_lines(schema: JsonSchema, indent = 0, depth = 0): string[] {
	if (depth > 4) return [];
	const lines: string[] = [];
	const pad = '  '.repeat(indent);
	for (const [name, sub] of Object.entries(schema.properties ?? {})) {
		const desc = sub.description ? ` — ${sub.description}` : '';
		lines.push(`${pad}- \`${name}\` (${schema_type(sub)})${desc}`);
		const child = sub.type === 'array' ? sub.items : sub;
		if (child?.properties) lines.push(...schema_lines(child, indent + 1, depth + 1));
		if (typeof sub.additionalProperties === 'object') {
			const ap = sub.additionalProperties;
			const ap_child = ap.type === 'array' ? ap.items : ap;
			if (ap_child?.properties) lines.push(...schema_lines(ap_child, indent + 1, depth + 1));
		}
	}
	return lines;
}

function render_parameters(params: Parameter[]): string[] {
	if (!params.length) return [];
	const lines = ['', '**Parameters**', '', '| Name | In | Type | Required | Default | Description |', '| --- | --- | --- | --- | --- | --- |'];
	for (const p of params) {
		const type = p.schema ? schema_type(p.schema) : '';
		const dflt = p.schema?.default !== undefined ? `\`${JSON.stringify(p.schema.default)}\`` : '';
		lines.push(`| \`${p.name}\` | ${p.in} | ${type} | ${p.required ? 'yes' : 'no'} | ${dflt} | ${p.description ?? ''} |`);
	}
	return lines;
}

function render_notes(title: string, notes: Record<string, string>): string[] {
	const lines = ['', `**${title}**`, ''];
	for (const [key, value] of Object.entries(notes)) {
		lines.push(`- \`${key}\`: ${value}`);
	}
	return lines;
}

function render_operation(method: string, path: string, op: Operation): string {
	const lines: string[] = [`## ${method} ${path}`];
	if (op.summary) lines.push('', op.summary);
	if (op.description) lines.push('', op.description);
	lines.push(...render_parameters(op.parameters ?? []));

	const ok = op.responses?.['200']?.content?.['application/json'];
	if (ok?.schema) {
		const body = schema_lines(ok.schema);
		if (body.length) lines.push('', '**Response**', '', ...body);
	}
	const example = ok?.example ?? Object.values(ok?.examples ?? {})[0]?.value;
	if (example !== undefined) {
		lines.push('', '**Example response**', '', '```json', JSON.stringify(example, null, 2), '```');
	}
	if (op['x-performance']) lines.push(...render_notes('Performance', op['x-performance']));
	if (op['x-frontend-notes']) lines.push(...render_notes('Usage notes', op['x-frontend-notes']));
	return lines.join('\n');
}

export function render_tag_markdown(spec: OpenApiSpec, tag: string): string | undefined {
	const ops = operations_by_tag(spec).get(tag);
	if (!ops) return undefined;
	const header = `# API reference: ${tag}\n\nGenerated from the live OpenAPI spec of the Storywrangler API.`;
	return [header, ...ops.map(({ method, path, op }) => render_operation(method, path, op))].join('\n\n');
}

export function get_tags(spec: OpenApiSpec): string[] {
	return [...operations_by_tag(spec).keys()];
}
