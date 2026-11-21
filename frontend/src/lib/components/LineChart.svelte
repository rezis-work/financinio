<script lang="ts">
	import { formatMoney } from '$lib/utils/format';

	export interface ChartSeries {
		name: string;
		color: string;
		dashed?: boolean;
		values: number[];
	}

	let {
		labels,
		series,
		currency = 'USD',
		height = 200
	}: {
		labels: string[];
		series: ChartSeries[];
		currency?: string;
		height?: number;
	} = $props();

	let hoverIdx = $state<number | null>(null);
	const chartId = `lc-${Math.random().toString(36).slice(2, 8)}`;

	const padLeft = 12;
	const padRight = 12;
	const padTop = 16;
	const padBottom = 26;
	const viewW = 600;
	let viewH = $derived(height);

	let allValues = $derived(series.flatMap((s) => s.values));
	let minVal = $derived.by(() => {
		if (allValues.length === 0) return 0;
		const m = Math.min(...allValues);
		return m > 0 ? Math.min(0, m * 0.9) : m * 1.05;
	});
	let maxVal = $derived.by(() => {
		if (allValues.length === 0) return 100;
		const m = Math.max(...allValues);
		return m === minVal ? m + 100 : m * 1.08;
	});

	function xFor(index: number): number {
		const n = labels.length;
		if (n <= 1) return (viewW - padLeft - padRight) / 2 + padLeft;
		return padLeft + (index / (n - 1)) * (viewW - padLeft - padRight);
	}

	function yFor(val: number): number {
		const span = maxVal - minVal || 1;
		const usableH = viewH - padTop - padBottom;
		return padTop + usableH - ((val - minVal) / span) * usableH;
	}

	function linePath(vals: number[]): string {
		if (vals.length === 0) return '';
		return vals
			.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i).toFixed(1)} ${yFor(v).toFixed(1)}`)
			.join(' ');
	}

	function areaPath(vals: number[]): string {
		if (vals.length < 2) return '';
		const line = linePath(vals);
		const baseY = (viewH - padBottom).toFixed(1);
		return `${line} L ${xFor(vals.length - 1).toFixed(1)} ${baseY} L ${xFor(0).toFixed(1)} ${baseY} Z`;
	}

	let gridTicks = $derived.by(() => {
		const span = maxVal - minVal || 1;
		return [0, 0.5, 1].map((t) => ({
			val: minVal + span * t,
			y: yFor(minVal + span * t)
		}));
	});

	let activeIndex = $derived(
		hoverIdx !== null ? hoverIdx : Math.max(0, labels.length - 1)
	);
</script>

<div class="space-y-3">
	<!-- Legend & Active Hover Readout -->
	<div class="flex flex-wrap items-center justify-between gap-2 text-xs">
		<div class="flex flex-wrap items-center gap-3.5">
			{#each series as s}
				<span class="inline-flex items-center gap-1.5 text-slate-300">
					<span
						class="w-3 h-0.5 rounded-full inline-block"
						style="background-color: {s.color}; {s.dashed ? 'border-top: 2px dashed ' + s.color + '; background: transparent;' : ''}"
					></span>
					<span>{s.name}:</span>
					<strong class="font-mono-num text-white">
						{formatMoney(s.values[activeIndex] ?? 0, currency)}
					</strong>
				</span>
			{/each}
		</div>
		{#if labels[activeIndex]}
			<span class="text-[11px] font-mono-num text-slate-400">
				{labels[activeIndex]}
			</span>
		{/if}
	</div>

	<!-- Responsive SVG Canvas -->
	<div class="relative w-full">
		<svg
			viewBox="0 0 {viewW} {viewH}"
			class="w-full h-auto overflow-visible select-none"
			role="img"
			aria-label="Financial trend line chart"
			onmouseleave={() => (hoverIdx = null)}
		>
			<defs>
				{#if series[0]}
					<linearGradient id="{chartId}-grad" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color={series[0].color} stop-opacity="0.28" />
						<stop offset="100%" stop-color={series[0].color} stop-opacity="0.01" />
					</linearGradient>
				{/if}
			</defs>

			<!-- Horizontal grid lines -->
			{#each gridTicks as tick}
				<line
					x1={padLeft}
					x2={viewW - padRight}
					y1={tick.y}
					y2={tick.y}
					stroke="rgba(148, 163, 184, 0.14)"
					stroke-dasharray="3 4"
				/>
			{/each}

			<!-- Zero baseline if negative values exist -->
			{#if minVal < 0 && maxVal > 0}
				<line
					x1={padLeft}
					x2={viewW - padRight}
					y1={yFor(0)}
					y2={yFor(0)}
					stroke="rgba(148, 163, 184, 0.3)"
					stroke-width="1"
				/>
			{/if}

			<!-- Area fill for primary series -->
			{#if series[0] && series[0].values.length >= 2}
				<path d={areaPath(series[0].values)} fill="url(#{chartId}-grad)" />
			{/if}

			<!-- Series lines -->
			{#each series as s}
				{#if s.values.length >= 2}
					<path
						d={linePath(s.values)}
						fill="none"
						stroke={s.color}
						stroke-width="2.5"
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-dasharray={s.dashed ? '6 4' : undefined}
					/>
				{/if}
			{/each}

			<!-- Vertical hover crosshair -->
			{#if labels.length > 0}
				<line
					x1={xFor(activeIndex)}
					x2={xFor(activeIndex)}
					y1={padTop}
					y2={viewH - padBottom}
					stroke="rgba(148, 163, 184, 0.35)"
					stroke-dasharray="2 3"
				/>
				{#each series as s}
					{#if s.values[activeIndex] !== undefined}
						<circle
							cx={xFor(activeIndex)}
							cy={yFor(s.values[activeIndex])}
							r="4.5"
							fill={s.color}
							stroke="#020617"
							stroke-width="2"
						/>
					{/if}
				{/each}
			{/if}

			<!-- X-axis start / mid / end labels -->
			{#if labels.length >= 1}
				<text x={padLeft} y={viewH - 6} fill="#94a3b8" font-size="10" text-anchor="start">
					{labels[0]}
				</text>
			{/if}
			{#if labels.length >= 3}
				{@const mid = Math.floor(labels.length / 2)}
				<text x={xFor(mid)} y={viewH - 6} fill="#94a3b8" font-size="10" text-anchor="middle">
					{labels[mid]}
				</text>
			{/if}
			{#if labels.length >= 2}
				<text x={viewW - padRight} y={viewH - 6} fill="#94a3b8" font-size="10" text-anchor="end">
					{labels[labels.length - 1]}
				</text>
			{/if}

			<!-- Invisible hit targets for smooth hover -->
			{#each labels as _, i}
				{@const segW = labels.length > 1 ? (viewW - padLeft - padRight) / (labels.length - 1) : viewW}
				<rect
					x={Math.max(0, xFor(i) - segW / 2)}
					y={padTop}
					width={segW}
					height={viewH - padTop - padBottom}
					fill="transparent"
					role="presentation"
					onmouseenter={() => (hoverIdx = i)}
				/>
			{/each}
		</svg>
	</div>
</div>
