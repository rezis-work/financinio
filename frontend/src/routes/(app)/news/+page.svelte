<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type {
		NewsArticle,
		NewsBriefingResponse,
		NewsCategory,
		NewsFeedResponse,
		NewsSentiment
	} from '$lib/api/types';
	import FinancinioLoader from '$lib/components/FinancinioLoader.svelte';
	import {
		Newspaper,
		Sparkles,
		RefreshCw,
		Search,
		ExternalLink,
		TrendingUp,
		TrendingDown,
		Globe,
		Clock,
		X,
		AlertTriangle,
		CheckCircle2,
		Landmark,
		Briefcase
	} from 'lucide-svelte';

	let loading = $state(true);
	let refreshing = $state(false);
	let activeCategory = $state<NewsCategory>('all');
	let sentimentFilter = $state<'all' | NewsSentiment>('all');
	let searchQuery = $state('');

	let feed = $state<NewsFeedResponse | null>(null);
	let briefing = $state<NewsBriefingResponse | null>(null);
	let loadingBriefing = $state(false);
	let error = $state<string | null>(null);

	const CATEGORIES: Array<{ id: NewsCategory; label: string }> = [
		{ id: 'all', label: 'All Global' },
		{ id: 'for_you', label: 'For My Portfolio' },
		{ id: 'markets', label: 'Wall Street & Tech' },
		{ id: 'macro_fx', label: 'Forex & Macro' },
		{ id: 'georgia', label: 'Georgia & NBG' },
		{ id: 'crypto_gold', label: 'Crypto & Gold' }
	];

	async function loadFeed(category: NewsCategory = activeCategory, forceRefresh = false) {
		activeCategory = category;
		if (!feed) loading = true;
		else refreshing = true;
		error = null;
		try {
			feed = await api.newsFeed({ category, forceRefresh });
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load live global news';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function generateBriefing() {
		loadingBriefing = true;
		error = null;
		try {
			briefing = await api.newsAiBriefing(activeCategory);
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Could not generate Luna Market Pulse';
		} finally {
			loadingBriefing = false;
		}
	}

	onMount(() => {
		loadFeed('all', false);
	});

	function relativeTime(iso: string): string {
		const dt = new Date(iso);
		const diffSec = Math.max(0, Math.floor((Date.now() - dt.getTime()) / 1000));
		if (diffSec < 60) return 'Just now';
		if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
		if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
		return `${Math.floor(diffSec / 86400)}d ago`;
	}

	function categoryLabel(cat: string): string {
		if (cat === 'markets') return 'Markets';
		if (cat === 'macro_fx') return 'Forex & Macro';
		if (cat === 'georgia') return 'Georgia & NBG';
		if (cat === 'crypto_gold') return 'Crypto & Gold';
		if (cat === 'for_you') return 'Portfolio';
		return cat;
	}

	function sentimentClass(s: NewsSentiment): string {
		if (s === 'bullish') return 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300';
		if (s === 'bearish') return 'bg-rose-500/15 border-rose-500/35 text-rose-300';
		return 'bg-slate-800 border-slate-700 text-slate-300';
	}

	function askLunaHref(art: NewsArticle): string {
		const q = encodeURIComponent(
			`Explain this breaking finance headline and how it could affect my personal finances, currency exposure, or watchlist: "${art.title}" (Source: ${art.source}).`
		);
		return `/advisor?q=${q}`;
	}

	let visibleArticles = $derived.by(() => {
		const list = feed?.articles ?? [];
		const q = searchQuery.trim().toLowerCase();
		return list.filter((art) => {
			if (sentimentFilter !== 'all' && art.sentiment !== sentimentFilter) return false;
			if (q) {
				const hay = `${art.title} ${art.summary} ${art.source} ${art.tickers.join(' ')}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		});
	});

	let leadStory = $derived(visibleArticles[0] ?? null);
	let gridStories = $derived(visibleArticles.slice(1));
</script>

{#if loading}
	<FinancinioLoader
		fullscreen={false}
		label="Loading Global Finance Newsroom"
		subtitles={[
			'Pulling live Wall Street, Forex & Macro headlines...',
			'Syncing Georgia & NBG economy news with your portfolio...'
		]}
	/>
{:else}
	<div class="space-y-6 pb-12">
		<!-- Executive Newsroom Header -->
		<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2.5 flex-wrap">
					<h1 class="text-2xl font-bold tracking-tight text-white">Global Finance Newsroom</h1>
					<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-500/15 border border-emerald-500/35 text-emerald-300">
						<span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
						Live Global Feed
					</span>
				</div>
				<p class="text-sm text-slate-400 mt-0.5">
					Real-time Wall Street, Forex, Macro, Crypto & Georgia NBG headlines — connected to your portfolio & Luna CFO.
				</p>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<button
					type="button"
					disabled={loadingBriefing}
					onclick={generateBriefing}
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-bold text-xs cursor-pointer transition disabled:opacity-55 shadow-lg shadow-emerald-500/20"
				>
					<Sparkles class="w-3.5 h-3.5 {loadingBriefing ? 'animate-spin' : ''}" />
					{loadingBriefing ? 'Summarizing Headlines...' : 'Luna AI Market Pulse'}
				</button>

				<button
					type="button"
					disabled={refreshing}
					onclick={() => loadFeed(activeCategory, true)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-200 cursor-pointer disabled:opacity-50"
				>
					<RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin text-emerald-400' : 'text-slate-400'}" />
					Refresh
				</button>
			</div>
		</div>

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

		<!-- Luna AI Daily Market Pulse Card -->
		{#if briefing}
			<div class="rounded-2xl p-5 sm:p-6 bg-gradient-to-br from-emerald-950/45 via-slate-900/90 to-violet-950/35 border border-emerald-500/35 space-y-4 shadow-xl">
				<div class="flex items-start justify-between gap-3">
					<div>
						<div class="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
							<Sparkles class="w-3.5 h-3.5" />
							Luna AI Market Pulse · Analyzed {briefing.articles_analyzed} Live Stories
						</div>
						<h2 class="text-base sm:text-lg font-bold text-white mt-1">{briefing.headline}</h2>
					</div>
					<button
						type="button"
						onclick={() => (briefing = null)}
						class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
						aria-label="Dismiss briefing"
					>
						<X class="w-4 h-4" />
					</button>
				</div>

				<ul class="space-y-2 text-xs sm:text-sm text-slate-200">
					{#each briefing.bullets as bullet}
						<li class="flex items-start gap-2.5 leading-relaxed">
							<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
							<span>{bullet}</span>
						</li>
					{/each}
				</ul>

				<div class="p-3.5 rounded-xl bg-slate-950/75 border border-cyan-500/25 text-xs text-cyan-100 leading-relaxed">
					<strong class="text-cyan-300">Personal CFO Takeaway:</strong> {briefing.personal_takeaway}
				</div>
			</div>
		{/if}

		<!-- Category Tabs, Search & Sentiment Bar -->
		<div class="card-surface rounded-2xl p-4 space-y-3.5">
			<div class="flex items-center gap-1.5 flex-wrap">
				{#each CATEGORIES as cat}
					{@const count = feed?.counts?.[cat.id] ?? 0}
					<button
						type="button"
						onclick={() => {
							briefing = null;
							loadFeed(cat.id, false);
						}}
						class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer {activeCategory === cat.id
							? 'bg-emerald-500/15 border-emerald-500/45 text-emerald-300'
							: 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white'}"
					>
						{#if cat.id === 'georgia'}
							<Landmark class="w-3.5 h-3.5 text-orange-400" />
						{:else if cat.id === 'for_you'}
							<Briefcase class="w-3.5 h-3.5 text-cyan-400" />
						{:else if cat.id === 'all'}
							<Globe class="w-3.5 h-3.5 text-emerald-400" />
						{/if}
						{cat.label}
						<span class="font-mono-num text-[10px] opacity-80">{count}</span>
					</button>
				{/each}
			</div>

			<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-slate-800/70">
				<div class="relative flex-1 max-w-md">
					<Search class="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
					<input
						type="text"
						bind:value={searchQuery}
						placeholder="Search headlines, tickers (NVDA, GEL, Fed), or sources..."
						class="w-full pl-9 pr-8 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
					/>
					{#if searchQuery}
						<button
							type="button"
							onclick={() => (searchQuery = '')}
							class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white cursor-pointer"
						>
							<X class="w-3.5 h-3.5" />
						</button>
					{/if}
				</div>

				<div class="flex items-center gap-1.5 text-xs">
					<span class="text-[11px] text-slate-500 mr-1">Tone:</span>
					{#each [
						{ id: 'all', label: 'All' },
						{ id: 'bullish', label: 'Bullish' },
						{ id: 'bearish', label: 'Bearish' },
						{ id: 'neutral', label: 'Neutral' }
					] as tone}
						<button
							type="button"
							onclick={() => (sentimentFilter = tone.id as 'all' | NewsSentiment)}
							class="px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition cursor-pointer {sentimentFilter === tone.id
								? 'bg-slate-800 border-slate-600 text-white'
								: 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'}"
						>
							{tone.label}
						</button>
					{/each}
				</div>
			</div>

			{#if activeCategory === 'for_you' && feed && feed.portfolio_symbols.length > 0}
				<div class="flex items-center flex-wrap gap-1.5 text-[11px] text-slate-400 pt-1">
					<span>Tracking your symbols:</span>
					{#each feed.portfolio_symbols as sym}
						<a
							href="/markets"
							class="px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-mono-num font-semibold hover:bg-cyan-500/20"
						>
							{sym}
						</a>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Empty State -->
		{#if visibleArticles.length === 0}
			<div class="card-surface rounded-2xl p-12 text-center space-y-2.5">
				<Newspaper class="w-8 h-8 text-slate-600 mx-auto" />
				<div class="text-sm font-semibold text-white">No headlines match this filter</div>
				<p class="text-xs text-slate-400">
					Try clearing your search or switching back to All Global news.
				</p>
				<button
					type="button"
					onclick={() => {
						searchQuery = '';
						sentimentFilter = 'all';
						loadFeed('all', false);
					}}
					class="mt-1 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white cursor-pointer"
				>
					Show All Global News
				</button>
			</div>
		{:else}
			<!-- Lead Hero Story -->
			{#if leadStory}
				<article class="card-surface rounded-2xl p-6 sm:p-7 border border-slate-800/90 hover:border-emerald-500/40 transition bg-gradient-to-br from-slate-900/95 via-slate-950 to-emerald-950/20 space-y-4">
					<div class="flex items-center justify-between gap-3 flex-wrap">
						<div class="flex items-center gap-2 flex-wrap text-[11px]">
							<span class="px-2.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/35 text-emerald-300 font-bold uppercase tracking-wider">
								Top Story
							</span>
							<span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-slate-300 font-semibold">
								{leadStory.source}
							</span>
							<span class="px-2 py-0.5 rounded-md bg-slate-900/80 text-cyan-300 font-medium">
								{categoryLabel(leadStory.category)}
							</span>
							<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase {sentimentClass(leadStory.sentiment)}">
								{#if leadStory.sentiment === 'bullish'}
									<TrendingUp class="w-3 h-3" />
								{:else if leadStory.sentiment === 'bearish'}
									<TrendingDown class="w-3 h-3" />
								{/if}
								{leadStory.sentiment}
							</span>
						</div>
						<span class="inline-flex items-center gap-1 text-xs text-slate-400 font-mono-num">
							<Clock class="w-3.5 h-3.5" /> {relativeTime(leadStory.published_at)}
						</span>
					</div>

					<a
						href={leadStory.url}
						target="_blank"
						rel="noopener noreferrer"
						class="block text-xl sm:text-2xl font-bold text-white hover:text-emerald-300 leading-snug transition"
					>
						{leadStory.title}
					</a>

					{#if leadStory.summary}
						<p class="text-sm text-slate-300 leading-relaxed max-w-3xl">
							{leadStory.summary}
						</p>
					{/if}

					<div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/70">
						<div class="flex items-center gap-1.5 flex-wrap">
							{#each leadStory.tickers as tk}
								<a
									href="/markets"
									class="px-2 py-0.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-mono-num font-bold text-cyan-300"
								>
									${tk}
								</a>
							{/each}
						</div>

						<div class="flex items-center gap-2">
							<a
								href={askLunaHref(leadStory)}
								class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/35 text-violet-200 text-xs font-semibold transition"
							>
								<Sparkles class="w-3.5 h-3.5" /> Ask Luna Impact
							</a>
							<a
								href={leadStory.url}
								target="_blank"
								rel="noopener noreferrer"
								class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold transition"
							>
								Read Story <ExternalLink class="w-3.5 h-3.5" />
							</a>
						</div>
					</div>
				</article>
			{/if}

			<!-- 2-Column Global News Grid -->
			<div class="grid md:grid-cols-2 gap-4">
				{#each gridStories as art}
					<article class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-3.5 hover:border-slate-700 transition">
						<div class="space-y-2.5">
							<div class="flex items-center justify-between gap-2 text-[11px]">
								<div class="flex items-center gap-1.5 flex-wrap min-w-0">
									<span class="font-semibold text-slate-300 truncate max-w-[160px]">{art.source}</span>
									<span class="text-slate-600">·</span>
									<span class="text-cyan-400 font-medium">{categoryLabel(art.category)}</span>
								</div>
								<span class="inline-flex items-center gap-1 text-slate-500 font-mono-num shrink-0">
									{relativeTime(art.published_at)}
								</span>
							</div>

							<a
								href={art.url}
								target="_blank"
								rel="noopener noreferrer"
								class="block text-sm sm:text-[15px] font-semibold text-white hover:text-emerald-300 leading-snug transition"
							>
								{art.title}
							</a>

							{#if art.summary}
								<p class="text-xs text-slate-400 leading-relaxed line-clamp-3">
									{art.summary}
								</p>
							{/if}
						</div>

						<div class="flex items-center justify-between gap-2 pt-2.5 border-t border-slate-800/70">
							<div class="flex items-center gap-1.5 flex-wrap">
								<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase {sentimentClass(art.sentiment)}">
									{#if art.sentiment === 'bullish'}
										<TrendingUp class="w-2.5 h-2.5" />
									{:else if art.sentiment === 'bearish'}
										<TrendingDown class="w-2.5 h-2.5" />
									{/if}
									{art.sentiment}
								</span>
								{#each art.tickers.slice(0, 3) as tk}
									<a
										href="/markets"
										class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] font-mono-num font-bold text-cyan-300 hover:border-cyan-500/40"
									>
										{tk}
									</a>
								{/each}
							</div>

							<div class="flex items-center gap-1.5 shrink-0">
								<a
									href={askLunaHref(art)}
									title="Ask Luna how this affects you"
									class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-violet-500/12 hover:bg-violet-500/25 border border-violet-500/30 text-violet-200 text-[11px] font-semibold transition"
								>
									<Sparkles class="w-3 h-3" /> Luna
								</a>
								<a
									href={art.url}
									target="_blank"
									rel="noopener noreferrer"
									class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 text-[11px] font-semibold transition"
								>
									Read <ExternalLink class="w-3 h-3" />
								</a>
							</div>
						</div>
					</article>
				{/each}
			</div>
		{/if}
	</div>
{/if}
