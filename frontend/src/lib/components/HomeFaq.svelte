<script lang="ts">
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { ChevronRight } from '@lucide/svelte';

	const faqs = [
		{
			question: 'What is Storywrangler?',
			answer: 'A decentralized data catalog that lets research groups register datasets once and immediately unlock analytical instruments — like the allotaxonometer — without writing any integration code. It tracks ownership, lineage, and schema compatibility so datasets remain discoverable and reproducible.',
		},
		{
			question: 'Why should I register a dataset?',
			answer: 'Registration gives your dataset schema validation, automatic instrument wiring, versioning, and discoverability across the platform. Other groups can find and build on your work, and their usage appears in your impact record automatically.',
		},
		{
			question: 'Do I need to host my data on a specific platform?',
			answer: 'No. Submitters own and manage their own Parquet files. The data can live on shared storage (like UVM netfiles), an S3 bucket, or any filesystem the API server can mount. Storywrangler only stores metadata — the files stay where you put them.',
		},
		{
			question: 'Where can I see a real example?',
			answer: 'The Wikimedia case study walks through how we registered our own Wikipedia ngrams pipeline end-to-end — from hive-partitioned parquet on shared storage to a live allotaxonometer endpoint.',
			link: '/case-studies/wikimedia',
		},
	];
</script>

<div class="not-prose space-y-2">
	{#each faqs as faq (faq.question)}
		<Collapsible.Root class="rounded-lg border border-border">
			<Collapsible.Trigger class="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-semibold text-foreground hover:bg-muted/50 transition-colors [&[data-state=open]>svg]:rotate-90">
				<ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" />
				{faq.question}
			</Collapsible.Trigger>
			<Collapsible.Content class="px-4 pb-4 pl-10 text-sm text-muted-foreground leading-relaxed">
				{faq.answer}
				{#if faq.link}
					<a href={faq.link} class="mt-2 inline-block text-foreground underline underline-offset-4">Read the case study &rarr;</a>
				{/if}
			</Collapsible.Content>
		</Collapsible.Root>
	{/each}
</div>
