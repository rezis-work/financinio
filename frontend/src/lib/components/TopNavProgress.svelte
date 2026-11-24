<script lang="ts">
	import { navigating } from '$app/state';
</script>

{#if navigating.to !== null}
	<div
		class="fixed top-0 inset-x-0 z-[100] h-[2.5px] bg-slate-900/40 overflow-hidden pointer-events-none"
		role="progressbar"
		aria-label="Navigating to next page"
	>
		<div
			class="h-full w-1/2 rounded-full bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.8)] fin-nav-bar"
		></div>
	</div>
{/if}
