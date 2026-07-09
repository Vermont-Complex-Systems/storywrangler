import type { Component } from 'svelte';
import SpecsDiagram from '$lib/components/SpecsDiagram.svelte';
import InstrumentDesignDiagram from '$lib/components/InstrumentDesignDiagram.svelte';
import RegistrationFlowchart from '$lib/components/RegistrationFlowchart.svelte';
import PipelineDiagram from '$lib/components/PipelineDiagram.svelte';
import DemoVideo from '$lib/components/DemoVideo.svelte';

/**
 * Components that doc markdown can embed via `<!-- Name -->` markers.
 *
 * The [...slug] catch-all splits each doc on these markers and renders the
 * matching component between the markdown segments. Markers whose name is not
 * registered here are left alone (HTML comments render invisibly), and the
 * llms.txt exports strip all markers.
 */
export const doc_components: Record<string, Component> = {
	SpecsDiagram,
	InstrumentDesignDiagram,
	RegistrationFlowchart,
	PipelineDiagram,
	DemoVideo
};

/** Split pattern matching only registered marker names (capturing the name). */
export const marker_pattern = new RegExp(
	`<!--\\s*(${Object.keys(doc_components).join('|')})\\s*-->`
);
