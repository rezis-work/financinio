<script lang="ts">
	import type { MonthlyCashFlowPoint } from '$lib/api/types';
	import { formatMoney, formatShortMonth } from '$lib/utils/format';

	let {
		points,
		currency = 'USD',
		months = 6,
		privacyMode = false,
		onChangeMonths
	}: {
		points: MonthlyCashFlowPoint[];
		currency: string;
		months: number;
		privacyMode?: boolean;
		onChangeMonths?: (m: number) => void;
	} = $props();

	let hoveredIdx = $state<number | null>(null);

	const W = 680;
	const H = 250;
	const PAD_L = 56;
	const PAD_R = 18;
	const PAD_T = 22;
	const PAD_B = 34;
	const PLOT_W = W - PAD_L - PAD_R;
	const PLOT_H = H - PAD_T - PAD_B;

	let parsed = $derived(
		points.map((p) => {
			const inc = Number.parseFloat(p.income) || 0;
			const exp = Number.parseFloat(p.expenses) || 0;
			const net = Number.parseFloat(p.net) || inc - exp;
			const savingsRate = inc > 0 ? Math.round((net / inc) * 1000) / 10 : 0;
			return { month: p.month, label: formatShortMonth(p.month), inc, exp, net, savingsRate };
		})
	);

	let maxVal = $derived.by(() => {
		const rawMax = Math.max(
			...parsed.flatMap((p) => [p.inc, p.exp, Math.abs(p.net)]),
			100
		);
		// Round up to a clean axis ceiling
		const mag = Math.pow(10, Math.floor(Math.log10(rawMax)));
		return Math.ceil(rawMax / (mag / 2)) * (mag / 2);
	});

	let yTicks = $derived([0, 0.25, 0.5, 0.75, 1].map((t) => t * maxVal));

	function yPos(val: number): number {
		const clamped = Math.max(0, Math.min(val, maxVal));
		return PAD_T + PLOT_H - (clamped / maxVal) * PLOT_H;
	}

	function compactAxis(v: number): string {
		if (privacyMode) return '•••';
		if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
		if (v >= 1000) return `${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}k`;
		return `${Math.round(v)}`;
	}

	let netLinePath = $derived.by(() => {
		if (parsed.length === 0) return '';
		const step = PLOT_W / parsed.length;
		return parsed
			.map((p, i) => {
				const cx = PAD_L + i * step + step / 2;
				const cy = yPos(Math.max(0, p.net));
				return `${i === 0 ? 'M' : 'L'} ${cx.toFixed(1)} ${cy.toFixed(1)}`;
			})
			.join(' ');
	});

	let activePoint = $derived(hoveredIdx !== null ? parsed[hoveredIdx] ?? null : null);

	let totalInc = $derived(parsed.reduce((s, p) => s + p.inc, 0));
	let totalExp = $derived(parsed.reduce((s, p) => s + p.exp, 0));
	let totalNet = $derived(totalInc - totalExp);
</script>

