<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import type { Category, DashboardSummary, ProactiveInsight } from '$lib/api/types';
	import { formatDate, formatMoney, formatShortMonth } from '$lib/utils/format';
	import {
		TrendingUp,
		TrendingDown,
		Wallet,
		Percent,
		UploadCloud,
		Plus,
		AlertCircle,
		ArrowUpRight,
		ArrowDownRight,
		Sparkles,
		Send
	} from 'lucide-svelte';

	let summary = $state<DashboardSummary | null>(null);
	let categories = $state<Map<string, Category>>(new Map());
	let insights = $state<ProactiveInsight[]>([]);
	let quickPrompt = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const [sum, cats, ins] = await Promise.all([
				api.dashboardSummary(6),
				api.listCategories(),
				api.listInsights().catch(() => [] as ProactiveInsight[])
			]);
			summary = sum;
			categories = new Map(cats.map((c) => [c.id, c]));
			insights = ins.slice(0, 3);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	function askLunaQuick(e: SubmitEvent) {
		e.preventDefault();
		const q = quickPrompt.trim();
		if (!q) return;
		goto(`/advisor?q=${encodeURIComponent(q)}`);
	}

	let maxBarValue = $derived.by(() => {
		if (!summary) return 100;
		const vals = summary.monthly_cash_flow.flatMap((m) => [
			Number.parseFloat(m.income),
			Number.parseFloat(m.expenses)
		]);
		return Math.max(...vals, 100);
	});
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Financial Overview</h1>
			<p class="text-sm text-slate-400 mt-0.5">Real-time net worth, cash flow trends, and spending breakdown.</p>
		</div>
		<div class="flex items-center gap-2.5">
			<a
				href="/imports"
				class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-sm font-medium text-slate-200 transition"
			>
				<UploadCloud class="w-4 h-4 text-emerald-400" />
				AI Import
			</a>
			<a
				href="/transactions"
				class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-sm font-semibold transition"
			>
				<Plus class="w-4 h-4" />
				Add Transaction
			</a>
		</div>
	</div>

	{#if loading}
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each Array(4) as _}
				<div class="card-surface rounded-2xl p-5 h-28 animate-pulse"></div>
			{/each}
		</div>
	{:else if error}
		<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
			{error}
		</div>
	{:else if summary}
		{#if summary.pending_review_batches > 0}
			<a
				href="/imports"
				class="flex items-center justify-between gap-4 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 hover:border-amber-400/60 transition"
			>
				<div class="flex items-center gap-3">
					<AlertCircle class="w-5 h-5 text-amber-400 shrink-0" />
					<div class="text-sm">
						<span class="font-semibold text-amber-200">
							{summary.pending_review_batches} AI import {summary.pending_review_batches === 1 ? 'batch' : 'batches'} waiting for review
						</span>
						<span class="text-amber-200/75 ml-1.5">Approve or edit AI-categorized rows before committing to your ledger.</span>
					</div>
				</div>
				<span class="text-xs font-semibold text-amber-300 whitespace-nowrap">Review Queue →</span>
			</a>
		{/if}

		<!-- Luna Quick-Ask & Proactive Insights -->
		<div class="card-surface rounded-2xl p-4 sm:p-5 space-y-3 border-emerald-500/20">
			<form onsubmit={askLunaQuick} class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
				<div class="flex items-center gap-2.5 flex-1 px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 focus-within:border-emerald-500">
					<Sparkles class="w-4 h-4 text-emerald-400 shrink-0" />
					<input
						type="text"
						bind:value={quickPrompt}
						placeholder="Ask Luna anything — e.g. 'How much did I spend on dining?' or 'Create a $400 Groceries budget'"
						class="w-full bg-transparent text-sm text-white placeholder:text-slate-500 focus:outline-none"
					/>
				</div>
				<button
					type="submit"
					class="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs transition cursor-pointer shrink-0"
				>
					<Send class="w-3.5 h-3.5" /> Ask Luna
				</button>
			</form>

			{#if insights.length > 0}
				<div class="grid md:grid-cols-3 gap-2.5 pt-1">
					{#each insights as ins}
						<a
							href="/advisor"
							class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/90 hover:border-emerald-500/40 transition space-y-1"
						>
							<div class="text-xs font-semibold truncate {ins.severity === 'alert' ? 'text-rose-300' : ins.severity === 'warning' ? 'text-amber-300' : 'text-emerald-300'}">
								{ins.title}
							</div>
							<p class="text-[11px] text-slate-400 line-clamp-2">
								{ins.summary.replace(/[*#_`>-]/g, '').replace(/\s+/g, ' ').trim()}
							</p>
						</a>
					{/each}
				</div>
			{/if}
		</div>

		<!-- KPI Cards -->
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			<div class="card-surface rounded-2xl p-5">
				<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
					<span>Net Worth</span>
					<Wallet class="w-4 h-4 text-emerald-400" />
				</div>
				<div class="text-2xl font-bold text-white font-mono-num mt-2">
					{formatMoney(summary.net_worth, summary.base_currency)}
				</div>
				<div class="text-xs text-slate-400 mt-1.5 font-mono-num">
					Assets {formatMoney(summary.total_assets, summary.base_currency)} · Debt {formatMoney(summary.total_liabilities, summary.base_currency)}
				</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
					<span>This Month Income</span>
					<TrendingUp class="w-4 h-4 text-emerald-400" />
				</div>
				<div class="text-2xl font-bold text-emerald-400 font-mono-num mt-2">
					{formatMoney(summary.period_income, summary.base_currency)}
				</div>
				<div class="text-xs text-slate-400 mt-1.5">Excludes internal transfers</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
					<span>This Month Expenses</span>
					<TrendingDown class="w-4 h-4 text-rose-400" />
				</div>
				<div class="text-2xl font-bold text-rose-400 font-mono-num mt-2">
					{formatMoney(summary.period_expenses, summary.base_currency)}
				</div>
				<div class="text-xs text-slate-400 mt-1.5 font-mono-num">
					Net Cash Flow: {formatMoney(summary.period_net, summary.base_currency)}
				</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
					<span>Savings Rate</span>
					<Percent class="w-4 h-4 text-cyan-400" />
				</div>
				<div class="text-2xl font-bold text-cyan-300 font-mono-num mt-2">
					{summary.savings_rate.toFixed(1)}%
				</div>
				<div class="text-xs text-slate-400 mt-1.5">Target benchmark: 20%+</div>
			</div>
		</div>

		<!-- Charts Row -->
		<div class="grid lg:grid-cols-3 gap-6">
			<!-- 6-Month Cash Flow Chart -->
			<div class="lg:col-span-2 card-surface rounded-2xl p-6 space-y-5">
				<div class="flex items-center justify-between">
					<div>
						<h2 class="text-base font-semibold text-white">6-Month Cash Flow</h2>
						<p class="text-xs text-slate-400">Monthly income vs. expenses</p>
					</div>
					<div class="flex items-center gap-4 text-xs text-slate-400">
						<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-emerald-400"></span>Income</span>
						<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-rose-400/80"></span>Expenses</span>
					</div>
				</div>

				<div class="grid grid-cols-6 gap-3 items-end h-52 pt-4">
					{#each summary.monthly_cash_flow as pt}
						{@const inc = Number.parseFloat(pt.income)}
						{@const exp = Number.parseFloat(pt.expenses)}
						{@const incPct = Math.max(inc > 0 ? (inc / maxBarValue) * 100 : 2, 2)}
						{@const expPct = Math.max(exp > 0 ? (exp / maxBarValue) * 100 : 2, 2)}
						<div class="flex flex-col items-center gap-2 h-full justify-end">
							<div class="w-full flex items-end justify-center gap-1.5 h-40">
								<div
									title="Income: {formatMoney(inc, summary.base_currency)}"
									class="w-4 sm:w-5 rounded-t-md bg-emerald-400/90 hover:bg-emerald-300 transition-all"
									style="height: {incPct}%"
								></div>
								<div
									title="Expenses: {formatMoney(exp, summary.base_currency)}"
									class="w-4 sm:w-5 rounded-t-md bg-rose-400/80 hover:bg-rose-300 transition-all"
									style="height: {expPct}%"
								></div>
							</div>
							<span class="text-xs text-slate-400 font-medium">{formatShortMonth(pt.month)}</span>
						</div>
					{/each}
				</div>
			</div>

			<!-- Category Breakdown -->
			<div class="card-surface rounded-2xl p-6 space-y-4">
				<div>
					<h2 class="text-base font-semibold text-white">Top Spending Categories</h2>
					<p class="text-xs text-slate-400">Share of total expenses</p>
				</div>

				{#if summary.category_breakdown.length === 0}
					<div class="py-12 text-center text-sm text-slate-500">
						No expenses recorded yet. Import a statement or add a transaction.
					</div>
				{:else}
					<div class="space-y-3.5">
						{#each summary.category_breakdown as item}
							<div class="space-y-1.5">
								<div class="flex items-center justify-between text-xs">
									<span class="font-medium text-slate-200 flex items-center gap-2">
										<span class="w-2.5 h-2.5 rounded-full" style="background-color: {item.color}"></span>
										{item.category_name}
									</span>
									<span class="font-mono-num text-slate-300">
										{formatMoney(item.total, summary.base_currency)} <span class="text-slate-500">({item.percentage}%)</span>
									</span>
								</div>
								<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
									<div
										class="h-full rounded-full"
										style="width: {Math.min(item.percentage, 100)}%; background-color: {item.color}"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<!-- Recent Transactions -->
		<div class="card-surface rounded-2xl p-6 space-y-4">
			<div class="flex items-center justify-between">
				<h2 class="text-base font-semibold text-white">Recent Transactions</h2>
				<a href="/transactions" class="text-xs font-medium text-emerald-400 hover:text-emerald-300">
					View All →
				</a>
			</div>

			{#if summary.recent_transactions.length === 0}
				<div class="py-10 text-center space-y-3">
					<p class="text-sm text-slate-400">Your ledger is ready. Create an account and import your first CSV or PDF bank statement.</p>
					<div class="flex items-center justify-center gap-3">
						<a href="/accounts" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-white">
							Create Account
						</a>
						<a href="/imports" class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-slate-950">
							Upload Statement
						</a>
					</div>
				</div>
			{:else}
				<div class="divide-y divide-slate-800/70">
					{#each summary.recent_transactions as tx}
						{@const cat = tx.category_id ? categories.get(tx.category_id) : null}
						<div class="py-3 flex items-center justify-between gap-4">
							<div class="flex items-center gap-3 min-w-0">
								<div
									class="h-9 w-9 rounded-xl flex items-center justify-center shrink-0 {tx.direction === 'inflow'
										? 'bg-emerald-500/15 text-emerald-400'
										: 'bg-slate-800 text-slate-300'}"
								>
									{#if tx.direction === 'inflow'}
										<ArrowDownRight class="w-4 h-4" />
									{:else}
										<ArrowUpRight class="w-4 h-4" />
									{/if}
								</div>
								<div class="min-w-0">
									<div class="text-sm font-medium text-white truncate">{tx.merchant_clean}</div>
									<div class="text-xs text-slate-400 flex items-center gap-2">
										<span>{formatDate(tx.occurred_at)}</span>
										{#if cat}
											<span class="px-1.5 py-0.5 rounded bg-slate-800/90 text-[11px]" style="color: {cat.color}">
												{cat.name}
											</span>
										{/if}
									</div>
								</div>
							</div>
							<div
								class="text-sm font-semibold font-mono-num shrink-0 {tx.direction === 'inflow'
									? 'text-emerald-400'
									: 'text-slate-100'}"
							>
								{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>
