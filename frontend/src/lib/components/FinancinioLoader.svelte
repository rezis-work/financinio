<script lang="ts">
	import { onMount } from 'svelte';
	import { Sparkles } from 'lucide-svelte';

	let {
		fullscreen = true,
		label = 'Loading Financinio',
		subtitles = [
			'Syncing encrypted ledger...',
			'Calculating real-time cash flow...',
			'Preparing Luna Personal CFO...'
		]
	}: {
		fullscreen?: boolean;
		label?: string;
		subtitles?: string[];
	} = $props();

	let subtitleIdx = $state(0);

	onMount(() => {
		if (subtitles.length <= 1) return;
		const timer = setInterval(() => {
			subtitleIdx = (subtitleIdx + 1) % subtitles.length;
		}, 1700);
		return () => clearInterval(timer);
	});
</script>

<div
	class="{fullscreen
		? 'min-h-dvh w-full bg-slate-950'
		: 'w-full py-16'} relative flex flex-col items-center justify-center px-6 overflow-hidden select-none"
	role="status"
	aria-live="polite"
	aria-label={label}
>
	<!-- Subtle Ambient Aurora Backdrop -->
	{#if fullscreen}
		<div
			class="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] h-[340px] sm:w-[480px] sm:h-[480px] rounded-full bg-emerald-500/10 blur-3xl"
		></div>
		<div
			class="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/4 -translate-y-1/3 w-[240px] h-[240px] sm:w-[340px] sm:h-[340px] rounded-full bg-cyan-500/10 blur-3xl"
		></div>
	{/if}

	<div class="relative z-10 flex flex-col items-center text-center space-y-6 max-w-xs w-full">
		<!-- Dual-Ring Orbital Emblem -->
		<div class="relative h-24 w-24 sm:h-28 sm:w-28 flex items-center justify-center">
			<!-- Outer Orbital SVG Arc -->
			<svg
				viewBox="0 0 120 120"
				class="absolute inset-0 w-full h-full fin-orbit"
				aria-hidden="true"
			>
				<defs>
					<linearGradient id="fin-loader-grad-1" x1="0%" y1="0%" x2="100%" y2="100%">
						<stop offset="0%" stop-color="#34d399" />
						<stop offset="55%" stop-color="#22d3ee" />
						<stop offset="100%" stop-color="#34d399" stop-opacity="0" />
					</linearGradient>
				</defs>
				<circle
					cx="60"
					cy="60"
					r="54"
					fill="none"
					stroke="rgba(148, 163, 184, 0.1)"
					stroke-width="2"
				/>
				<circle
					cx="60"
					cy="60"
					r="54"
					fill="none"
					stroke="url(#fin-loader-grad-1)"
					stroke-width="3"
					stroke-linecap="round"
					stroke-dasharray="110 230"
				/>
			</svg>

			<!-- Inner Counter-Rotating Dashed Ring -->
			<svg
				viewBox="0 0 120 120"
				class="absolute inset-2.5 w-[calc(100%-1.25rem)] h-[calc(100%-1.25rem)] fin-orbit-reverse"
				aria-hidden="true"
			>
				<circle
					cx="60"
					cy="60"
					r="50"
					fill="none"
					stroke="rgba(34, 211, 238, 0.28)"
					stroke-width="1.8"
					stroke-dasharray="14 18"
					stroke-linecap="round"
				/>
			</svg>

			<!-- Center Glass Brand Tile -->
			<div
				class="h-14 w-14 sm:h-16 sm:w-16 rounded-2xl bg-gradient-to-br from-emerald-500/20 via-slate-900/90 to-cyan-500/20 border border-emerald-500/35 shadow-xl shadow-emerald-950/60 flex items-center justify-center text-emerald-400"
			>
				<Sparkles class="w-7 h-7 sm:w-8 sm:h-8" />
			</div>
		</div>

		<!-- Animated 5-Bar Financial Pulse Wave -->
		<div class="flex items-end justify-center gap-1.5 h-6" aria-hidden="true">
			{#each [0, 140, 280, 420, 560] as delay, idx}
				<span
					class="w-1.5 rounded-full fin-bar {idx % 2 === 0
						? 'bg-emerald-400'
						: 'bg-cyan-400'}"
					style="height: {idx === 2 ? '24px' : idx === 1 || idx === 3 ? '18px' : '13px'}; animation-delay: {delay}ms"
				></span>
			{/each}
		</div>

		<!-- Brand Title & Dynamic Status -->
		<div class="space-y-1.5">
			<div class="text-base sm:text-lg font-bold tracking-tight text-white">
				{label}
			</div>
			{#if subtitles.length > 0}
				<p class="text-xs text-slate-400 min-h-[1rem] transition-opacity duration-300">
					{subtitles[subtitleIdx]}
				</p>
			{/if}
		</div>

		<!-- Sleek Shimmer Progress Pill -->
		<div class="w-44 h-1 rounded-full bg-slate-800/90 fin-shimmer-track"></div>
	</div>
</div>