<div class="card-surface rounded-2xl p-5 sm:p-6 space-y-4">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
		<div>
			<div class="flex items-center gap-2">
				<h2 class="text-base font-semibold text-white">Cash Flow & Net Trend</h2>
				<span class="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] font-mono-num text-slate-400">
					{months}M
				</span>
			</div>
			<p class="text-xs text-slate-400 mt-0.5">
				Period net:
				<span
					class="font-mono-num font-semibold {totalNet >= 0 ? 'text-emerald-400' : 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
				>
					{totalNet >= 0 ? '+' : ''}{formatMoney(totalNet, currency)}
				</span>
				· Hover any month for details
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-3">
			<div class="flex items-center gap-3 text-[11px] text-slate-400">
				<span class="flex items-center gap-1.5">
					<span class="w-2.5 h-2.5 rounded-xs bg-emerald-400"></span>Income
				</span>
				<span class="flex items-center gap-1.5">
					<span class="w-2.5 h-2.5 rounded-xs bg-rose-400/85"></span>Expenses
				</span>
				<span class="flex items-center gap-1.5">
					<span class="w-3 h-0.5 rounded-full bg-cyan-400"></span>Net
				</span>
			</div>

			{#if onChangeMonths}
				<div class="inline-flex p-0.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px]">
					{#each [3, 6, 12] as m}
						<button
							type="button"
							onclick={() => onChangeMonths(m)}
							class="px-2 py-1 rounded-md font-semibold transition cursor-pointer {months === m
								? 'bg-emerald-500/20 text-emerald-300'
								: 'text-slate-400 hover:text-white'}"
						>
							{m}M
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<div class="relative">
		{#if parsed.length === 0}
			<div class="h-56 flex items-center justify-center text-sm text-slate-500">
				No cash flow history yet.
			</div>
		{:else}
			{@const step = PLOT_W / parsed.length}
			{@const barW = Math.min(22, Math.max(8, step * 0.27))}

			<svg
				viewBox="0 0 {W} {H}"
				class="w-full h-56 sm:h-64 select-none overflow-visible"
				role="img"
				aria-label="Monthly cash flow bar and net trend chart"
				onmouseleave={() => (hoveredIdx = null)}
			>
				<defs>
					<linearGradient id="cf-inc-grad" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color="#34d399" stop-opacity="0.95" />
						<stop offset="100%" stop-color="#10b981" stop-opacity="0.45" />
					</linearGradient>
					<linearGradient id="cf-exp-grad" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color="#fb7185" stop-opacity="0.9" />
						<stop offset="100%" stop-color="#f43f5e" stop-opacity="0.4" />
					</linearGradient>
				</defs>

				<!-- Horizontal Gridlines & Y-axis labels -->
				{#each yTicks as tick}
					{@const y = yPos(tick)}
					<line
						x1={PAD_L}
						y1={y}
						x2={W - PAD_R}
						y2={y}
						stroke="rgba(148, 163, 184, 0.12)"
						stroke-dasharray={tick === 0 ? undefined : '3 4'}
					/>
					<text
						x={PAD_L - 8}
						y={y + 3.5}
						text-anchor="end"
						class="fill-slate-500 text-[10px] font-mono-num"
					>
						{compactAxis(tick)}
					</text>
				{/each}

				<!-- Month Columns -->
				{#each parsed as pt, i}
					{@const colX = PAD_L + i * step}
					{@const cx = colX + step / 2}
					{@const incH = Math.max(pt.inc > 0 ? (pt.inc / maxVal) * PLOT_H : 2, 2)}
					{@const expH = Math.max(pt.exp > 0 ? (pt.exp / maxVal) * PLOT_H : 2, 2)}
					{@const isActive = hoveredIdx === i}

					<!-- Interactive hover column backdrop -->
					<g
						role="button"
						tabindex="0"
						aria-label="{pt.label}: Income {formatMoney(pt.inc, currency)}, Expenses {formatMoney(pt.exp, currency)}"
						onmouseenter={() => (hoveredIdx = i)}
						onfocus={() => (hoveredIdx = i)}
						onclick={() => (hoveredIdx = hoveredIdx === i ? null : i)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') hoveredIdx = i;
						}}
						class="cursor-pointer outline-none"
					>
						<rect
							x={colX + 3}
							y={PAD_T}
							width={Math.max(step - 6, 8)}
							height={PLOT_H}
							rx="8"
							fill={isActive ? 'rgba(148, 163, 184, 0.08)' : 'transparent'}
						/>

						<!-- Income Bar -->
						<rect
							x={cx - barW - 2}
							y={PAD_T + PLOT_H - incH}
							width={barW}
							height={incH}
							rx="4"
							fill="url(#cf-inc-grad)"
							opacity={hoveredIdx === null || isActive ? 1 : 0.45}
							class="transition-opacity duration-150"
						/>

						<!-- Expense Bar -->
						<rect
							x={cx + 2}
							y={PAD_T + PLOT_H - expH}
							width={barW}
							height={expH}
							rx="4"
							fill="url(#cf-exp-grad)"
							opacity={hoveredIdx === null || isActive ? 1 : 0.45}
							class="transition-opacity duration-150"
						/>

						<!-- Month Label -->
						<text
							x={cx}
							y={H - 10}
							text-anchor="middle"
							class="text-[11px] font-medium transition-colors {isActive
								? 'fill-white'
								: 'fill-slate-400'}"
						>
							{pt.label}
						</text>
					</g>
				{/each}

				<!-- Net Cash Flow Trend Line -->
				{#if parsed.length > 1}
					<path
						d={netLinePath}
						fill="none"
						stroke="#22d3ee"
						stroke-width="2.2"
						stroke-linecap="round"
						stroke-linejoin="round"
						class="pointer-events-none"
					/>
				{/if}

				<!-- Net Data Points -->
				{#each parsed as pt, i}
					{@const cx = PAD_L + i * step + step / 2}
					{@const cy = yPos(Math.max(0, pt.net))}
					{@const isActive = hoveredIdx === i}
					<circle
						cx={cx}
						cy={cy}
						r={isActive ? 5 : 3.2}
						fill={pt.net >= 0 ? '#22d3ee' : '#fb7185'}
						stroke="#020617"
						stroke-width="1.8"
						class="pointer-events-none transition-all duration-150"
					/>
				{/each}
			</svg>

			<!-- Floating Interactive Tooltip -->
			{#if activePoint && hoveredIdx !== null}
				{@const leftPct = Math.min(76, Math.max(4, ((hoveredIdx + 0.5) / parsed.length) * 100 - 14))}
				<div
					class="pointer-events-none absolute top-1 z-10 w-48 rounded-xl bg-slate-950/95 border border-slate-700/90 px-3 py-2.5 shadow-2xl backdrop-blur-md text-xs space-y-1.5"
					style="left: {leftPct}%"
				>
					<div class="flex items-center justify-between border-b border-slate-800 pb-1">
						<span class="font-semibold text-white">{activePoint.month}</span>
						<span class="text-[10px] font-mono-num text-cyan-300">
							{activePoint.savingsRate}% saved
						</span>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-slate-400">Income</span>
						<span class="font-mono-num text-emerald-400 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(activePoint.inc, currency)}
						</span>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-slate-400">Expenses</span>
						<span class="font-mono-num text-rose-400 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(activePoint.exp, currency)}
						</span>
					</div>
					<div class="flex items-center justify-between pt-1 border-t border-slate-800/80 font-semibold">
						<span class="text-slate-300">Net</span>
						<span
							class="font-mono-num {activePoint.net >= 0 ? 'text-cyan-300' : 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{activePoint.net >= 0 ? '+' : ''}{formatMoney(activePoint.net, currency)}
						</span>
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>
