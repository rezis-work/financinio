<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { theme } from '$lib/stores/theme.svelte';

	let { children } = $props();

	onMount(() => {
		theme.hydrate();
		auth.hydrate();
		if ('serviceWorker' in navigator && import.meta.env.PROD) {
			navigator.serviceWorker.register('/sw.js').catch(() => {
				// ignore sw registration errors in restricted contexts
			});
		}
	});
</script>

{@render children()}
