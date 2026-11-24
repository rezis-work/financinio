<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { QuantSignal, QuoteDetail, WatchlistItem } from '$lib/api/types';
	import {
		X,
		TrendingUp,
		TrendingDown,
		Sparkles,
		Bell,
		CheckCircle2,
		ShieldAlert,
		Activity
	} from 'lucide-svelte';

	interface Props {
		symbol: string | null;
		watchlist: WatchlistItem[];
		onClose: () => void;
		onOpenTrade: (qa: QuantSignal) => void;
		onWatchlistUpdated: () => void;
	}

	let { symbol, watchlist, onClose, onOpenTrade, onWatchlistUpdated }: Props = $props();

	let rangeStr = $state<'1mo' | '3mo' | '6mo' | '1y'>('6mo');
	let loading = $state(false);
	let detail = $state<QuoteDetail | null>(null);
	let err = $state<string | null>(null);

	let hoverIdx = $state<number | null>(null);
	let targetBuy = $state('');
	let targetSell = $state('');
	let savingAlert = $state(false);
	let alertSaved = $state(false);

	let existingWatch = $derived(
		symbol ? watchlist.find((w) => w.symbol === symbol) ?? null : null
	);

	async function loadDetail(sym: string, r: '1mo' | '3mo' | '6mo' | '1y') {
		loading = true;
		err = null;
		hoverIdx = null;
		try {
			detail = await api.marketsQuoteDetail(sym, r);
		} catch (e) {
			err = e instanceof ApiError ? e.message : 'Could not load quote';
			detail = null;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (!symbol) return;
		alertSaved = false;
		targetBuy = existingWatch?.target_buy_price ?? '';
		targetSell = existingWatch?.target_sell_price ?? '';
		loadDetail(symbol, rangeStr);
	});

	async function saveWatchAlert(e: SubmitEvent) {
		e.preventDefault();
		if (!detail) return;
		savingAlert = true;
		alertSaved = false;
		try {
			await api.addWatchlistItem({
				symbol: detail.analysis.symbol,
				display_name: detail.analysis.display_name,
				asset_type: detail.analysis.asset_type,
				target_buy_price: targetBuy ? targetBuy : null,
				target_sell_price: targetSell ? targetSell : null,
				alert_enabled: true
			});
			alertSaved = true;
			onWatchlistUpdated();
		} catch (e) {
			err = e instanceof ApiError ? e.message : 'Failed to save watchlist alert';
		} finally {
			savingAlert = false;
		}
	}

	// Interactive SVG Chart coordinates
	const W = 520;
	const H = 200;
	const PAD = 14;

	let chartGeom = $derived.by(() => {
		const pts = detail?.candles ?? [];
		if (pts.length < 2) return null;
		const vals: number[] = [];
		for (const c of pts) {
			vals.push(c.close);
			if (c.sma_20 !== null) vals.push(c.sma_20);
			if (c.sma_50 !== null) vals.push(c.sma_50);
		}
		const minV = Math.min(...vals);
		const maxV = Math.max(...vals);
		const span = Math.max(0.0001, maxV - minV);
		const xFor = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const yFor = (v: number) => H - PAD - ((v - minV) / span) * (H - PAD * 2);

		const pricePath = pts
			.map((c, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i).toFixed(1)} ${yFor(c.close).toFixed(1)}`)
			.join(' ');
		const areaPath = `${pricePath} L ${xFor(pts.length - 1).toFixed(1)} ${H - PAD} L ${xFor(0).toFixed(1)} ${H - PAD} Z`;

		const buildLine = (key: 'sma_20' | 'sma_50') => {
			let d = '';
			let started = false;
			for (let i = 0; i < pts.length; i++) {
				const v = pts[i][key];
				if (v === null) continue;
				d += `${started ? ' L ' : 'M '}${xFor(i).toFixed(1)} ${yFor(v).toFixed(1)}`;
				started = true;
			}
			return d;
		};

		const up = pts[pts.length - 1].close >= pts[0].close;
		return {
			pts,
			minV,
			maxV,
			xFor,
			yFor,
			pricePath,
			areaPath,
			sma20Path: buildLine('sma_20'),
			sma50Path: buildLine('sma_50'),
			up
		};
	});

	let activeCandle = $derived(
		chartGeom && hoverIdx !== null && chartGeom.pts[hoverIdx]
			? chartGeom.pts[hoverIdx]
			: chartGeom
				? chartGeom.pts[chartGeom.pts.length - 1]
				: null
	);

	function signalBadgeClass(sig: string): string {
		if (sig === 'STRONG_BUY') return 'bg-emerald-500/20 border-emerald-400/50 text-emerald-300';
		if (sig === 'BUY') return 'bg-cyan-500/15 border-cyan-400/40 text-cyan-300';
		if (sig === 'HOLD') return 'bg-slate-800 border-slate-700 text-slate-300';
		if (sig === 'WATCH_SELL') return 'bg-amber-500/15 border-amber-400/40 text-amber-300';
		return 'bg-rose-500/15 border-rose-500/40 text-rose-300';
	}

	let lunaPrompt = $derived(
		detail
			? encodeURIComponent(
					`Analyze ${detail.analysis.symbol} (${detail.analysis.display_name}) at ${detail.analysis.price} ${detail.analysis.currency}. Quant score is ${detail.analysis.quant_score}/100 (${detail.analysis.signal}). Should I buy or wait given my financial profile?`
				)
			: ''
	);
</script>

{#if symbol}
	<div
		class="fixed inset-0 z-50 bg-black/65 backdrop-blur-xs flex justify-end"
		role="dialog"
		aria-modal="true"
		aria-label="Symbol market analysis"
	>
		<button type="button" class="flex-1 cursor-default" aria-label="Close drawer" onclick={onClose}></button>

		<div class="w-full max-w-xl bg-slate-950 border-l border-slate-800/90 h-full overflow-y-auto flex flex-col shadow-2xl">
			<!-- Header -->
			<div class="sticky top-0 z-10 bg-slate-950/95 backdrop-blur-md px-5 py-4 border-b border-slate-800/80 flex items-center justify-between gap-3">
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<h3 class="text-base font-bold text-white">{symbol}</h3>
						{#if detail}
							<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase border {signalBadgeClass(detail.analysis.signal)}">
								{detail.analysis.signal.replace('_', ' ')}
							</span>
						{/if}
					</div>
					<p class="text-xs text-slate-400 truncate">
						{detail?.analysis.display_name || 'Loading live market data...'}
					</p>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-4 h-4" />
				</button>
			</div>

			<div class="p-5 space-y-5 flex-1">
				{#if loading}
					<div class="py-16 text-center space-y-2">
						<Activity class="w-7 h-7 text-emerald-400 mx-auto animate-pulse" />
						<p class="text-xs text-slate-400">Fetching live candles & computing quant signals...</p>
					</div>
				{:else if err}
					<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs">{err}</div>
				{:else if detail}
					{@const qa = detail.analysis}

					<!-- Live Price + Quick Actions -->
					<div class="flex flex-wrap items-end justify-between gap-4">
						<div>
							<div class="text-3xl font-bold font-mono-num text-white">
								{qa.price} <span class="text-sm font-normal text-slate-400">{qa.currency}</span>
							</div>
							<div class="inline-flex items-center gap-1.5 text-xs font-mono-num font-semibold mt-1 {qa.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
								{#if qa.change_pct >= 0}
									<TrendingUp class="w-3.5 h-3.5" /> +{qa.change} (+{qa.change_pct}%)
								{:else}
									<TrendingDown class="w-3.5 h-3.5" /> {qa.change} ({qa.change_pct}%)
								{/if}
								<span class="text-slate-500 font-sans font-normal">today</span>
							</div>
						</div>

						<div class="flex items-center gap-2">
							<button
								type="button"
								onclick={() => onOpenTrade(qa)}
								class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer transition"
							>
								Paper Trade
							</button>
							<a
								href="/advisor?q={lunaPrompt}"
								class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/35 text-violet-200 font-semibold text-xs transition"
							>
								<Sparkles class="w-3.5 h-3.5" /> Ask Luna
							</a>
						</div>
					</div>

					<!-- Interactive Price + Moving Average Chart -->
					<div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 space-y-3">
						<div class="flex items-center justify-between gap-2 flex-wrap">
							<div class="text-[11px] font-mono-num text-slate-300">
								{#if activeCandle}
									<span class="text-slate-400">{activeCandle.date}</span> ·
									<strong class="text-white">{activeCandle.close}</strong>
									{#if activeCandle.sma_20 !== null}
										<span class="text-cyan-400 ml-2">SMA20: {activeCandle.sma_20}</span>
									{/if}
									{#if activeCandle.sma_50 !== null}
										<span class="text-amber-300 ml-2">SMA50: {activeCandle.sma_50}</span>
									{/if}
								{/if}
							</div>
							<div class="inline-flex p-0.5 rounded-lg bg-slate-950 border border-slate-800 text-[10px]">
								{#each (['1mo', '3mo', '6mo', '1y'] as const) as r}
									<button
										type="button"
										onclick={() => {
											rangeStr = r;
											if (symbol) loadDetail(symbol, r);
										}}
										class="px-2 py-1 rounded-md font-semibold uppercase cursor-pointer transition {rangeStr === r
											? 'bg-emerald-500/20 text-emerald-300'
											: 'text-slate-400 hover:text-white'}"
									>
										{r}
									</button>
								{/each}
							</div>
						</div>

						{#if chartGeom}
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<svg
								viewBox="0 0 {W} {H}"
								class="w-full h-44 select-none overflow-visible"
								onmouseleave={() => (hoverIdx = null)}
								onmousemove={(e) => {
									const rect = e.currentTarget.getBoundingClientRect();
									const relX = ((e.clientX - rect.left) / rect.width) * W;
									const idx = Math.round(((relX - PAD) / (W - PAD * 2)) * (chartGeom!.pts.length - 1));
									hoverIdx = Math.max(0, Math.min(chartGeom!.pts.length - 1, idx));
								}}
							>
								<defs>
									<linearGradient id="mkt-grad" x1="0" y1="0" x2="0" y2="1">
										<stop offset="0%" stop-color={chartGeom.up ? '#10b981' : '#f43f5e'} stop-opacity="0.28" />
										<stop offset="100%" stop-color={chartGeom.up ? '#10b981' : '#f43f5e'} stop-opacity="0.0" />
									</linearGradient>
								</defs>
								<path d={chartGeom.areaPath} fill="url(#mkt-grad)" />
								{#if chartGeom.sma50Path}
									<path d={chartGeom.sma50Path} fill="none" stroke="#fbbf24" stroke-width="1.3" stroke-dasharray="4 3" opacity="0.8" />
								{/if}
								{#if chartGeom.sma20Path}
									<path d={chartGeom.sma20Path} fill="none" stroke="#22d3ee" stroke-width="1.3" opacity="0.85" />
								{/if}
								<path d={chartGeom.pricePath} fill="none" stroke={chartGeom.up ? '#34d399' : '#fb7185'} stroke-width="2.2" stroke-linecap="round" />
								{#if hoverIdx !== null && chartGeom.pts[hoverIdx]}
									{@const hx = chartGeom.xFor(hoverIdx)}
									{@const hy = chartGeom.yFor(chartGeom.pts[hoverIdx].close)}
									<line x1={hx} y1={PAD} x2={hx} y2={H - PAD} stroke="#475569" stroke-dasharray="3 3" stroke-width="1" />
									<circle cx={hx} cy={hy} r="4.5" fill={chartGeom.up ? '#34d399' : '#fb7185'} stroke="#020617" stroke-width="2" />
								{/if}
							</svg>
						{/if}
					</div>

					<!-- AI Trader Bot Quant Trade Plan -->
					<div class="p-4 rounded-2xl bg-gradient-to-br from-emerald-950/30 via-slate-900/70 to-cyan-950/25 border border-emerald-500/25 space-y-4">
						<div class="flex items-center justify-between gap-2">
							<div>
								<div class="text-[10px] uppercase tracking-wider text-emerald-300 font-semibold">
									AI Trader Bot Trade Plan
								</div>
								<div class="text-sm font-bold text-white mt-0.5">
									Quant Score: <span class="font-mono-num text-emerald-300">{qa.quant_score}/100</span> · {qa.trend_label}
								</div>
							</div>
							<span class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono-num text-cyan-300">
								R:R {qa.risk_reward_ratio}:1
							</span>
						</div>

						<div class="grid grid-cols-3 gap-2 text-xs">
							<div class="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/80">
								<div class="text-[10px] text-slate-400">Entry Zone</div>
								<div class="font-mono-num font-bold text-white mt-0.5">
									{qa.entry_zone_low}–{qa.entry_zone_high}
								</div>
							</div>
							<div class="p-2.5 rounded-xl bg-slate-950/80 border border-rose-500/25">
								<div class="text-[10px] text-rose-300">Stop-Loss</div>
								<div class="font-mono-num font-bold text-rose-300 mt-0.5">{qa.stop_loss}</div>
							</div>
							<div class="p-2.5 rounded-xl bg-slate-950/80 border border-emerald-500/25">
								<div class="text-[10px] text-emerald-300">Take-Profit</div>
								<div class="font-mono-num font-bold text-emerald-300 mt-0.5">{qa.take_profit}</div>
							</div>
						</div>

						<ul class="space-y-1.5 text-xs text-slate-300">
							{#each qa.reasons as r}
								<li class="flex items-start gap-2">
									<CheckCircle2 class="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
									<span>{r}</span>
								</li>
							{/each}
						</ul>

						{#if qa.cfo_guardrail_note}
							<div class="p-3 rounded-xl bg-slate-950/80 border border-amber-500/25 text-[11px] text-amber-200 flex items-start gap-2">
								<ShieldAlert class="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
								<span>{qa.cfo_guardrail_note}</span>
							</div>
						{/if}
					</div>

					<!-- Technical Indicators Grid -->
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
						<div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
							<div class="text-[10px] text-slate-400">RSI (14)</div>
							<div class="font-mono-num font-bold text-white mt-0.5">{qa.rsi_14 ?? '—'}</div>
						</div>
						<div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
							<div class="text-[10px] text-slate-400">MACD Hist</div>
							<div class="font-mono-num font-bold mt-0.5 {(qa.macd_hist ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
								{qa.macd_hist ?? '—'}
							</div>
						</div>
						<div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
							<div class="text-[10px] text-slate-400">1M Return</div>
							<div class="font-mono-num font-bold mt-0.5 {(qa.return_1m_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
								{qa.return_1m_pct !== null ? `${qa.return_1m_pct > 0 ? '+' : ''}${qa.return_1m_pct}%` : '—'}
							</div>
						</div>
						<div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
							<div class="text-[10px] text-slate-400">Daily Vol (ATR)</div>
							<div class="font-mono-num font-bold text-slate-200 mt-0.5">
								{qa.volatility_pct !== null ? `${qa.volatility_pct}%` : '—'}
							</div>
						</div>
					</div>

					<!-- Watchlist & Price Target Alerts -->
					<form onsubmit={saveWatchAlert} class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3">
						<div class="flex items-center justify-between">
							<div class="inline-flex items-center gap-1.5 text-xs font-semibold text-white">
								<Bell class="w-3.5 h-3.5 text-amber-400" />
								Watchlist & Price Alerts
							</div>
							{#if alertSaved}
								<span class="text-[11px] text-emerald-400 font-semibold">Saved to Watchlist!</span>
							{/if}
						</div>
						<div class="grid grid-cols-2 gap-3">
							<div>
								<label for="wl-buy" class="block text-[10px] text-slate-400 mb-1">Alert if drops to (Buy Target)</label>
								<input
									id="wl-buy"
									type="number"
									step="0.0001"
									bind:value={targetBuy}
									placeholder={String(qa.entry_zone_low)}
									class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono-num text-white focus:outline-none focus:border-emerald-500"
								/>
							</div>
							<div>
								<label for="wl-sell" class="block text-[10px] text-slate-400 mb-1">Alert if rises to (Sell Target)</label>
								<input
									id="wl-sell"
									type="number"
									step="0.0001"
									bind:value={targetSell}
									placeholder={String(qa.take_profit)}
									class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono-num text-white focus:outline-none focus:border-cyan-500"
								/>
							</div>
						</div>
						<button
							type="submit"
							disabled={savingAlert}
							class="w-full py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold cursor-pointer transition disabled:opacity-50"
						>
							{savingAlert
								? 'Saving Alert...'
								: existingWatch
									? 'Update Watchlist & Price Alerts'
									: 'Add to Watchlist & Set Alerts'}
						</button>
					</form>
				{/if}
			</div>
		</div>
	</div>
{/if}
