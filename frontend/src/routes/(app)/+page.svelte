<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type {
		Account,
		BudgetOverview,
		Category,
		DashboardSummary,
		FinancialGoal,
		FinancialHealthProfile,
		ProactiveInsight,
		RecurringOverview
	} from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import CashFlowChart from '$lib/components/dashboard/CashFlowChart.svelte';
	import SpendingDonutChart from '$lib/components/dashboard/SpendingDonutChart.svelte';
	import HealthScoreCard from '$lib/components/dashboard/HealthScoreCard.svelte';
	import QuickAddTransactionModal from '$lib/components/dashboard/QuickAddTransactionModal.svelte';
	import {
		TrendingUp,
		TrendingDown,
		Wallet,
		Percent,
		Plus,
		AlertCircle,
		ArrowUpRight,
		ArrowDownRight,
		Sparkles,
		Send,
		Eye,
		EyeOff,
		Landmark,
		Shield,
		CalendarClock,
		Target,
		PieChart,
		Search,
		Flame,
		CheckCircle2,
		Circle,
		AlertTriangle
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';

	let summary = $state<DashboardSummary | null>(null);
	let health = $state<FinancialHealthProfile | null>(null);
	let budgets = $state<BudgetOverview | null>(null);
	let recurring = $state<RecurringOverview | null>(null);
	let goals = $state<FinancialGoal[]>([]);
	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let categoriesMap = $state<Map<string, Category>>(new Map());
	let accountsMap = $state<Map<string, Account>>(new Map());
	let insights = $state<ProactiveInsight[]>([]);

	let months = $state<number>(6);
	let switchingMonths = $state(false);
	let privacyMode = $state(false);
	let quickAddOpen = $state(false);
	let quickPrompt = $state('');
	let txSearch = $state('');
	let txFilter = $state<'all' | 'inflow' | 'outflow'>('all');

	let loading = $state(true);
	let error = $state<string | null>(null);

	let greeting = $derived.by(() => {
		const h = new Date().getHours();
		const part = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
		const first = auth.user?.full_name?.trim().split(/\s+/)[0];
		return first ? `${part}, ${first}` : part;
	});

	let todayFormatted = $derived(
		new Date().toLocaleDateString('en-US', {
			weekday: 'long',
			month: 'long',
			day: 'numeric'
		})
	);

	let baseCcy = $derived(summary?.base_currency || auth.user?.base_currency || 'USD');

	async function loadDashboard(selectedMonths = months, silent = false) {
		if (!silent) loading = true;
		error = null;
		try {
			const [sum, cats, accs, ins, hlth, bud, rec, gls] = await Promise.all([
				api.dashboardSummary(selectedMonths),
				api.listCategories(),
				api.listAccounts(),
				api.listInsights().catch(() => [] as ProactiveInsight[]),
				api.financialHealthScore().catch(() => null),
				api.getBudgets().catch(() => null),
				api.getRecurring().catch(() => null),
				api.listGoals().catch(() => [] as FinancialGoal[])
			]);
			summary = sum;
			categories = cats;
			categoriesMap = new Map(cats.map((c) => [c.id, c]));
			accounts = accs;
			accountsMap = new Map(accs.map((a) => [a.id, a]));
			insights = ins.slice(0, 3);
			health = hlth;
			budgets = bud;
			recurring = rec;
			goals = gls;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	}

	async function changeTimeframe(m: number) {
		if (m === months || switchingMonths) return;
		months = m;
		switchingMonths = true;
		try {
			summary = await api.dashboardSummary(m);
		} catch {
			// keep existing chart on transient failure
		} finally {
			switchingMonths = false;
		}
	}

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadDashboard(months);
	});

	function askLuna(prompt: string) {
		const q = prompt.trim();
		if (!q) return;
		goto(`/advisor?q=${encodeURIComponent(q)}`);
	}

	function handleQuickAskSubmit(e: SubmitEvent) {
		e.preventDefault();
		askLuna(quickPrompt);
	}

	// Month-over-Month deltas computed from monthly_cash_flow
	let momDeltas = $derived.by(() => {
		const pts = summary?.monthly_cash_flow ?? [];
		if (pts.length < 2) return { incomePct: null as number | null, expensePct: null as number | null };
		const cur = pts[pts.length - 1];
		const prev = pts[pts.length - 2];
		const curInc = Number.parseFloat(cur.income) || 0;
		const prevInc = Number.parseFloat(prev.income) || 0;
		const curExp = Number.parseFloat(cur.expenses) || 0;
		const prevExp = Number.parseFloat(prev.expenses) || 0;
		return {
			incomePct: prevInc > 0 ? Math.round(((curInc - prevInc) / prevInc) * 1000) / 10 : null,
			expensePct: prevExp > 0 ? Math.round(((curExp - prevExp) / prevExp) * 1000) / 10 : null
		};
	});

	// Safe-to-spend & daily allowance calculation
	let safeToSpend = $derived.by(() => {
		const now = new Date();
		const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
		const daysRemaining = Math.max(1, daysInMonth - now.getDate() + 1);
		const rawSafe = health
			? Number.parseFloat(health.cash_flow_ratios.safe_to_spend_remaining_this_month)
			: summary
				? Number.parseFloat(summary.period_net)
				: 0;
		const safeVal = Number.isNaN(rawSafe) ? 0 : rawSafe;
		const daily = safeVal / daysRemaining;
		return { total: safeVal, daily, daysRemaining };
	});

	// Upcoming recurring outflows within next 30 days
	let upcomingBills = $derived.by(() => {
		if (!recurring) return [];
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		return recurring.items
			.filter((i) => i.is_active && i.direction === 'outflow')
			.map((i) => {
				const due = new Date(i.next_due_date + 'T00:00:00');
				const diffDays = Math.round((due.getTime() - today.getTime()) / 86_400_000);
				return { ...i, diffDays };
			})
			.sort((a, b) => a.diffDays - b.diffDays)
			.slice(0, 4);
	});

	let activeGoals = $derived(goals.filter((g) => !g.is_completed).slice(0, 3));
	let topBudgets = $derived((budgets?.budgets ?? []).slice(0, 4));

	// Context-aware dynamic Luna CFO prompt chips based on live user data
	let dynamicCfoChips = $derived.by(() => {
		const chips: string[] = [];
		const leak = health?.spending_leaks_mom?.[0];
		if (leak) {
			chips.push(`Why did ${leak.category} jump +${leak.increase_pct}% this month?`);
		}
		const over = health?.over_budget_categories?.[0];
		if (over) {
			chips.push(`Help me rebalance my ${over.category} budget`);
		}
		chips.push(`Can I afford a 500 ${baseCcy} purchase right now?`);
		chips.push('Run my full CFP Financial Health Checkup');
		if (chips.length < 4) {
			chips.push('Where am I leaking money & how can I boost my savings rate?');
		}
		return chips.slice(0, 4);
	});

	// Filterable recent transactions
	let filteredRecentTxs = $derived.by(() => {
		const list = summary?.recent_transactions ?? [];
		const q = txSearch.trim().toLowerCase();
		return list.filter((tx) => {
			if (txFilter !== 'all' && tx.direction !== txFilter) return false;
			if (!q) return true;
			const catName = (tx.category_id ? categoriesMap.get(tx.category_id)?.name : '') || '';
			return (
				tx.merchant_clean.toLowerCase().includes(q) ||
				catName.toLowerCase().includes(q) ||
				(tx.description || '').toLowerCase().includes(q)
			);
		});
	});

	// Onboarding checklist for brand-new users
	let showOnboarding = $derived(
		!loading &&
			summary !== null &&
			(accounts.length === 0 || summary.recent_transactions.length === 0)
	);
	let onboardingSteps = $derived([
		{
			label: 'Create your first bank account (e.g. GEL / USD)',
			done: accounts.length > 0,
			href: '/accounts'
		},
		{
			label: 'Import a Bank of Georgia (BOG) PDF or CSV statement',
			done: (summary?.recent_transactions.length ?? 0) > 0,
			href: '/imports'
		},
		{
			label: 'Set at least one monthly budget',
			done: (budgets?.budgets.length ?? 0) > 0,
			href: '/budgets'
		},
		{
			label: 'Run your first CFP Health Checkup with Luna',
			done: insights.length > 0,
			href: '/advisor?q=' + encodeURIComponent('Run a full Senior Financial Advisor checkup on my finances')
		}
	]);
