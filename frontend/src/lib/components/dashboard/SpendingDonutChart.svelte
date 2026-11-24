<script lang="ts">
	import type { CategorySpendItem } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { Sparkles } from 'lucide-svelte';

	let {
		items,
		currency = 'USD',
		privacyMode = false,
		onAskCategory
	}: {
		items: CategorySpendItem[];
		currency: string;
		privacyMode?: boolean;
		onAskCategory?: (categoryName: string) => void;
	} = $props();

	let activeIndex = $state<number | null>(null);

	const R = 64;
	const CIRC = 2 * Math.PI * R;

	let total = $derived(items.reduce((s, item) => s + (Number.parseFloat(item.total) || 0), 0));

	let segments = $derived.by(() => {
		let offset = 0;
		return items.slice(0, 7).map((item, idx) => {
			const val = Number.parseFloat(item.total) || 0;
			const frac = total > 0 ? val / total : 0;
			const dash = Math.max(frac * CIRC - 2.5, 1.5);
			const seg = {
				idx,
				item,
				val,
				dash,
				gap: CIRC - dash,
				offset: -offset
			};
			offset += frac * CIRC;
			return seg;
		});
	});

	let activeItem = $derived(activeIndex !== null ? segments[activeIndex] ?? null : null);
</script>

<div class="card-surface rounded-2xl p-5 sm:p-6 flex flex-col justify-between gap-4">
	<div class="flex items-center justify-between gap-2">
		<div>
			<h2 class="text-base font-semibold text-white">Spending Mix</h2>
			<p class="text-xs text-slate-400">Hover or tap a category slice</p>
		</div>
		{#if activeItem && onAskCategory}
			<button
				type="button"
				onclick={() => onAskCategory(activeItem.item.category_name)}
				class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-[11px] font-semibold cursor-pointer transition"
			>
				<Sparkles class="w-3 h-3" /> Ask Luna
			</button>
		{/if}
	</div>

	{#if items.length === 0 || total <= 0}
		<div class="py-14 text-center text-sm text-slate-500">
			No expenses recorded yet. Import a statement or add a transaction.
		</div>
	{:else}
		<!-- SVG Donut Ring -->
		<div class="flex items-center justify-center py-1">
			<div class="relative w-44 h-44">
				<svg viewBox="0 0 160 160" class="w-full h-full -rotate-90" role="img" aria-label="Spending breakdown donut chart">
					<circle
						cx="80"
						cy="80"
						r={R}
						fill="none"
						stroke="rgba(148, 163, 184, 0.1)"
						stroke-width="18"
					/>
					{#each segments as seg}
						{@const isSelected = activeIndex === seg.idx}
						<circle
							cx="80"
							cy="80"
							r={R}
							fill="none"
							stroke={seg.item.color}
							stroke-width={isSelected ? 22 : 18}
							stroke-dasharray="{seg.dash} {seg.gap}"
							stroke-dashoffset={seg.offset}
							stroke-linecap="butt"
							opacity={activeIndex === null || isSelected ? 1 : 0.38}
							role="button"
							tabindex="0"
							aria-label="{seg.item.category_name}: {formatMoney(seg.val, currency)}"
							onmouseenter={() => (activeIndex = seg.idx)}
							onmouseleave={() => (activeIndex = null)}
							onclick={() => (activeIndex = activeIndex === seg.idx ? null : seg.idx)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') activeIndex = seg.idx;
							}}
							class="cursor-pointer transition-all duration-150 outline-none"
						/>
					{/each}
				</svg>

				<!-- Center Readout -->
				<div class="absolute inset-0 flex flex-col items-center justify-center text-center px-5 pointer-events-none">
					{#if activeItem}
						<span class="text-[10px] font-medium text-slate-400 truncate max-w-full">
							{activeItem.item.category_name}
						</span>
						<span class="text-sm font-bold text-white font-mono-num mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(activeItem.val, currency)}
						</span>
						<span class="text-[11px] font-mono-num text-emerald-400">
							{activeItem.item.percentage}%
						</span>
					{:else}
						<span class="text-[10px] uppercase tracking-wider text-slate-400">Total Spend</span>
						<span class="text-sm font-bold text-white font-mono-num mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(total, currency)}
						</span>
						<span class="text-[10px] text-slate-500">{items.length} categories</span>
					{/if}
				</div>
			</div>
		</div>

		<!-- Interactive Legend -->
		<div class="space-y-1.5 max-h-44 overflow-y-auto pr-1">
			{#each segments as seg}
				{@const isSelected = activeIndex === seg.idx}
				<button
					type="button"
					onmouseenter={() => (activeIndex = seg.idx)}
					onmouseleave={() => (activeIndex = null)}
					onclick={() => onAskCategory?.(seg.item.category_name)}
					class="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl text-xs transition cursor-pointer {isSelected
						? 'bg-slate-800/90 text-white'
						: 'hover:bg-slate-900/70 text-slate-300'}"
				>
					<span class="flex items-center gap-2 min-w-0">
						<span class="w-2.5 h-2.5 rounded-full shrink-0" style="background-color: {seg.item.color}"></span>
						<span class="truncate font-medium">{seg.item.category_name}</span>
					</span>
					<span class="font-mono-num text-[11px] shrink-0">
						<span class={privacyMode ? 'privacy-blur' : ''}>{formatMoney(seg.val, currency)}</span>
						<span class="text-slate-500 ml-1">{seg.item.percentage}%</span>
					</span>
				</button>
			{/each}
		</div>
	{/if}
</div>
