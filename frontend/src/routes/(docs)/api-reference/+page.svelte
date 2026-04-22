<script lang="ts">
	let { data } = $props();
</script>

<div class="px-8 py-10 lg:px-14 max-w-3xl mx-auto">
	<h1 class="text-foreground text-2xl font-bold mb-2">
		{(data.spec.info as Record<string, string>)?.title ?? 'API Reference'}
	</h1>
	{#if (data.spec.info as Record<string, string>)?.description}
		<p class="text-muted-foreground text-sm mb-4">
			{(data.spec.info as Record<string, string>).description}
		</p>
	{/if}
	{#if (data.spec.info as Record<string, string>)?.version}
		<p class="text-muted-foreground text-xs">
			Version: {(data.spec.info as Record<string, string>).version}
		</p>
	{/if}
</div>