</script>

<div class="space-y-6">
	<!-- 1. TOP EXECUTIVE ROW -->
	<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
		<div>
			<div class="flex items-center gap-2.5 flex-wrap">
				<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">{greeting}</h1>
				<span class="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[11px] font-mono-num text-slate-400">
					{baseCcy}
				</span>
			</div>
			<p class="text-xs sm:text-sm text-slate-400 mt-1">
				{todayFormatted} · Personal CFO Command Center
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<!-- Privacy Mode Toggle -->
			<button
				type="button"
				onclick={togglePrivacy}
				title={privacyMode ? 'Show amounts' : 'Hide amounts (Privacy Mode)'}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition cursor-pointer {privacyMode
					? 'bg-cyan-500/15 border-cyan-500/35 text-cyan-300'
					: 'bg-slate-900/90 hover:bg-slate-800 border-slate-800 text-slate-300'}"
			>
				{#if privacyMode}
					<EyeOff class="w-3.5 h-3.5" />
					<span class="hidden sm:inline">Hidden</span>
				{:else}
					<Eye class="w-3.5 h-3.5" />
					<span class="hidden sm:inline">Privacy</span>
				{/if}
			</button>

			<!-- Timeframe Switcher -->
			<div class="inline-flex p-1 rounded-xl bg-slate-900/90 border border-slate-800 text-xs">
				{#each [3, 6, 12] as m}
					<button
						type="button"
						disabled={switchingMonths}
						onclick={() => changeTimeframe(m)}
						class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer {months === m
							? 'bg-emerald-500/20 text-emerald-300'
							: 'text-slate-400 hover:text-white'}"
					>
						{m}M
					</button>
				{/each}
			</div>

			<!-- Dedicated BOG PDF Import CTA -->
			<a
				href="/imports"
				class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-orange-500/15 hover:bg-orange-500/25 border border-orange-500/35 text-xs font-semibold text-orange-200 transition"
			>
				<Landmark class="w-3.5 h-3.5 text-orange-400" />
				<span>Import BOG PDF</span>
			</a>

			<!-- Inline Quick-Add Transaction Modal Trigger -->
			<button
				type="button"
				onclick={() => (quickAddOpen = true)}
				class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold transition cursor-pointer shadow-sm"
			>
				<Plus class="w-4 h-4" />
				<span>Add Transaction</span>
			</button>
		</div>
	</div>

	{#if loading}
		<!-- Polished Skeleton Layout -->
		<div class="grid lg:grid-cols-12 gap-5">
			<div class="lg:col-span-5 card-surface rounded-2xl h-72 animate-pulse"></div>
			<div class="lg:col-span-7 space-y-4">
				<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
				<div class="grid sm:grid-cols-2 gap-4">
					{#each Array(4) as _}
						<div class="card-surface rounded-2xl h-24 animate-pulse"></div>
					{/each}
				</div>
			</div>
		</div>
	{:else if error}
		<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
			{error}
		</div>
	{:else if summary}
		<!-- Pending AI Import Reviews Banner -->
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
						<span class="text-amber-200/75 ml-1.5 hidden sm:inline">
							Approve or edit staged rows before committing to your ledger.
						</span>
					</div>
				</div>
				<span class="text-xs font-semibold text-amber-300 whitespace-nowrap">Review Queue →</span>
			</a>
		{/if}

		<!-- Smart Onboarding Checklist for New Workspaces -->
		{#if showOnboarding}
			<div class="card-surface rounded-2xl p-5 border-emerald-500/25 space-y-3">
				<div class="flex items-center justify-between">
					<div>
						<h2 class="text-sm font-semibold text-white">Quick Setup Checklist</h2>
						<p class="text-xs text-slate-400">Get your Personal CFO up and running in under 2 minutes.</p>
					</div>
					<span class="text-xs font-mono-num text-emerald-400 font-semibold">
						{onboardingSteps.filter((s) => s.done).length}/{onboardingSteps.length} done
					</span>
				</div>
				<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
					{#each onboardingSteps as step}
						<a
							href={step.href}
							class="flex items-start gap-2.5 p-3 rounded-xl border transition {step.done
								? 'bg-emerald-500/8 border-emerald-500/25 text-emerald-200'
								: 'bg-slate-950/70 border-slate-800 hover:border-emerald-500/40 text-slate-200'}"
						>
							{#if step.done}
								<CheckCircle2 class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
							{:else}
								<Circle class="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
							{/if}
							<span class="text-xs leading-snug {step.done ? 'line-through opacity-75' : ''}">
								{step.label}
							</span>
						</a>
					{/each}
				</div>
			</div>
		{/if}

		<!-- 2. CFO HERO GRID: Health Score Gauge + Safe-to-Spend & 4 Upgraded KPI Cards -->
		<div class="grid lg:grid-cols-12 gap-5">
			<!-- Left: Interactive Financial Health Score Gauge -->
			<div class="lg:col-span-5 flex flex-col">
				{#if health}
					<HealthScoreCard profile={health} onAskLuna={askLuna} />
				{:else}
					<div class="card-surface rounded-2xl p-6 flex-1 flex flex-col justify-center items-center text-center space-y-2">
						<Sparkles class="w-7 h-7 text-emerald-400" />
						<div class="text-sm font-semibold text-white">CFP Financial Health Score</div>
						<p class="text-xs text-slate-400 max-w-xs">
							Import your first statement to unlock your live 0–100 score and personalized priorities.
						</p>
					</div>
				{/if}
			</div>

			<!-- Right: Safe-to-Spend Daily Allowance + 4 KPI Cards with MoM Deltas -->
			<div class="lg:col-span-7 flex flex-col gap-4">
				<!-- Safe-to-Spend & Emergency Runway Banner -->
				<div class="card-surface rounded-2xl p-5 grid sm:grid-cols-3 gap-4 border-cyan-500/20">
					<div class="sm:col-span-1 space-y-1">
						<div class="text-[11px] font-medium text-cyan-300 flex items-center gap-1.5">
							<Flame class="w-3.5 h-3.5" /> Safe-to-Spend
						</div>
						<div
							class="text-2xl font-bold font-mono-num {safeToSpend.total >= 0 ? 'text-white' : 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{formatMoney(safeToSpend.total, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-400 font-mono-num">
							<span class="{safeToSpend.daily >= 0 ? 'text-emerald-400' : 'text-rose-400'} font-semibold {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(safeToSpend.daily, baseCcy)}/day
							</span>
							· {safeToSpend.daysRemaining}d left
						</div>
					</div>

					<div class="sm:border-l sm:border-slate-800/80 sm:pl-4 space-y-1.5">
						<div class="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
							<Shield class="w-3.5 h-3.5 text-emerald-400" /> Emergency Runway
						</div>
						<div class="text-xl font-bold text-white font-mono-num">
							{health ? `${health.cash_flow_ratios.emergency_runway_months} mo` : '—'}
						</div>
						<div class="space-y-1">
							<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
								<div
									class="h-full rounded-full {(health?.cash_flow_ratios.emergency_runway_months ?? 0) >= 6
										? 'bg-emerald-400'
										: (health?.cash_flow_ratios.emergency_runway_months ?? 0) >= 3
											? 'bg-cyan-400'
											: 'bg-amber-400'}"
									style="width: {Math.min(100, ((health?.cash_flow_ratios.emergency_runway_months ?? 0) / 6) * 100)}%"
								></div>
							</div>
							<div class="text-[10px] text-slate-500">Target: 6.0 months liquid cash</div>
						</div>
					</div>

					<div class="sm:border-l sm:border-slate-800/80 sm:pl-4 space-y-1.5">
						<div class="text-[11px] font-medium text-slate-400">Fixed Bills Ratio</div>
						<div class="text-xl font-bold text-white font-mono-num">
							{health ? `${health.cash_flow_ratios.fixed_recurring_ratio_pct}%` : '—'}
						</div>
						<div class="text-[11px] text-slate-400 font-mono-num">
							{#if health}
								<span class={privacyMode ? 'privacy-blur' : ''}>
									{formatMoney(health.cash_flow_ratios.monthly_recurring_burn, baseCcy)}/mo
								</span>
								<span class="text-slate-500">· ≤50% ideal</span>
							{:else}
								Benchmark: ≤50%
							{/if}
						</div>
					</div>
				</div>

				<!-- 4 Upgraded KPI Cards -->
				<div class="grid sm:grid-cols-2 gap-4 flex-1">
					<!-- Net Worth -->
					<a href="/wealth" class="card-surface card-surface-hover rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
						<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
							<span>Net Worth</span>
							<Wallet class="w-4 h-4 text-emerald-400" />
						</div>
						<div class="text-2xl font-bold text-white font-mono-num mt-2 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(summary.net_worth, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-400 mt-1.5 font-mono-num truncate {privacyMode ? 'privacy-blur' : ''}">
							Assets {formatMoney(summary.total_assets, baseCcy)} · Debt {formatMoney(summary.total_liabilities, baseCcy)}
						</div>
					</a>

					<!-- Monthly Income -->
					<div class="card-surface rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
						<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
							<span>This Month Income</span>
							<TrendingUp class="w-4 h-4 text-emerald-400" />
						</div>
						<div class="flex items-baseline justify-between gap-2 mt-2">
							<span class="text-2xl font-bold text-emerald-400 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(summary.period_income, baseCcy)}
							</span>
							{#if momDeltas.incomePct !== null}
								<span
									class="text-[10px] font-mono-num font-semibold px-1.5 py-0.5 rounded-full {momDeltas.incomePct >= 0
										? 'bg-emerald-500/15 text-emerald-300'
										: 'bg-rose-500/15 text-rose-300'}"
								>
									{momDeltas.incomePct >= 0 ? '+' : ''}{momDeltas.incomePct}% MoM
								</span>
							{/if}
						</div>
						<div class="text-[11px] text-slate-400 mt-1.5">Excludes internal transfers</div>
					</div>

					<!-- Monthly Expenses -->
					<div class="card-surface rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
						<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
							<span>This Month Expenses</span>
							<TrendingDown class="w-4 h-4 text-rose-400" />
						</div>
						<div class="flex items-baseline justify-between gap-2 mt-2">
							<span class="text-2xl font-bold text-rose-400 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(summary.period_expenses, baseCcy)}
							</span>
							{#if momDeltas.expensePct !== null}
								<span
									class="text-[10px] font-mono-num font-semibold px-1.5 py-0.5 rounded-full {momDeltas.expensePct <= 0
										? 'bg-emerald-500/15 text-emerald-300'
										: 'bg-rose-500/15 text-rose-300'}"
								>
									{momDeltas.expensePct >= 0 ? '+' : ''}{momDeltas.expensePct}% MoM
								</span>
							{/if}
						</div>
						<div class="text-[11px] text-slate-400 mt-1.5 font-mono-num">
							Net Flow:
							<span class="{Number.parseFloat(summary.period_net) >= 0 ? 'text-emerald-300' : 'text-rose-300'} {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(summary.period_net, baseCcy)}
							</span>
						</div>
					</div>

					<!-- Savings Rate -->
					<div class="card-surface rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
						<div class="flex items-center justify-between text-slate-400 text-xs font-medium">
							<span>Savings Rate</span>
							<Percent class="w-4 h-4 text-cyan-400" />
						</div>
						<div class="flex items-baseline justify-between gap-2 mt-2">
							<span class="text-2xl font-bold text-cyan-300 font-mono-num">
								{summary.savings_rate.toFixed(1)}%
							</span>
							<span class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full {summary.savings_rate >= 20
								? 'bg-emerald-500/15 text-emerald-300'
								: summary.savings_rate >= 10
									? 'bg-amber-500/15 text-amber-300'
									: 'bg-rose-500/15 text-rose-300'}">
								{summary.savings_rate >= 20 ? 'On Target' : 'Goal 20%+'}
							</span>
						</div>
						<div class="h-1.5 rounded-full bg-slate-800 overflow-hidden mt-2">
							<div
								class="h-full rounded-full transition-all {summary.savings_rate >= 20
									? 'bg-emerald-400'
									: summary.savings_rate >= 10
										? 'bg-cyan-400'
										: 'bg-amber-400'}"
								style="width: {Math.min(100, Math.max(0, (summary.savings_rate / 30) * 100))}%"
							></div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 3. INTERACTIVE CHARTS ROW -->
		<div class="grid lg:grid-cols-12 gap-5">
			<div class="lg:col-span-8">
				<CashFlowChart
					points={summary.monthly_cash_flow}
					currency={baseCcy}
					{months}
					{privacyMode}
					onChangeMonths={changeTimeframe}
				/>
			</div>
			<div class="lg:col-span-4">
				<SpendingDonutChart
					items={summary.category_breakdown}
					currency={baseCcy}
					{privacyMode}
					onAskCategory={(cat) =>
						askLuna(`Analyze my spending in "${cat}" this month — is it healthy and how can I optimize it?`)}
				/>
			</div>
		</div>

		<!-- 4. ACTIONABLE PULSE ROW -->
		<!-- 4a. Accounts Balance Strip -->
		<div class="space-y-2.5">
			<div class="flex items-center justify-between px-0.5">
				<h2 class="text-sm font-semibold text-white">Accounts Snapshot</h2>
				<a href="/accounts" class="text-xs font-medium text-emerald-400 hover:text-emerald-300">
					Manage Accounts →
				</a>
			</div>

			{#if accounts.length === 0}
				<div class="card-surface rounded-2xl p-5 flex items-center justify-between gap-4">
					<p class="text-xs text-slate-400">No accounts connected yet. Add your checking, savings, or BOG account to track balances.</p>
					<a href="/accounts" class="px-3.5 py-2 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs font-semibold shrink-0">
						+ Add Account
					</a>
				</div>
			{:else}
				<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
					{#each accounts.slice(0, 8) as acc}
						{@const bal = Number.parseFloat(acc.current_balance) || 0}
						<a
							href="/transactions"
							class="card-surface card-surface-hover rounded-2xl p-4 relative overflow-hidden space-y-2"
						>
							<div
								class="absolute top-0 inset-x-0 h-1"
								style="background-color: {acc.color || '#10b981'}"
							></div>
							<div class="flex items-center justify-between gap-2">
								<span class="text-xs font-semibold text-white truncate">{acc.name}</span>
								<span class="text-[10px] uppercase font-mono-num px-1.5 py-0.5 rounded bg-slate-900 text-slate-400">
									{acc.type}
								</span>
							</div>
							<div class="text-lg font-bold font-mono-num {bal < 0 ? 'text-rose-400' : 'text-white'} {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(acc.current_balance, acc.currency)}
							</div>
							<div class="text-[10px] text-slate-500 truncate">
								{acc.institution || acc.currency}
							</div>
						</a>
					{/each}
				</div>
			{/if}
		</div>

		<!-- 4b. 3-Column Pulse Grid: Budget Pacing + Upcoming Bills + Active Goals -->
		<div class="grid lg:grid-cols-3 gap-5">
			<!-- Live Budget Pacing with "Today" Marker -->
			<div class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-4">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<PieChart class="w-4 h-4 text-emerald-400" />
						<h2 class="text-sm font-semibold text-white">Budget Pacing</h2>
					</div>
					<a href="/budgets" class="text-[11px] font-medium text-emerald-400 hover:text-emerald-300">
						Manage →
					</a>
				</div>

				{#if topBudgets.length === 0}
					<div class="py-8 text-center space-y-2.5">
						<p class="text-xs text-slate-400">No monthly budgets yet. Apply the 50/30/20 template in one click.</p>
						<a href="/budgets" class="inline-block px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-white">
							Set Budgets
						</a>
					</div>
				{:else}
					<div class="space-y-3.5">
						{#if budgets}
							<div class="flex items-center justify-between text-[11px] text-slate-400 pb-1 border-b border-slate-800/80">
								<span>Day {budgets.days_elapsed} of {budgets.days_in_month}</span>
								<span class="font-mono-num text-cyan-300">Month pace: {budgets.pace_pct}%</span>
							</div>
						{/if}
						{#each topBudgets as b}
							<div class="space-y-1.5">
								<div class="flex items-center justify-between text-xs gap-2">
									<span class="font-medium text-slate-200 truncate">{b.category_name}</span>
									<span class="font-mono-num text-[11px] shrink-0 {privacyMode ? 'privacy-blur' : ''}">
										<span class={b.status === 'over_budget' ? 'text-rose-400 font-semibold' : 'text-slate-200'}>
											{formatMoney(b.spent, baseCcy)}
										</span>
										<span class="text-slate-500"> / {formatMoney(b.effective_limit, baseCcy)}</span>
									</span>
								</div>
								<div class="relative h-2 rounded-full bg-slate-800 overflow-visible">
									<div
										class="h-full rounded-full transition-all {b.status === 'over_budget'
											? 'bg-rose-400'
											: b.status === 'warning' || b.status === 'pacing_fast'
												? 'bg-amber-400'
												: 'bg-emerald-400'}"
										style="width: {Math.min(b.percent_used, 100)}%"
									></div>
									{#if budgets}
										<!-- Vertical "Today" Pace Marker -->
										<div
											title="Today's month pace ({budgets.pace_pct}%)"
											class="absolute -top-0.5 -bottom-0.5 w-0.5 bg-white/80 rounded-full"
											style="left: {Math.min(98, Math.max(2, budgets.pace_pct))}%"
										></div>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}

				{#if budgets && topBudgets.length > 0}
					<div class="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono-num">
						<span>Total Spent</span>
						<span class="text-slate-200 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(budgets.total_spent, baseCcy)} / {formatMoney(budgets.total_budgeted, baseCcy)}
						</span>
					</div>
				{/if}
			</div>

			<!-- Upcoming Bills & Subscriptions (Next 30d) -->
			<div class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-4">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<CalendarClock class="w-4 h-4 text-cyan-400" />
						<h2 class="text-sm font-semibold text-white">Upcoming Bills (30d)</h2>
					</div>
					<a href="/recurring" class="text-[11px] font-medium text-emerald-400 hover:text-emerald-300">
						View All →
					</a>
				</div>

				{#if recurring && recurring.price_hike_alerts.length > 0}
					<a
						href="/recurring"
						class="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-200 flex items-center gap-2"
					>
						<AlertTriangle class="w-3.5 h-3.5 text-amber-400 shrink-0" />
						<span class="truncate">
							Price hike detected on <strong>{recurring.price_hike_alerts[0].merchant_name}</strong>
						</span>
					</a>
				{/if}

				{#if upcomingBills.length === 0}
					<div class="py-8 text-center space-y-2.5">
						<p class="text-xs text-slate-400">No recurring bills tracked yet. Run auto-detection on your ledger.</p>
						<a href="/recurring" class="inline-block px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-white">
							Detect Subscriptions
						</a>
					</div>
				{:else}
					<div class="divide-y divide-slate-800/70">
						{#each upcomingBills as bill}
							<div class="py-2.5 flex items-center justify-between gap-3">
								<div class="min-w-0">
									<div class="text-xs font-medium text-white truncate">{bill.merchant_name}</div>
									<div class="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1.5">
										<span class="capitalize">{bill.cadence}</span>
										<span>·</span>
										<span
											class="{bill.diffDays <= 3
												? 'text-amber-300 font-semibold'
												: 'text-slate-400'}"
										>
											{bill.diffDays < 0
												? `${Math.abs(bill.diffDays)}d overdue`
												: bill.diffDays === 0
													? 'Due today'
													: `In ${bill.diffDays}d`}
										</span>
									</div>
								</div>
								<span class="text-xs font-mono-num font-semibold text-slate-100 shrink-0 {privacyMode ? 'privacy-blur' : ''}">
									{formatMoney(bill.amount, bill.currency)}
								</span>
							</div>
						{/each}
					</div>
				{/if}

				{#if recurring}
					<div class="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono-num">
						<span>30-Day Obligations</span>
						<span class="text-slate-200 font-semibold {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(recurring.upcoming_30d_total, baseCcy)}
						</span>
					</div>
				{/if}
			</div>

			<!-- Active Financial Goals -->
			<div class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-4">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<Target class="w-4 h-4 text-violet-400" />
						<h2 class="text-sm font-semibold text-white">Active Goals</h2>
					</div>
					<a href="/wealth" class="text-[11px] font-medium text-emerald-400 hover:text-emerald-300">
						Wealth & Goals →
					</a>
				</div>

				{#if activeGoals.length === 0}
					<div class="py-8 text-center space-y-2.5">
						<p class="text-xs text-slate-400">Set an Emergency Fund, travel, or investment goal to track monthly momentum.</p>
						<a href="/wealth" class="inline-block px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-medium text-white">
							+ Create Goal
						</a>
					</div>
				{:else}
					<div class="space-y-3.5">
						{#each activeGoals as g}
							<div class="space-y-1.5">
								<div class="flex items-center justify-between gap-2 text-xs">
									<span class="font-medium text-slate-200 truncate">{g.name}</span>
									<span class="font-mono-num text-emerald-400 font-semibold shrink-0">
										{Math.round(g.progress_pct)}%
									</span>
								</div>
								<div class="h-2 rounded-full bg-slate-800 overflow-hidden">
									<div
										class="h-full rounded-full transition-all"
										style="width: {Math.min(100, g.progress_pct)}%; background-color: {g.color || '#10b981'}"
									></div>
								</div>
								<div class="flex items-center justify-between text-[10px] text-slate-400 font-mono-num">
									<span class={privacyMode ? 'privacy-blur' : ''}>
										{formatMoney(g.current_amount, baseCcy)} / {formatMoney(g.target_amount, baseCcy)}
									</span>
									<span>{g.projected_completion_date ? `Est. ${formatDate(g.projected_completion_date)}` : 'Active'}</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<button
					type="button"
					onclick={() =>
						askLuna('Review my financial goals and recommend how much I should allocate monthly based on my surplus.')}
					class="w-full py-2 rounded-xl bg-violet-500/12 hover:bg-violet-500/20 border border-violet-500/25 text-violet-200 text-xs font-semibold transition cursor-pointer"
				>
					Optimize Goals with Luna
				</button>
			</div>
		</div>

		<!-- 5. UPGRADED LUNA CFO BRIEF + FILTERABLE RECENT TRANSACTIONS -->
		<div class="card-surface rounded-2xl p-5 space-y-3.5 border-emerald-500/20">
			<div class="flex items-center justify-between gap-2">
				<div class="flex items-center gap-2 text-xs font-semibold text-emerald-300">
					<Sparkles class="w-4 h-4" />
					<span>Luna · Senior Personal CFO Command Bar</span>
				</div>
				<a href="/advisor" class="text-xs text-slate-400 hover:text-emerald-300 transition">
					Open Full Chat →
				</a>
			</div>

			<form onsubmit={handleQuickAskSubmit} class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
				<div class="flex items-center gap-2.5 flex-1 px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 focus-within:border-emerald-500">
					<Sparkles class="w-4 h-4 text-emerald-400 shrink-0" />
					<input
						type="text"
						bind:value={quickPrompt}
						placeholder="Ask Luna before you spend — e.g. 'Can I afford a 1,200 {baseCcy} laptop?' or 'Spot my spending leaks'"
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

			<!-- Dynamic Context-Aware Decision Chips -->
			<div class="flex flex-wrap gap-2">
				{#each dynamicCfoChips as chip}
					<button
						type="button"
						onclick={() => askLuna(chip)}
						class="px-3 py-1.5 rounded-full bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-emerald-500/40 text-[11px] text-slate-300 hover:text-white transition cursor-pointer"
					>
						{chip}
					</button>
				{/each}
			</div>

			{#if insights.length > 0}
				<div class="grid md:grid-cols-3 gap-2.5 pt-1">
					{#each insights as ins}
						<a
							href="/advisor"
							class="p-3 rounded-xl bg-slate-950/75 border border-slate-800/90 hover:border-emerald-500/40 transition space-y-1"
						>
							<div
								class="text-xs font-semibold truncate {ins.severity === 'alert'
									? 'text-rose-300'
									: ins.severity === 'warning'
										? 'text-amber-300'
										: 'text-emerald-300'}"
							>
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

		<!-- Filterable Recent Transactions -->
		<div class="card-surface rounded-2xl p-5 sm:p-6 space-y-4">
			<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
				<div>
					<h2 class="text-base font-semibold text-white">Recent Transactions</h2>
					<p class="text-xs text-slate-400">Latest posted ledger activity</p>
				</div>

				<div class="flex flex-wrap items-center gap-2">
					<div class="relative">
						<Search class="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
						<input
							type="text"
							bind:value={txSearch}
							placeholder="Filter merchant..."
							class="pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 w-40 sm:w-48"
						/>
					</div>

					<div class="inline-flex p-0.5 rounded-xl bg-slate-950 border border-slate-800 text-[11px]">
						{#each [['all', 'All'], ['outflow', 'Outflow'], ['inflow', 'Inflow']] as [val, label]}
							<button
								type="button"
								onclick={() => (txFilter = val as 'all' | 'inflow' | 'outflow')}
								class="px-2.5 py-1 rounded-lg font-medium transition cursor-pointer {txFilter === val
									? 'bg-emerald-500/20 text-emerald-300'
									: 'text-slate-400 hover:text-white'}"
							>
								{label}
							</button>
						{/each}
					</div>

					<a href="/transactions" class="text-xs font-medium text-emerald-400 hover:text-emerald-300 pl-1">
						View All →
					</a>
				</div>
			</div>

			{#if summary.recent_transactions.length === 0}
				<div class="py-10 text-center space-y-3">
					<p class="text-sm text-slate-400">
						Your ledger is ready. Import a Bank of Georgia PDF, upload a CSV, or add your first transaction.
					</p>
					<div class="flex items-center justify-center gap-3">
						<a href="/imports" class="px-4 py-2 rounded-xl bg-orange-500/20 border border-orange-500/35 text-xs font-semibold text-orange-200">
							Import BOG PDF
						</a>
						<button
							type="button"
							onclick={() => (quickAddOpen = true)}
							class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-slate-950 cursor-pointer"
						>
							+ Quick-Add Transaction
						</button>
					</div>
				</div>
			{:else if filteredRecentTxs.length === 0}
				<div class="py-8 text-center text-xs text-slate-500">
					No recent transactions match your filter.
				</div>
			{:else}
				<div class="divide-y divide-slate-800/70">
					{#each filteredRecentTxs as tx}
						{@const cat = tx.category_id ? categoriesMap.get(tx.category_id) : null}
						{@const acc = accountsMap.get(tx.account_id)}
						<div class="py-3 flex items-center justify-between gap-3 group">
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
									<div class="text-xs text-slate-400 flex items-center gap-1.5 flex-wrap mt-0.5">
										<span>{formatDate(tx.occurred_at)}</span>
										{#if acc}
											<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
												{acc.name}
											</span>
										{/if}
										{#if cat}
											<span
												class="px-1.5 py-0.5 rounded bg-slate-800/90 text-[10px] font-medium"
												style="color: {cat.color}"
											>
												{cat.name}
											</span>
										{/if}
									</div>
								</div>
							</div>

							<div class="flex items-center gap-3 shrink-0">
								<button
									type="button"
									onclick={() =>
										askLuna(`Analyze my spending history at "${tx.merchant_clean}" and tell me if it's trending up.`)}
									class="hidden sm:inline-flex opacity-0 group-hover:opacity-100 items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-emerald-500/15 border border-slate-800 hover:border-emerald-500/35 text-[10px] text-slate-300 hover:text-emerald-300 transition cursor-pointer"
								>
									<Sparkles class="w-3 h-3" /> Analyze
								</button>
								<div
									class="text-sm font-semibold font-mono-num {tx.direction === 'inflow'
										? 'text-emerald-400'
										: 'text-slate-100'} {privacyMode ? 'privacy-blur' : ''}"
								>
									{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- Inline Quick-Add Transaction Modal -->
<QuickAddTransactionModal
	bind:open={quickAddOpen}
	{accounts}
	{categories}
	onCreated={() => loadDashboard(months, true)}
/>
