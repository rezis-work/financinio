<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type {
		MarketRiskProfile,
		MarketsOverview,
		PaperPortfolio,
		PaperPosition,
		QuantSignal,
		SymbolSearchHit,
		WatchlistItem
	} from '$lib/api/types';
	import { formatDate } from '$lib/utils/format';
	import FinancinioLoader from '$lib/components/FinancinioLoader.svelte';
	import SymbolDetailDrawer from '$lib/components/markets/SymbolDetailDrawer.svelte';
	import PaperTradeModal from '$lib/components/markets/PaperTradeModal.svelte';
	import {
		TrendingUp,
		TrendingDown,
		Search,
		RefreshCw,
		Sparkles,
		Bell,
		Eye,
		EyeOff,
		Star,
		Trash2,
		Wallet,
		Bot,
		BarChart3,
		RotateCcw,
		AlertTriangle,
		CheckCircle2,
		X,
		ShieldCheck,
		Landmark
	} from 'lucide-svelte';

	type DeskTab = 'scanner' | 'paper' | 'watchlist';
	type ScannerCat = 'all' | 'buy_only' | 'stock' | 'etf' | 'forex' | 'crypto' | 'commodity';

	let loading = $state(true);
	let refreshing = $state(false);
	let activeTab = $state<DeskTab>('scanner');
	let scannerCat = $state<ScannerCat>('all');

	let overview = $state<MarketsOverview | null>(null);
	let scannerItems = $state<QuantSignal[]>([]);
	let watchlist = $state<WatchlistItem[]>([]);
	let portfolio = $state<PaperPortfolio | null>(null);
	let riskProfile = $state<MarketRiskProfile>('balanced');

	// Live symbol search
	let searchQuery = $state('');
	let searchHits = $state<SymbolSearchHit[]>([]);
	let searching = $state(false);
	let searchOpen = $state(false);
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	// Drawers & Modals
	let inspectingSymbol = $state<string | null>(null);
	let tradeModalState = $state<{
		symbol: string;
		displayName: string;
		livePrice: number;
		currency: string;
		signal: QuantSignal | null;
		initialSide: 'buy' | 'sell';
	} | null>(null);
	let confirmResetOpen = $state(false);
	let resetting = $state(false);

	// Privacy & Feedback
	let privacyMode = $state(false);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('financinio_privacy_mode', privacyMode ? '1' : '0');
		}
	}

	async function loadAll(forceRefresh = false) {
		if (!forceRefresh) loading = true;
		else refreshing = true;
		error = null;
		try {
			const [ov, sc, wl, pf] = await Promise.all([
				api.marketsOverview(forceRefresh),
				api.marketsScanner('all', forceRefresh ? riskProfile : undefined),
				api.listWatchlist(),
				api.getPaperPortfolio()
			]);
			overview = ov;
			scannerItems = sc.items;
			watchlist = wl;
			portfolio = pf;
			riskProfile = pf.risk_profile;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load live market data';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	onMount(() => {
		if (typeof localStorage !== 'undefined') {
			privacyMode = localStorage.getItem('financinio_privacy_mode') === '1';
		}
		loadAll(false);
		return () => clearTimeout(searchTimer);
	});

	async function changeRiskProfile(next: MarketRiskProfile) {
		riskProfile = next;
		refreshing = true;
		try {
			const [pf, sc] = await Promise.all([
				api.updatePaperSettings(next),
				api.marketsScanner('all', next)
			]);
			portfolio = pf;
			scannerItems = sc.items;
			notice = `Updated AI Trader Bot risk profile to ${next}.`;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to update risk profile';
		} finally {
			refreshing = false;
		}
	}

	function handleSearchInput() {
		clearTimeout(searchTimer);
		const q = searchQuery.trim();
		if (!q) {
			searchHits = [];
			searchOpen = false;
			return;
		}
		searchOpen = true;
		searching = true;
		searchTimer = setTimeout(async () => {
			try {
				searchHits = await api.marketsSearch(q);
			} catch {
				searchHits = [];
			} finally {
				searching = false;
			}
		}, 220);
	}

	function selectSearchHit(hit: SymbolSearchHit) {
		searchOpen = false;
		searchQuery = '';
		inspectingSymbol = hit.symbol;
	}

	async function quickAddWatch(qa: QuantSignal) {
		error = null;
		try {
			await api.addWatchlistItem({
				symbol: qa.symbol,
				display_name: qa.display_name,
				asset_type: qa.asset_type,
				target_buy_price: String(qa.entry_zone_low),
				target_sell_price: String(qa.take_profit),
				alert_enabled: true
			});
			watchlist = await api.listWatchlist();
			notice = `Added ${qa.symbol} to Watchlist with Buy (${qa.entry_zone_low}) & Sell (${qa.take_profit}) alerts.`;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to add to watchlist';
		}
	}

	async function removeWatch(item: WatchlistItem) {
		try {
			await api.deleteWatchlistItem(item.id);
			watchlist = watchlist.filter((w) => w.id !== item.id);
			notice = `Removed ${item.symbol} from Watchlist.`;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to remove watchlist item';
		}
	}

	function openTradeForSignal(qa: QuantSignal, side: 'buy' | 'sell' = 'buy') {
		tradeModalState = {
			symbol: qa.symbol,
			displayName: qa.display_name,
			livePrice: qa.price,
			currency: qa.currency,
			signal: qa,
			initialSide: side
		};
	}

	function openTradeForPosition(pos: PaperPosition, side: 'buy' | 'sell') {
		const matchSignal = scannerItems.find((s) => s.symbol === pos.symbol) ?? null;
		tradeModalState = {
			symbol: pos.symbol,
			displayName: pos.display_name,
			livePrice: pos.live_price,
			currency: 'USD',
			signal: matchSignal,
			initialSide: side
		};
	}

	async function handleConfirmReset() {
		resetting = true;
		try {
			portfolio = await api.resetPaperPortfolio();
			confirmResetOpen = false;
			notice = 'Paper Portfolio reset cleanly to $10,000.00 virtual cash.';
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to reset paper portfolio';
		} finally {
			resetting = false;
		}
	}

	function signalBadge(sig: string): string {
		if (sig === 'STRONG_BUY') return 'bg-emerald-500/20 border-emerald-400/50 text-emerald-300';
		if (sig === 'BUY') return 'bg-cyan-500/15 border-cyan-400/40 text-cyan-300';
		if (sig === 'HOLD') return 'bg-slate-800 border-slate-700 text-slate-300';
		if (sig === 'WATCH_SELL') return 'bg-amber-500/15 border-amber-400/40 text-amber-300';
		return 'bg-rose-500/15 border-rose-500/40 text-rose-300';
	}

	function scoreBarColor(score: number): string {
		if (score >= 72) return 'bg-emerald-400';
		if (score >= 58) return 'bg-cyan-400';
		if (score >= 42) return 'bg-slate-400';
		return 'bg-rose-400';
	}

	let watchedSymbols = $derived(new Set(watchlist.map((w) => w.symbol)));
	let triggeredAlerts = $derived(watchlist.filter((w) => w.alert_triggered !== 'none'));
	let buySignalsCount = $derived(
		scannerItems.filter((i) => i.signal === 'STRONG_BUY' || i.signal === 'BUY').length
	);

	let filteredScanner = $derived.by(() => {
		if (scannerCat === 'all') return scannerItems;
		if (scannerCat === 'buy_only') {
			return scannerItems.filter((i) => i.signal === 'STRONG_BUY' || i.signal === 'BUY');
		}
		return scannerItems.filter((i) => i.asset_type === scannerCat);
	});

	let lunaMarketPrompt = $derived(
		encodeURIComponent(
			`Act as my AI Trader Bot & Personal CFO. Based on today's live stocks, ETFs, and USD/GEL forex rates under my ${riskProfile} risk profile, what are the top 3 opportunities to watch or buy right now? Include entry zones, stop-loss, targets, and safe position sizes.`
		)
	);
</script>

{#if loading}
	<FinancinioLoader
		fullscreen={false}
		label="Loading Markets & AI Trader Bot"
		subtitles={[
			'Fetching live stocks, ETFs & official NBG GEL forex rates...',
			'Running deterministic RSI, MACD, SMA & ATR quant signals...',
			'Syncing your virtual $10,000 Paper Portfolio & alerts...'
		]}
	/>
{:else}
	<div class="space-y-6 pb-12">
		<!-- Executive Header -->
		<div class="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2.5 flex-wrap">
					<h1 class="text-2xl font-bold tracking-tight text-white">Markets, Forex & AI Trader Bot</h1>
					<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 border border-emerald-500/35 text-emerald-300">
						<span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
						{buySignalsCount} Buy Signals Live
					</span>
				</div>
				<p class="text-sm text-slate-400 mt-0.5">
					Live Yahoo Finance & official NBG GEL rates · Python Quant Engine (`RSI`, `MACD`, `SMA`, `ATR`) · Virtual $10k Paper Desk.
				</p>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<!-- Risk Profile Switcher -->
				<div class="inline-flex p-1 rounded-xl bg-slate-900 border border-slate-800 text-[11px]">
					{#each (['conservative', 'balanced', 'aggressive'] as const) as rp}
						<button
							type="button"
							onclick={() => changeRiskProfile(rp)}
							class="px-2.5 py-1 rounded-lg font-semibold capitalize transition cursor-pointer {riskProfile === rp
								? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
								: 'text-slate-400 hover:text-white border border-transparent'}"
						>
							{rp}
						</button>
					{/each}
				</div>

				<button
					type="button"
					onclick={togglePrivacy}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs font-medium text-slate-300 hover:text-white cursor-pointer"
				>
					{#if privacyMode}
						<EyeOff class="w-3.5 h-3.5 text-amber-400" />
					{:else}
						<Eye class="w-3.5 h-3.5 text-slate-400" />
					{/if}
				</button>

				<button
					type="button"
					disabled={refreshing}
					onclick={() => loadAll(true)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 cursor-pointer disabled:opacity-50"
				>
					<RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin text-emerald-400' : 'text-slate-400'}" />
					Refresh
				</button>

				<a
					href="/advisor?q={lunaMarketPrompt}"
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/35 text-violet-200 text-xs font-semibold transition"
				>
					<Sparkles class="w-3.5 h-3.5" /> Ask Luna Picks
				</a>
			</div>
		</div>

		<!-- Global Live Symbol Search -->
		<div class="relative max-w-xl">
			<Search class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
			<input
				type="text"
				bind:value={searchQuery}
				oninput={handleSearchInput}
				placeholder="Search any stock, ETF, Forex pair, or crypto (e.g., NVDA, AAPL, EUR/USD, BTC, TSLA)..."
				class="w-full pl-10 pr-10 py-2.5 rounded-2xl bg-slate-900/90 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 transition"
			/>
			{#if searchQuery}
				<button
					type="button"
					onclick={() => {
						searchQuery = '';
						searchOpen = false;
					}}
					class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-4 h-4" />
				</button>
			{/if}

			{#if searchOpen}
				<div class="absolute z-30 mt-1.5 w-full rounded-2xl bg-slate-950 border border-slate-800 shadow-2xl overflow-hidden">
					{#if searching}
						<div class="p-4 text-xs text-slate-400 text-center">Searching global markets...</div>
					{:else if searchHits.length === 0}
						<div class="p-4 text-xs text-slate-400 text-center">No matching symbols found.</div>
					{:else}
						<div class="divide-y divide-slate-800/70">
							{#each searchHits as hit}
								<button
									type="button"
									onclick={() => selectSearchHit(hit)}
									class="w-full px-4 py-2.5 text-left hover:bg-slate-900 flex items-center justify-between gap-3 cursor-pointer"
								>
									<div class="min-w-0">
										<div class="text-xs font-bold text-white flex items-center gap-2">
											<span>{hit.symbol}</span>
											<span class="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-medium uppercase text-cyan-300">
												{hit.asset_type}
											</span>
										</div>
										<div class="text-[11px] text-slate-400 truncate">{hit.display_name}</div>
									</div>
									<span class="text-[10px] text-slate-500 shrink-0">{hit.exchange}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Feedback Alerts -->
		{#if error}
			<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
					<span>{error}</span>
				</div>
				<button type="button" onclick={() => (error = null)} class="text-rose-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}
		{#if notice}
			<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm flex items-start justify-between gap-3">
				<div class="flex items-start gap-2.5">
					<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
					<span>{notice}</span>
				</div>
				<button type="button" onclick={() => (notice = null)} class="text-emerald-300 hover:text-white cursor-pointer">
					<X class="w-4 h-4" />
				</button>
			</div>
		{/if}

		<!-- Triggered Watchlist Price Alerts Banner -->
		{#if triggeredAlerts.length > 0}
			<div class="p-4 rounded-2xl bg-gradient-to-r from-amber-500/15 via-emerald-500/10 to-slate-950 border border-amber-500/40 space-y-2">
				<div class="flex items-center gap-2 text-xs font-bold text-amber-200">
					<Bell class="w-4 h-4 text-amber-400 animate-bounce" />
					Price Target Alerts Triggered ({triggeredAlerts.length})
				</div>
				<div class="flex flex-wrap gap-2">
					{#each triggeredAlerts as al}
						<button
							type="button"
							onclick={() => (inspectingSymbol = al.symbol)}
							class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950/90 border border-amber-500/35 text-xs hover:border-emerald-400 cursor-pointer transition"
						>
							<strong class="text-white">{al.symbol}</strong>
							<span class="font-mono-num text-slate-300">{al.live_price} {al.currency}</span>
							<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase {al.alert_triggered === 'buy_target_hit' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-cyan-500/20 text-cyan-300'}">
								{al.alert_triggered === 'buy_target_hit' ? 'Buy Target Hit' : 'Sell Target Hit'}
							</span>
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Official NBG GEL Forex Strip -->
		{#if overview && overview.nbg_forex_rates.length > 0}
			<div class="card-surface rounded-2xl p-4 space-y-3">
				<div class="flex items-center justify-between gap-2">
					<div class="inline-flex items-center gap-2 text-xs font-semibold text-white">
						<Landmark class="w-4 h-4 text-orange-400" />
						Official National Bank of Georgia (NBG) GEL Exchange Rates
					</div>
					<span class="text-[11px] font-mono-num text-slate-500">
						Valid {overview.nbg_forex_rates[0].valid_from}
					</span>
				</div>
				<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
					{#each overview.nbg_forex_rates.slice(0, 6) as fx}
						<div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
							<div class="flex items-center justify-between text-[11px]">
								<span class="font-bold text-white">{fx.quantity > 1 ? `${fx.quantity} ` : ''}{fx.code}/GEL</span>
								<span class="font-mono-num text-[10px] {fx.diff >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
									{fx.diff >= 0 ? '+' : ''}{fx.diff.toFixed(4)}
								</span>
							</div>
							<div class="text-base font-bold font-mono-num text-orange-200 mt-1">
								₾ {fx.rate.toFixed(4)}
							</div>
							<div class="text-[10px] text-slate-500 truncate">{fx.name}</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Live Global Ticker Strip -->
		{#if overview && overview.ticker_quotes.length > 0}
			<div class="flex items-center gap-2.5 overflow-x-auto pb-1">
				{#each overview.ticker_quotes as tq}
					<button
						type="button"
						onclick={() => (inspectingSymbol = tq.symbol)}
						class="shrink-0 min-w-[155px] text-left p-3 rounded-xl bg-slate-900/75 hover:bg-slate-900 border border-slate-800 hover:border-emerald-500/40 transition cursor-pointer"
					>
						<div class="flex items-center justify-between gap-2">
							<span class="text-xs font-bold text-white">{tq.symbol}</span>
							<span class="text-[10px] font-mono-num font-semibold {tq.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
								{tq.change_pct >= 0 ? '+' : ''}{tq.change_pct}%
							</span>
						</div>
						<div class="text-sm font-bold font-mono-num text-slate-100 mt-1">
							{tq.price} <span class="text-[10px] font-normal text-slate-500">{tq.currency}</span>
						</div>
						<div class="text-[10px] text-slate-400 truncate mt-0.5">{tq.display_name}</div>
					</button>
				{/each}
			</div>
		{/if}

		<!-- Main Workspace Tab Bar -->
		<div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
			<div class="inline-flex p-1 rounded-xl bg-slate-900 border border-slate-800">
				<button
					type="button"
					onclick={() => (activeTab = 'scanner')}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition cursor-pointer {activeTab === 'scanner'
						? 'bg-emerald-500 text-slate-950'
						: 'text-slate-400 hover:text-white'}"
				>
					<Bot class="w-3.5 h-3.5" />
					AI Trader Bot ({scannerItems.length})
				</button>
				<button
					type="button"
					onclick={() => (activeTab = 'paper')}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition cursor-pointer {activeTab === 'paper'
						? 'bg-emerald-500 text-slate-950'
						: 'text-slate-400 hover:text-white'}"
				>
					<Wallet class="w-3.5 h-3.5" />
					Paper Portfolio
					{#if portfolio}
						<span class="font-mono-num text-[10px] px-1.5 py-0.2 rounded {activeTab === 'paper' ? 'bg-slate-950/20 text-slate-950' : 'bg-slate-800 text-emerald-300'} {privacyMode ? 'privacy-blur' : ''}">
							${Number.parseFloat(portfolio.total_equity).toLocaleString(undefined, { maximumFractionDigits: 0 })}
						</span>
					{/if}
				</button>
				<button
					type="button"
					onclick={() => (activeTab = 'watchlist')}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition cursor-pointer {activeTab === 'watchlist'
						? 'bg-emerald-500 text-slate-950'
						: 'text-slate-400 hover:text-white'}"
				>
					<Bell class="w-3.5 h-3.5" />
					Watchlist & Alerts ({watchlist.length})
				</button>
			</div>

			{#if overview && overview.cfo_runway_months < 3}
				<span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-200">
					<ShieldCheck class="w-3.5 h-3.5 text-amber-400" />
					CFO Gate: Runway {overview.cfo_runway_months.toFixed(1)} mo — practice in Paper Portfolio first!
				</span>
			{/if}
		</div>

		<!-- ==================== TAB 1: AI TRADER BOT SCANNER ==================== -->
		{#if activeTab === 'scanner'}
			<div class="space-y-4">
				<!-- Category Filter Strip -->
				<div class="flex flex-wrap items-center gap-1.5">
					{#each [
						{ id: 'all', label: 'All Markets' },
						{ id: 'buy_only', label: `Buy Signals (${buySignalsCount})` },
						{ id: 'stock', label: 'US Stocks' },
						{ id: 'etf', label: 'ETFs' },
						{ id: 'forex', label: 'Forex' },
						{ id: 'commodity', label: 'Gold' },
						{ id: 'crypto', label: 'Crypto' }
					] as pill}
						<button
							type="button"
							onclick={() => (scannerCat = pill.id as ScannerCat)}
							class="px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer {scannerCat === pill.id
								? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
								: 'bg-slate-900/70 border-slate-800 text-slate-400 hover:text-white'}"
						>
							{pill.label}
						</button>
					{/each}
				</div>

				<!-- Ranked Signal Cards Grid -->
				<div class="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
					{#each filteredScanner as item}
						{@const isWatched = watchedSymbols.has(item.symbol)}
						<div class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-4 hover:border-slate-700 transition">
							<div class="space-y-3">
								<!-- Top Row -->
								<div class="flex items-start justify-between gap-3">
									<button
										type="button"
										onclick={() => (inspectingSymbol = item.symbol)}
										class="text-left min-w-0 group cursor-pointer"
									>
										<div class="flex items-center gap-2 flex-wrap">
											<span class="text-base font-bold text-white group-hover:text-emerald-300 transition">
												{item.symbol}
											</span>
											<span class="text-[10px] uppercase px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
												{item.asset_type}
											</span>
										</div>
										<div class="text-xs text-slate-400 truncate mt-0.5">{item.display_name}</div>
									</button>

									<span class="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase border shrink-0 {signalBadge(item.signal)}">
										{item.signal.replace('_', ' ')}
									</span>
								</div>

								<!-- Price & Quant Score -->
								<div class="flex items-end justify-between gap-3">
									<div>
										<div class="text-2xl font-bold font-mono-num text-white">
											{item.price} <span class="text-xs font-normal text-slate-400">{item.currency}</span>
										</div>
										<div class="inline-flex items-center gap-1 text-xs font-mono-num font-semibold {item.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
											{#if item.change_pct >= 0}
												<TrendingUp class="w-3.5 h-3.5" /> +{item.change_pct}%
											{:else}
												<TrendingDown class="w-3.5 h-3.5" /> {item.change_pct}%
											{/if}
											{#if item.return_1m_pct !== null}
												<span class="text-slate-500 font-normal ml-1">1M: {item.return_1m_pct > 0 ? '+' : ''}{item.return_1m_pct}%</span>
											{/if}
										</div>
									</div>

									<div class="text-right">
										<div class="text-[10px] text-slate-400 uppercase">Quant Score</div>
										<div class="text-lg font-bold font-mono-num text-white">{item.quant_score}<span class="text-xs text-slate-500">/100</span></div>
									</div>
								</div>

								<!-- Score Bar -->
								<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
									<div class="h-full rounded-full transition-all {scoreBarColor(item.quant_score)}" style="width: {item.quant_score}%"></div>
								</div>

								<!-- Compact Trade Levels -->
								<div class="grid grid-cols-3 gap-1.5 text-[11px] font-mono-num">
									<div class="p-2 rounded-lg bg-slate-950/75 border border-slate-800/80">
										<div class="text-[9px] text-slate-500 font-sans uppercase">RSI 14</div>
										<div class="text-slate-200 font-semibold mt-0.5">{item.rsi_14 ?? '—'}</div>
									</div>
									<div class="p-2 rounded-lg bg-slate-950/75 border border-rose-500/20">
										<div class="text-[9px] text-rose-300/80 font-sans uppercase">Stop</div>
										<div class="text-rose-300 font-semibold mt-0.5">{item.stop_loss}</div>
									</div>
									<div class="p-2 rounded-lg bg-slate-950/75 border border-emerald-500/20">
										<div class="text-[9px] text-emerald-300/80 font-sans uppercase">Target</div>
										<div class="text-emerald-300 font-semibold mt-0.5">{item.take_profit}</div>
									</div>
								</div>

								<!-- Top Quant Driver -->
								{#if item.reasons.length > 0}
									<p class="text-[11px] text-slate-300 leading-relaxed line-clamp-2">
										{item.reasons[0]}
									</p>
								{/if}
							</div>

							<!-- Action Row -->
							<div class="flex items-center gap-2 pt-2 border-t border-slate-800/70">
								<button
									type="button"
									onclick={() => openTradeForSignal(item, 'buy')}
									class="flex-1 py-2 px-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer transition"
								>
									Paper Buy
								</button>
								<button
									type="button"
									onclick={() => (inspectingSymbol = item.symbol)}
									class="py-2 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 inline-flex items-center gap-1 cursor-pointer transition"
								>
									<BarChart3 class="w-3.5 h-3.5 text-cyan-400" /> Chart
								</button>
								<button
									type="button"
									onclick={() => quickAddWatch(item)}
									title={isWatched ? 'Update watchlist alerts' : 'Add to Watchlist'}
									class="p-2 rounded-xl border transition cursor-pointer {isWatched
										? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
										: 'bg-slate-900 hover:bg-slate-800 border-slate-800 text-slate-400 hover:text-amber-300'}"
								>
									<Star class="w-3.5 h-3.5 {isWatched ? 'fill-amber-400' : ''}" />
								</button>
							</div>
						</div>
					{/each}
				</div>
			</div>

		<!-- ==================== TAB 2: PAPER PORTFOLIO ($10,000 SANDBOX) ==================== -->
		{:else if activeTab === 'paper' && portfolio}
			{@const pnlNum = Number.parseFloat(portfolio.total_pnl) || 0}
			<div class="space-y-6">
				<!-- 4-Card Paper Portfolio Hero -->
				<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
					<div class="card-surface rounded-2xl p-5">
						<div class="text-xs text-slate-400">Total Virtual Equity</div>
						<div class="text-2xl font-bold font-mono-num text-white mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
							${Number.parseFloat(portfolio.total_equity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
						</div>
						<div class="text-[11px] text-slate-400 mt-1">
							Started with ${Number.parseFloat(portfolio.starting_cash).toLocaleString()}
						</div>
					</div>

					<div class="card-surface rounded-2xl p-5">
						<div class="text-xs text-slate-400">Total Paper P&L</div>
						<div class="text-2xl font-bold font-mono-num mt-1.5 {privacyMode ? 'privacy-blur' : ''} {pnlNum >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
							{pnlNum >= 0 ? '+' : ''}${pnlNum.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
						</div>
						<div class="text-[11px] font-mono-num mt-1 {portfolio.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
							{portfolio.total_return_pct >= 0 ? '+' : ''}{portfolio.total_return_pct}% return
						</div>
					</div>

					<div class="card-surface rounded-2xl p-5">
						<div class="text-xs text-slate-400">Available Paper Cash</div>
						<div class="text-2xl font-bold font-mono-num text-cyan-300 mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
							${Number.parseFloat(portfolio.cash_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
						</div>
						<div class="text-[11px] text-slate-400 mt-1">
							Invested: ${Number.parseFloat(portfolio.invested_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
						</div>
					</div>

					<div class="card-surface rounded-2xl p-5 flex flex-col justify-between">
						<div>
							<div class="text-xs text-slate-400">Closed Trades Win Rate</div>
							<div class="text-2xl font-bold font-mono-num text-white mt-1.5">
								{portfolio.win_rate_pct !== null ? `${portfolio.win_rate_pct}%` : '—'}
							</div>
							<div class="text-[11px] text-slate-400 mt-1">
								{portfolio.closed_trades_count} closed · Realized ${Number.parseFloat(portfolio.realized_pnl_total).toFixed(2)}
							</div>
						</div>
					</div>
				</div>

				<!-- Open Positions -->
				<div class="card-surface rounded-2xl overflow-hidden">
					<div class="p-5 border-b border-slate-800/80 flex items-center justify-between gap-3">
						<div>
							<h2 class="text-base font-semibold text-white">Open Paper Positions ({portfolio.positions.length})</h2>
							<p class="text-xs text-slate-400 mt-0.5">Live marked-to-market positions from your AI Trader Bot simulations.</p>
						</div>
						<button
							type="button"
							onclick={() => (confirmResetOpen = true)}
							class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-rose-500/15 border border-slate-800 hover:border-rose-500/35 text-xs font-medium text-slate-300 hover:text-rose-300 cursor-pointer transition"
						>
							<RotateCcw class="w-3.5 h-3.5" /> Reset to $10k
						</button>
					</div>

					{#if portfolio.positions.length === 0}
						<div class="p-10 text-center space-y-2">
							<Bot class="w-8 h-8 text-slate-600 mx-auto" />
							<p class="text-sm font-medium text-slate-300">No open paper positions yet</p>
							<p class="text-xs text-slate-500">Pick any Buy Signal in the AI Trader Bot Scanner and test it risk-free with your $10,000 virtual cash.</p>
							<button
								type="button"
								onclick={() => (activeTab = 'scanner')}
								class="mt-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer"
							>
								Browse AI Trader Bot Picks
							</button>
						</div>
					{:else}
						<div class="overflow-x-auto">
							<table class="w-full text-left border-collapse text-xs">
								<thead>
									<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-950/40">
										<th class="py-3 px-4">Asset</th>
										<th class="py-3 px-3 text-right">Qty</th>
										<th class="py-3 px-3 text-right">Avg Entry</th>
										<th class="py-3 px-3 text-right">Live Price</th>
										<th class="py-3 px-3 text-right">Market Value</th>
										<th class="py-3 px-3 text-right">Unrealized P&L</th>
										<th class="py-3 px-4 text-right">Actions</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-slate-800/60 font-mono-num">
									{#each portfolio.positions as pos}
										{@const upnl = Number.parseFloat(pos.unrealized_pnl) || 0}
										<tr class="hover:bg-slate-900/45">
											<td class="py-3 px-4 font-sans">
												<button
													type="button"
													onclick={() => (inspectingSymbol = pos.symbol)}
													class="text-left group cursor-pointer"
												>
													<div class="font-bold text-white group-hover:text-emerald-300 flex items-center gap-1.5">
														{pos.symbol}
														{#if pos.signal}
															<span class="text-[9px] px-1.5 py-0.5 rounded border uppercase {signalBadge(pos.signal)}">
																{pos.signal.replace('_', ' ')}
															</span>
														{/if}
													</div>
													<div class="text-[11px] text-slate-400">{pos.display_name}</div>
												</button>
											</td>
											<td class="py-3 px-3 text-right text-slate-200">{Number.parseFloat(pos.quantity).toFixed(4)}</td>
											<td class="py-3 px-3 text-right text-slate-400">${Number.parseFloat(pos.avg_entry_price).toFixed(2)}</td>
											<td class="py-3 px-3 text-right text-white font-semibold">${pos.live_price.toFixed(2)}</td>
											<td class="py-3 px-3 text-right text-white {privacyMode ? 'privacy-blur' : ''}">
												${Number.parseFloat(pos.market_value).toLocaleString(undefined, { minimumFractionDigits: 2 })}
											</td>
											<td class="py-3 px-3 text-right font-semibold {privacyMode ? 'privacy-blur' : ''} {upnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
												{upnl >= 0 ? '+' : ''}${upnl.toFixed(2)} ({pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct}%)
											</td>
											<td class="py-3 px-4 text-right font-sans whitespace-nowrap">
												<div class="inline-flex gap-1.5">
													<button
														type="button"
														onclick={() => openTradeForPosition(pos, 'buy')}
														class="px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-emerald-300 font-semibold cursor-pointer"
													>
														Buy
													</button>
													<button
														type="button"
														onclick={() => openTradeForPosition(pos, 'sell')}
														class="px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/35 text-rose-300 font-semibold cursor-pointer"
													>
														Sell
													</button>
												</div>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/if}
				</div>

				<!-- Paper Trade Journal -->
				<div class="card-surface rounded-2xl p-5 space-y-3">
					<h2 class="text-sm font-semibold text-white">Paper Trade Journal ({portfolio.recent_trades.length})</h2>
					{#if portfolio.recent_trades.length === 0}
						<p class="text-xs text-slate-500 py-3">Your simulated buy/sell orders and bot rationales will be logged here.</p>
					{:else}
						<div class="divide-y divide-slate-800/70 text-xs">
							{#each portfolio.recent_trades as tr}
								<div class="py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
									<div class="flex items-center gap-2.5 flex-wrap">
										<span class="px-2 py-0.5 rounded font-semibold uppercase text-[10px] {tr.side === 'buy' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}">
											{tr.side}
										</span>
										<strong class="text-white">{tr.symbol}</strong>
										<span class="font-mono-num text-slate-400">
											{Number.parseFloat(tr.quantity).toFixed(4)} @ ${Number.parseFloat(tr.price).toFixed(2)}
										</span>
										{#if tr.signal_at_trade}
											<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-cyan-300">
												Bot: {tr.signal_at_trade.replace('_', ' ')}
											</span>
										{/if}
									</div>
									<div class="flex items-center gap-3 font-mono-num">
										<span class="text-slate-200 {privacyMode ? 'privacy-blur' : ''}">
											${Number.parseFloat(tr.total_value).toFixed(2)}
										</span>
										{#if tr.realized_pnl !== null}
											{@const rpnl = Number.parseFloat(tr.realized_pnl)}
											<span class="font-semibold {rpnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
												P&L {rpnl >= 0 ? '+' : ''}${rpnl.toFixed(2)}
											</span>
										{/if}
										<span class="text-slate-500 text-[11px]">{formatDate(tr.executed_at)}</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

		<!-- ==================== TAB 3: WATCHLIST & PRICE ALERTS ==================== -->
		{:else if activeTab === 'watchlist'}
			<div class="card-surface rounded-2xl overflow-hidden">
				<div class="p-5 border-b border-slate-800/80">
					<h2 class="text-base font-semibold text-white">Watchlist & Price Target Alerts</h2>
					<p class="text-xs text-slate-400 mt-0.5">
						Track favorite stocks, ETFs, and Forex pairs with custom Buy / Sell target price triggers.
					</p>
				</div>

				{#if watchlist.length === 0}
					<div class="p-10 text-center space-y-2">
						<Star class="w-8 h-8 text-slate-600 mx-auto" />
						<p class="text-sm font-medium text-slate-300">Your Watchlist is empty</p>
						<p class="text-xs text-slate-500">Click the star icon on any asset in the AI Trader Bot Scanner or search any ticker above.</p>
					</div>
				{:else}
					<div class="divide-y divide-slate-800/70">
						{#each watchlist as item}
							<div class="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-900/40 transition">
								<button
									type="button"
									onclick={() => (inspectingSymbol = item.symbol)}
									class="text-left min-w-0 flex-1 cursor-pointer group"
								>
									<div class="flex items-center gap-2 flex-wrap">
										<span class="text-sm font-bold text-white group-hover:text-emerald-300">{item.symbol}</span>
										<span class="text-xs text-slate-400">{item.display_name}</span>
										{#if item.signal}
											<span class="text-[10px] px-2 py-0.5 rounded-full border uppercase font-semibold {signalBadge(item.signal)}">
												{item.signal.replace('_', ' ')}
											</span>
										{/if}
										{#if item.alert_triggered !== 'none'}
											<span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-400/50 text-amber-200 font-bold uppercase">
												{item.alert_triggered === 'buy_target_hit' ? 'Buy Alert Hit!' : 'Sell Alert Hit!'}
											</span>
										{/if}
									</div>
									<div class="text-[11px] text-slate-400 font-mono-num mt-1 flex items-center gap-3 flex-wrap">
										<span>Buy Alert: <strong class="text-emerald-300">{item.target_buy_price ?? '—'}</strong></span>
										<span>Sell Alert: <strong class="text-cyan-300">{item.target_sell_price ?? '—'}</strong></span>
										{#if item.notes}
											<span class="font-sans text-slate-500">· {item.notes}</span>
										{/if}
									</div>
								</button>

								<div class="flex items-center justify-between md:justify-end gap-4 shrink-0">
									<div class="text-right font-mono-num">
										<div class="text-sm font-bold text-white">
											{item.live_price !== null ? `${item.live_price} ${item.currency}` : '—'}
										</div>
										{#if item.change_pct !== null}
											<div class="text-[11px] {item.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
												{item.change_pct >= 0 ? '+' : ''}{item.change_pct}%
											</div>
										{/if}
									</div>

									<div class="flex items-center gap-1.5">
										<button
											type="button"
											onclick={() => (inspectingSymbol = item.symbol)}
											class="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 cursor-pointer"
										>
											Chart & Alerts
										</button>
										<button
											type="button"
											onclick={() => removeWatch(item)}
											title="Remove from watchlist"
											class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										>
											<Trash2 class="w-4 h-4" />
										</button>
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Educational Research Guardrail Footer -->
		<p class="text-[11px] text-slate-500 text-center pt-2">
			Financinio Markets & AI Trader Bot provides automated quantitative research, technical indicators, and simulated virtual paper trading for educational purposes only — not licensed investment advice or live brokerage execution.
		</p>
	</div>
{/if}

<!-- Symbol Deep-Dive Chart & Quant Drawer -->
<SymbolDetailDrawer
	symbol={inspectingSymbol}
	{watchlist}
	onClose={() => (inspectingSymbol = null)}
	onOpenTrade={(qa) => {
		inspectingSymbol = null;
		openTradeForSignal(qa, 'buy');
	}}
	onWatchlistUpdated={async () => {
		watchlist = await api.listWatchlist();
	}}
/>

<!-- Paper Trade Execution Modal -->
{#if tradeModalState}
	<PaperTradeModal
		symbol={tradeModalState.symbol}
		displayName={tradeModalState.displayName}
		livePrice={tradeModalState.livePrice}
		currency={tradeModalState.currency}
		signal={tradeModalState.signal}
		{portfolio}
		initialSide={tradeModalState.initialSide}
		onClose={() => (tradeModalState = null)}
		onTraded={(updated, msg) => {
			portfolio = updated;
			notice = msg;
		}}
	/>
{/if}

<!-- Safe Reset Paper Portfolio Modal -->
{#if confirmResetOpen}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-4 border border-rose-500/30">
			<div class="flex items-start justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400 flex items-center justify-center shrink-0">
						<RotateCcw class="w-5 h-5" />
					</div>
					<div>
						<h3 class="text-base font-semibold text-white">Reset Paper Portfolio?</h3>
						<p class="text-xs text-slate-400">Clear positions & restart with $10,000.00</p>
					</div>
				</div>
				<button type="button" onclick={() => (confirmResetOpen = false)} class="p-1 text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>
			<p class="text-xs text-slate-300 leading-relaxed">
				This closes all open virtual paper positions, clears your paper trade journal, and restores your virtual cash balance to <strong>$10,000.00</strong>. Your real Neon financial accounts are untouched.
			</p>
			<div class="flex items-center justify-end gap-2">
				<button
					type="button"
					disabled={resetting}
					onclick={() => (confirmResetOpen = false)}
					class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={resetting}
					onclick={handleConfirmReset}
					class="px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					{resetting ? 'Resetting...' : 'Reset Paper Portfolio'}
				</button>
			</div>
		</div>
	</div>
{/if}
