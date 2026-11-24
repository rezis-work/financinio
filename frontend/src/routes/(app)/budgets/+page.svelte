<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type {
		BudgetOverview,
		BudgetStatus,
		Category,
		FinancialHealthProfile,
		Transaction
	} from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatMoney } from '$lib/utils/format';
	import BudgetDetailDrawer from '$lib/components/budgets/BudgetDetailDrawer.svelte';
	import {
		Plus,
		Sparkles,
		Trash2,
		Pencil,
		AlertTriangle,
		CheckCircle2,
		RefreshCw,
		X,
		ChevronLeft,
		ChevronRight,
		Eye,
		EyeOff,
		Flame,
		TrendingUp,
		Radar
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';

	const NEEDS_NAMES = new Set([
		'housing & rent',
		'groceries',
		'utilities & internet',
		'transportation & transit',
		'healthcare & pharmacy',
		'education',
		'taxes & fees'
	]);

	function currentMonthIso(): string {
		const now = new Date();
		return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
	}

	function shiftMonth(yyyyMm: string, delta: number): string {
		const [y, m] = yyyyMm.split('-').map(Number);
		const d = new Date(y, m - 1 + delta, 1);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
	}

	function formatMonthLabel(yyyyMm: string): string {
		const [y, m] = yyyyMm.split('-').map(Number);
		return new Date(y, m - 1, 1).toLocaleDateString('en-US', {
			month: 'long',
			year: 'numeric'
		});
	}

	function monthBounds(yyyyMm: string): { from: string; to: string } {
		const [yStr, mStr] = yyyyMm.split('-');
		const lastDay = new Date(Number(yStr), Number(mStr), 0).getDate();
		return {
			from: `${yStr}-${mStr}-01`,
			to: `${yStr}-${mStr}-${String(lastDay).padStart(2, '0')}`
		};
	}

	let selectedMonth = $state(currentMonthIso());
	let overview = $state<BudgetOverview | null>(null);
	let categories = $state<Category[]>([]);
	let monthTxs = $state<Transaction[]>([]);
	let health = $state<FinancialHealthProfile | null>(null);

	let loading = $state(true);
	let switchingMonth = $state(false);
	let privacyMode = $state(false);
	let error = $state<string | null>(null);
	let successMsg = $state<string | null>(null);

	// Filters & Sort
	let statusFilter = $state<'all' | 'over_budget' | 'attention' | 'on_track'>('all');
	let sortBy = $state<'urgency' | 'spend' | 'remaining' | 'name'>('urgency');

	// Drawer & Modals
	let inspectedBudgetId = $state<string | null>(null);
	let inspectedBudget = $derived(
		overview?.budgets.find((b) => b.id === inspectedBudgetId) ?? null
	);

	let showCreateModal = $state(false);
	let editingBudgetId = $state<string | null>(null);
	let formCategoryId = $state('');
	let formAmount = $state('');
	let formRollover = $state(false);
	let formThreshold = $state(80);

	let showTemplateModal = $state(false);
	let templateIncome = $state('5000.00');
	let saving = $state(false);

	let deleteTarget = $state<BudgetStatus | null>(null);
	let deleting = $state(false);

	let baseCcy = $derived(auth.user?.base_currency || 'USD');
	let expenseCategories = $derived(categories.filter((c) => c.kind === 'expense'));
	let categoriesMap = $derived(new Map(categories.map((c) => [c.id, c])));
	let isCurrentMonth = $derived(selectedMonth === currentMonthIso());

	async function loadMonthData(month: string, initial = false) {
		if (initial) loading = true;
		else switchingMonth = true;
		error = null;
		const bounds = monthBounds(month);
		try {
			const [ov, txRes, cats, hlth] = await Promise.all([
				api.getBudgets(month),
				api
					.listTransactions({
						direction: 'outflow',
						date_from: bounds.from,
						date_to: bounds.to,
						limit: 200
					})
					.catch(() => ({ items: [] as Transaction[], total: 0, limit: 200, offset: 0 })),
				initial ? api.listCategories() : Promise.resolve(categories),
				initial ? api.financialHealthScore().catch(() => null) : Promise.resolve(health)
			]);
			overview = ov;
			monthTxs = txRes.items;
			if (initial) {
				categories = cats;
				health = hlth;
				const avgInc = hlth ? Number.parseFloat(hlth.cash_flow_ratios.avg_monthly_income) : 0;
				if (avgInc >= 100) {
					templateIncome = avgInc.toFixed(2);
				}
				if (!formCategoryId) {
					const firstExp = cats.find((c) => c.kind === 'expense');
					if (firstExp) formCategoryId = firstExp.id;
				}
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load budgets';
		} finally {
			loading = false;
			switchingMonth = false;
		}
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadMonthData(selectedMonth, true);
	});

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	function goMonth(delta: number) {
		selectedMonth = shiftMonth(selectedMonth, delta);
		loadMonthData(selectedMonth, false);
	}

	function goTodayMonth() {
		selectedMonth = currentMonthIso();
		loadMonthData(selectedMonth, false);
	}

	// Master Hero Metrics
	let masterMetrics = $derived.by(() => {
		if (!overview) {
			return {
				budgeted: 0,
				spent: 0,
				remaining: 0,
				pctUsed: 0,
				daysLeft: 1,
				dailyAllowance: 0,
				projectedEom: 0,
				overCount: 0,
				attentionCount: 0,
				onTrackCount: 0,
				needsTotal: 0,
				wantsTotal: 0
			};
		}
		const budgeted = Number.parseFloat(overview.total_budgeted) || 0;
		const spent = Number.parseFloat(overview.total_spent) || 0;
		const remaining = Number.parseFloat(overview.total_remaining) || 0;
		const pctUsed = budgeted > 0 ? Math.round((spent / budgeted) * 1000) / 10 : 0;
		const elapsed = Math.max(1, overview.days_elapsed);
		const daysLeft = Math.max(1, overview.days_in_month - overview.days_elapsed + 1);
		const dailyAllowance = remaining / daysLeft;
		const projectedEom = (spent / elapsed) * overview.days_in_month;

		let overCount = 0;
		let attentionCount = 0;
		let onTrackCount = 0;
		let needsTotal = 0;
		let wantsTotal = 0;

		for (const b of overview.budgets) {
			if (b.status === 'over_budget') overCount++;
			else if (b.status === 'warning' || b.status === 'pacing_fast') attentionCount++;
			else onTrackCount++;

			const lim = Number.parseFloat(b.effective_limit) || 0;
			if (NEEDS_NAMES.has(b.category_name.toLowerCase())) needsTotal += lim;
			else wantsTotal += lim;
		}

		return {
			budgeted,
			spent,
			remaining,
			pctUsed,
			daysLeft,
			dailyAllowance,
			projectedEom,
			overCount,
			attentionCount,
			onTrackCount,
			needsTotal,
			wantsTotal
		};
	});

	// Per-card forecasting helper
	function cardForecast(b: BudgetStatus): {
		dailyAllowance: number;
		projectedEom: number;
		projectedDiff: number;
	} {
		const spent = Number.parseFloat(b.spent) || 0;
		const limit = Number.parseFloat(b.effective_limit) || 0;
		const remaining = Number.parseFloat(b.remaining) || 0;
		const elapsed = Math.max(1, overview?.days_elapsed ?? 1);
		const dim = overview?.days_in_month ?? 30;
		const daysLeft = Math.max(1, dim - elapsed + 1);
		const projectedEom = (spent / elapsed) * dim;
		return {
			dailyAllowance: remaining / daysLeft,
			projectedEom,
			projectedDiff: projectedEom - limit
		};
	}

	// Filtered & sorted budget cards
	let filteredBudgets = $derived.by(() => {
		const list = overview?.budgets ?? [];
		const filtered = list.filter((b) => {
			if (statusFilter === 'all') return true;
			if (statusFilter === 'over_budget') return b.status === 'over_budget';
			if (statusFilter === 'attention')
				return b.status === 'warning' || b.status === 'pacing_fast';
			if (statusFilter === 'on_track') return b.status === 'on_track';
			return true;
		});
		return [...filtered].sort((a, b) => {
			if (sortBy === 'urgency') return b.percent_used - a.percent_used;
			if (sortBy === 'spend')
				return (Number.parseFloat(b.spent) || 0) - (Number.parseFloat(a.spent) || 0);
			if (sortBy === 'remaining')
				return (Number.parseFloat(b.remaining) || 0) - (Number.parseFloat(a.remaining) || 0);
			return a.category_name.localeCompare(b.category_name);
		});
	});

	// 3. Unbudgeted Spending Radar
	let unbudgetedCategories = $derived.by(() => {
		const budgetedCatIds = new Set((overview?.budgets ?? []).map((b) => b.category_id));
		const totals = new Map<string, { category: Category; spent: number; count: number }>();

		for (const tx of monthTxs) {
			if (tx.is_transfer || !tx.category_id) continue;
			if (budgetedCatIds.has(tx.category_id)) continue;
			const cat = categoriesMap.get(tx.category_id);
			if (!cat || cat.kind !== 'expense') continue;
			const cur = totals.get(cat.id) ?? { category: cat, spent: 0, count: 0 };
			cur.spent += Number.parseFloat(tx.base_amount || tx.amount) || 0;
			cur.count += 1;
			totals.set(cat.id, cur);
		}

		const elapsed = Math.max(1, overview?.days_elapsed ?? 1);
		const dim = overview?.days_in_month ?? 30;
		return Array.from(totals.values())
			.sort((a, b) => b.spent - a.spent)
			.slice(0, 6)
			.map((item) => {
				const projected = (item.spent / elapsed) * dim;
				const suggested = Math.max(25, Math.ceil((Math.max(item.spent, projected) * 1.1) / 10) * 10);
				return { ...item, suggested };
			});
	});

	// 50/30/20 Live Preview Breakdown
	let templatePreview = $derived.by(() => {
		const inc = Number.parseFloat(templateIncome) || 0;
		return {
			valid: inc >= 100,
			needs: inc * 0.5,
			wants: inc * 0.3,
			savings: inc * 0.2
		};
	});

	function openCreateModal(prefillCatId?: string, prefillAmount?: number) {
		editingBudgetId = null;
		formCategoryId =
			prefillCatId ||
			expenseCategories.find((c) => !(overview?.budgets ?? []).some((b) => b.category_id === c.id))
				?.id ||
			expenseCategories[0]?.id ||
			'';
		formAmount = prefillAmount ? prefillAmount.toFixed(2) : '';
		formRollover = false;
		formThreshold = 80;
		showCreateModal = true;
	}

	function openEditModal(b: BudgetStatus) {
		editingBudgetId = b.id;
		formCategoryId = b.category_id;
		formAmount = b.amount;
		formRollover = b.rollover;
		formThreshold = b.alert_threshold_pct;
		showCreateModal = true;
	}

	async function handleSaveBudget(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		successMsg = null;
		try {
			if (editingBudgetId) {
				await api.updateBudget(editingBudgetId, {
					amount: formAmount,
					rollover: formRollover,
					alert_threshold_pct: formThreshold
				});
				successMsg = 'Budget updated successfully.';
			} else {
				await api.upsertBudget({
					category_id: formCategoryId,
					amount: formAmount,
					period: 'monthly',
					rollover: formRollover,
					alert_threshold_pct: formThreshold
				});
				successMsg = 'Monthly budget saved.';
			}
			overview = await api.getBudgets(selectedMonth);
			showCreateModal = false;
			editingBudgetId = null;
			formAmount = '';
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save budget';
		} finally {
			saving = false;
		}
	}

	async function handleApplyTemplate(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		successMsg = null;
		try {
			await api.apply503020Template(templateIncome);
			overview = await api.getBudgets(selectedMonth);
			showTemplateModal = false;
			successMsg = `Applied 50/30/20 budget template based on ${formatMoney(templateIncome, baseCcy)}/mo income.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to apply 50/30/20 template';
		} finally {
			saving = false;
		}
	}

	async function confirmDelete() {
		if (!deleteTarget || deleting) return;
		const target = deleteTarget;
		deleting = true;
		error = null;
		successMsg = null;
		try {
			await api.deleteBudget(target.id);
			if (inspectedBudgetId === target.id) inspectedBudgetId = null;
			deleteTarget = null;
			overview = await api.getBudgets(selectedMonth);
			successMsg = `Removed monthly budget for "${target.category_name}".`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete budget';
		} finally {
			deleting = false;
		}
	}

	function statusPill(status: BudgetStatus['status']): { label: string; cls: string } {
		if (status === 'over_budget') {
			return { label: 'Over Budget', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' };
		}
		if (status === 'warning') {
			return { label: 'Near Limit', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' };
		}
		if (status === 'pacing_fast') {
			return { label: 'Pacing Fast', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' };
		}
		return { label: 'On Track', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' };
	}

	function barColor(status: BudgetStatus['status'], fallback: string): string {
		if (status === 'over_budget') return '#f43f5e';
		if (status === 'warning' || status === 'pacing_fast') return '#f59e0b';
		return fallback;
	}

	const HERO_R = 44;
	const HERO_CIRC = 2 * Math.PI * HERO_R;
</script>

<div class="space-y-6">
	<!-- 1. EXECUTIVE MONTH CONTROL BAR -->
	<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">Budgets & Pacing</h1>
			<p class="text-xs sm:text-sm text-slate-400 mt-0.5">
				Real-time spending limits, end-of-month burn forecasts, rollover carry, and unbudgeted spend radar.
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<!-- Interactive Month Switcher -->
			<div class="inline-flex items-center rounded-xl bg-slate-900/90 border border-slate-800 p-1 text-xs">
				<button
					type="button"
					disabled={switchingMonth}
					onclick={() => goMonth(-1)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer disabled:opacity-40"
					aria-label="Previous month"
				>
					<ChevronLeft class="w-4 h-4" />
				</button>
				<span class="px-2.5 font-semibold text-white min-w-[116px] text-center">
					{formatMonthLabel(selectedMonth)}
				</span>
				<button
					type="button"
					disabled={switchingMonth}
					onclick={() => goMonth(1)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer disabled:opacity-40"
					aria-label="Next month"
				>
					<ChevronRight class="w-4 h-4" />
				</button>
				{#if !isCurrentMonth}
					<button
						type="button"
						onclick={goTodayMonth}
						class="ml-1 px-2 py-1 rounded-lg bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 font-semibold text-[11px] cursor-pointer"
					>
						Today
					</button>
				{/if}
			</div>

			<!-- Privacy Toggle -->
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
				{:else}
					<Eye class="w-3.5 h-3.5" />
				{/if}
			</button>

			<!-- Rebalance with Luna -->
			<button
				type="button"
				onclick={() =>
					goto(
						`/advisor?q=${encodeURIComponent(
							`Audit my ${selectedMonth} budgets, identify any over-budget or fast-pacing categories, and suggest a realistic rebalance plan.`
						)}`
					)}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-emerald-300 transition cursor-pointer"
			>
				<Sparkles class="w-3.5 h-3.5" />
				<span class="hidden sm:inline">Rebalance</span>
			</button>

			<!-- 50/30/20 Setup -->
			<button
				type="button"
				onclick={() => (showTemplateModal = true)}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 text-xs font-semibold text-cyan-200 transition cursor-pointer"
			>
				50/30/20
			</button>

			<!-- Set Budget -->
			<button
				type="button"
				onclick={() => openCreateModal()}
				class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs transition cursor-pointer shadow-sm"
			>
				<Plus class="w-4 h-4" />
				<span>Set Budget</span>
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
			<span>{error}</span>
			<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}
	{#if successMsg}
		<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3">
			<span class="flex items-center gap-2">
				<CheckCircle2 class="w-4 h-4 shrink-0" />
				{successMsg}
			</span>
			<button type="button" onclick={() => (successMsg = null)} class="text-emerald-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	{#if loading}
		<div class="card-surface rounded-2xl h-44 animate-pulse"></div>
		<div class="grid md:grid-cols-2 gap-4">
			{#each Array(4) as _}
				<div class="card-surface rounded-2xl h-36 animate-pulse"></div>
			{/each}
		</div>
	{:else if overview}
		<!-- MASTER BUDGET PACING HERO CARD -->
		{@const heroDashOffset = HERO_CIRC * (1 - Math.min(100, masterMetrics.pctUsed) / 100)}
		{@const heroStroke =
			masterMetrics.pctUsed > 100
				? '#f43f5e'
				: masterMetrics.pctUsed >= 85
					? '#f59e0b'
					: '#34d399'}
		<div class="card-surface rounded-2xl p-5 sm:p-6 border-emerald-500/20 space-y-5">
			<div class="grid lg:grid-cols-12 gap-6 items-center">
				<!-- Left: Overall Ring + Spent vs Budgeted -->
				<div class="lg:col-span-5 flex items-center gap-5">
					<div class="relative w-28 h-28 shrink-0">
						<svg viewBox="0 0 110 110" class="w-full h-full -rotate-90" role="img" aria-label="Overall budget utilization {masterMetrics.pctUsed}%">
							<circle
								cx="55"
								cy="55"
								r={HERO_R}
								fill="none"
								stroke="rgba(148, 163, 184, 0.14)"
								stroke-width="10"
							/>
							<circle
								cx="55"
								cy="55"
								r={HERO_R}
								fill="none"
								stroke={heroStroke}
								stroke-width="10"
								stroke-linecap="round"
								stroke-dasharray={HERO_CIRC}
								stroke-dashoffset={heroDashOffset}
								class="transition-all duration-700"
							/>
						</svg>
						<div class="absolute inset-0 flex flex-col items-center justify-center">
							<span class="text-xl font-bold text-white font-mono-num">
								{Math.round(masterMetrics.pctUsed)}%
							</span>
							<span class="text-[10px] text-slate-400">used</span>
						</div>
					</div>

					<div class="min-w-0 space-y-1">
						<div class="text-xs text-slate-400">
							Remaining Safe-to-Spend ({overview.month})
						</div>
						<div
							class="text-2xl sm:text-3xl font-bold font-mono-num {masterMetrics.remaining < 0
								? 'text-rose-400'
								: 'text-emerald-400'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{formatMoney(masterMetrics.remaining, baseCcy)}
						</div>
						<div class="text-xs text-slate-400 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
							Spent <span class="text-white font-semibold">{formatMoney(masterMetrics.spent, baseCcy)}</span>
							of {formatMoney(masterMetrics.budgeted, baseCcy)}
						</div>
					</div>
				</div>

				<!-- Right: Forecast KPIs + Health Count Pills -->
				<div class="lg:col-span-7 grid sm:grid-cols-3 gap-4 lg:border-l lg:border-slate-800/80 lg:pl-6">
					<div class="space-y-1">
						<div class="text-[11px] text-slate-400 flex items-center gap-1.5">
							<Flame class="w-3.5 h-3.5 text-emerald-400" /> Daily Allowance
						</div>
						<div
							class="text-lg font-bold font-mono-num {masterMetrics.dailyAllowance >= 0
								? 'text-white'
								: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{formatMoney(Math.max(0, masterMetrics.dailyAllowance), baseCcy)}/day
						</div>
						<div class="text-[11px] text-slate-500">
							{masterMetrics.daysLeft} {masterMetrics.daysLeft === 1 ? 'day' : 'days'} left in month
						</div>
					</div>

					<div class="space-y-1">
						<div class="text-[11px] text-slate-400 flex items-center gap-1.5">
							<TrendingUp class="w-3.5 h-3.5 text-cyan-400" /> Projected EOM
						</div>
						<div
							class="text-lg font-bold font-mono-num {masterMetrics.projectedEom > masterMetrics.budgeted && masterMetrics.budgeted > 0
								? 'text-rose-400'
								: 'text-cyan-300'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{formatMoney(masterMetrics.projectedEom, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-500">
							Day {overview.days_elapsed} of {overview.days_in_month} ({overview.pace_pct}% pace)
						</div>
					</div>

					<div class="space-y-1.5">
						<div class="text-[11px] text-slate-400">Category Health</div>
						<div class="flex flex-wrap gap-1.5">
							{#if masterMetrics.overCount > 0}
								<button
									type="button"
									onclick={() =>
										(statusFilter = statusFilter === 'over_budget' ? 'all' : 'over_budget')}
									class="px-2 py-0.5 rounded-full bg-rose-500/15 border border-rose-500/35 text-rose-300 text-[10px] font-semibold cursor-pointer"
								>
									{masterMetrics.overCount} Over
								</button>
							{/if}
							{#if masterMetrics.attentionCount > 0}
								<button
									type="button"
									onclick={() =>
										(statusFilter = statusFilter === 'attention' ? 'all' : 'attention')}
									class="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/35 text-amber-300 text-[10px] font-semibold cursor-pointer"
								>
									{masterMetrics.attentionCount} Fast
								</button>
							{/if}
							<button
								type="button"
								onclick={() => (statusFilter = statusFilter === 'on_track' ? 'all' : 'on_track')}
								class="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/35 text-emerald-300 text-[10px] font-semibold cursor-pointer"
							>
								{masterMetrics.onTrackCount} On Track
							</button>
						</div>
					</div>
				</div>
			</div>

			<!-- Master Pacing Bar + Needs vs. Wants Split -->
			{#if overview.budgets.length > 0}
				{@const needsShare =
					masterMetrics.budgeted > 0
						? Math.round((masterMetrics.needsTotal / masterMetrics.budgeted) * 100)
						: 0}
				{@const wantsShare = Math.max(0, 100 - needsShare)}
				<div class="grid lg:grid-cols-2 gap-4 pt-4 border-t border-slate-800/80">
					<div class="space-y-1.5">
						<div class="flex items-center justify-between text-[11px] text-slate-400">
							<span>Overall Month Pace</span>
							<span class="font-mono-num">
								Spent {masterMetrics.pctUsed}% · Elapsed {overview.pace_pct}%
							</span>
						</div>
						<div class="relative h-2.5 rounded-full bg-slate-800 overflow-visible">
							<div
								class="h-full rounded-full transition-all"
								style="width: {Math.min(masterMetrics.pctUsed, 100)}%; background-color: {heroStroke}"
							></div>
							<div
								title="Today's month pace ({overview.pace_pct}%)"
								class="absolute -top-1 w-0.5 h-4.5 bg-white/90 rounded-full"
								style="left: {Math.min(overview.pace_pct, 100)}%"
							></div>
						</div>
					</div>

					<div class="space-y-1.5">
						<div class="flex items-center justify-between text-[11px] text-slate-400">
							<span>Budget Mix (Needs vs. Wants)</span>
							<span class="font-mono-num">
								<span class="text-emerald-300">{needsShare}% Needs</span> ·
								<span class="text-cyan-300">{wantsShare}% Wants</span>
							</span>
						</div>
						<div class="h-2.5 rounded-full bg-slate-800 overflow-hidden flex gap-0.5">
							<div
								title="Needs: {formatMoney(masterMetrics.needsTotal, baseCcy)}"
								class="h-full bg-emerald-400/90 transition-all"
								style="width: {needsShare}%"
							></div>
							<div
								title="Wants: {formatMoney(masterMetrics.wantsTotal, baseCcy)}"
								class="h-full bg-cyan-400/90 transition-all"
								style="width: {wantsShare}%"
							></div>
						</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- 2. FILTER & SORT STRIP + BUDGET CARDS -->
		{#if overview.budgets.length === 0}
			<div class="card-surface rounded-2xl p-12 text-center space-y-3">
				<h2 class="text-lg font-semibold text-white">No budgets configured for {formatMonthLabel(selectedMonth)}</h2>
				<p class="text-sm text-slate-400 max-w-md mx-auto">
					Set individual category limits or auto-generate a balanced 50/30/20 plan from your monthly income in one click.
				</p>
				<div class="flex items-center justify-center gap-3 pt-2">
					<button
						type="button"
						onclick={() => (showTemplateModal = true)}
						class="px-4 py-2 rounded-xl bg-cyan-500/20 border border-cyan-500/35 text-xs font-semibold text-cyan-200 cursor-pointer"
					>
						Apply 50/30/20 Template
					</button>
					<button
						type="button"
						onclick={() => openCreateModal()}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-slate-950 cursor-pointer"
					>
						+ Create Custom Budget
					</button>
				</div>
			</div>
		{:else}
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div class="inline-flex flex-wrap p-1 rounded-xl bg-slate-900/90 border border-slate-800 text-xs gap-0.5">
					{#each [
						['all', `All (${overview.budgets.length})`],
						['over_budget', `Over Budget (${masterMetrics.overCount})`],
						['attention', `Needs Attention (${masterMetrics.attentionCount})`],
						['on_track', `On Track (${masterMetrics.onTrackCount})`]
					] as [val, label]}
						<button
							type="button"
							onclick={() =>
								(statusFilter = val as 'all' | 'over_budget' | 'attention' | 'on_track')}
							class="px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer {statusFilter === val
								? 'bg-emerald-500/20 text-emerald-300'
								: 'text-slate-400 hover:text-white'}"
						>
							{label}
						</button>
					{/each}
				</div>

				<div class="flex items-center gap-2 text-xs">
					<span class="text-slate-500">Sort:</span>
					<select
						bind:value={sortBy}
						class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
					>
						<option value="urgency">Urgency (% Used)</option>
						<option value="spend">Highest Spend</option>
						<option value="remaining">Most Remaining</option>
						<option value="name">Category A–Z</option>
					</select>
				</div>
			</div>

			{#if filteredBudgets.length === 0}
				<div class="card-surface rounded-2xl p-8 text-center text-xs text-slate-400">
					No budgets match this status filter.
				</div>
			{:else}
				<div class="grid md:grid-cols-2 gap-4">
					{#each filteredBudgets as b}
						{@const pill = statusPill(b.status)}
						{@const fc = cardForecast(b)}
						{@const remNum = Number.parseFloat(b.remaining) || 0}
						<div
							role="button"
							tabindex="0"
							onclick={() => (inspectedBudgetId = b.id)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									inspectedBudgetId = b.id;
								}
							}}
							class="card-surface card-surface-hover rounded-2xl p-5 space-y-4 text-left cursor-pointer group outline-none focus:ring-2 focus:ring-emerald-500/50"
						>
							<div class="flex items-start justify-between gap-3">
								<div class="flex items-center gap-2.5 min-w-0">
									<span
										class="w-3 h-3 rounded-full shrink-0"
										style="background-color: {b.category_color}"
									></span>
									<div class="min-w-0">
										<div class="font-semibold text-white flex items-center gap-2 flex-wrap">
											<span class="truncate">{b.category_name}</span>
											{#if b.rollover}
												<span class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300">
													<RefreshCw class="w-2.5 h-2.5" /> Rollover
												</span>
											{/if}
										</div>
										<div class="text-xs text-slate-400 font-mono-num mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
											{formatMoney(b.spent, baseCcy)} of {formatMoney(b.effective_limit, baseCcy)}
											{#if Number.parseFloat(b.rollover_carry) > 0}
												<span class="text-cyan-400">(+{formatMoney(b.rollover_carry, baseCcy)} carried)</span>
											{/if}
										</div>
									</div>
								</div>

								<div class="flex items-center gap-1 shrink-0">
									<span
										class="inline-flex items-center gap-1 text-[10px] font-semibold px-2.5 py-0.5 rounded-full border {pill.cls}"
									>
										{#if b.status === 'on_track'}
											<CheckCircle2 class="w-3 h-3" />
										{:else}
											<AlertTriangle class="w-3 h-3" />
										{/if}
										{pill.label}
									</span>
									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											openEditModal(b);
										}}
										class="p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-slate-800 cursor-pointer"
										title="Edit budget"
									>
										<Pencil class="w-3.5 h-3.5" />
									</button>
									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											deleteTarget = b;
										}}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										title="Remove budget"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</div>
							</div>

							<!-- Progress bar with vertical month-pace marker -->
							<div class="space-y-1.5">
								<div class="relative h-2.5 rounded-full bg-slate-800 overflow-visible">
									<div
										class="h-full rounded-full transition-all"
										style="width: {Math.min(b.percent_used, 100)}%; background-color: {barColor(b.status, b.category_color)}"
									></div>
									<div
										title="Today's month pace: {b.pace_pct}%"
										class="absolute -top-1 w-0.5 h-4.5 bg-white/85 rounded-full"
										style="left: {Math.min(b.pace_pct, 100)}%"
									></div>
								</div>

								<div class="flex items-center justify-between text-[11px] font-mono-num gap-2">
									<span class="text-slate-400">
										{b.percent_used}% used · pace {b.pace_pct}%
									</span>
									<span
										class="{remNum < 0 ? 'text-rose-400 font-semibold' : 'text-emerald-400'} {privacyMode ? 'privacy-blur' : ''}"
									>
										{remNum < 0
											? `${formatMoney(Math.abs(remNum), baseCcy)} over`
											: `${formatMoney(b.remaining, baseCcy)} left`}
									</span>
								</div>
							</div>

							<!-- Smart Forecast Footer -->
							<div class="pt-2.5 border-t border-slate-800/70 flex items-center justify-between text-[11px]">
								{#if fc.projectedDiff > 1 && b.status !== 'on_track'}
									<span class="text-amber-300 flex items-center gap-1.5 font-mono-num">
										<TrendingUp class="w-3.5 h-3.5 shrink-0" />
										<span class={privacyMode ? 'privacy-blur' : ''}>
											Projected EOM: {formatMoney(fc.projectedEom, baseCcy)} (+{formatMoney(fc.projectedDiff, baseCcy)} over)
										</span>
									</span>
								{:else}
									<span class="text-slate-400 flex items-center gap-1.5 font-mono-num">
										<Flame class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
										Daily allowance:
										<span class="text-emerald-300 font-semibold {privacyMode ? 'privacy-blur' : ''}">
											{formatMoney(Math.max(0, fc.dailyAllowance), baseCcy)}/day
										</span>
									</span>
								{/if}
								<span class="text-[10px] text-slate-500 group-hover:text-emerald-400 transition">
									Inspect →
								</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		{/if}

		<!-- 3. UNBUDGETED SPENDING RADAR -->
		{#if unbudgetedCategories.length > 0}
			<div class="card-surface rounded-2xl p-5 border-amber-500/25 space-y-3.5">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2">
						<Radar class="w-4 h-4 text-amber-400" />
						<div>
							<h2 class="text-sm font-semibold text-white">Unbudgeted Spending Radar</h2>
							<p class="text-[11px] text-slate-400">
								Categories with real {formatMonthLabel(selectedMonth)} expenses but no monthly limit set yet.
							</p>
						</div>
					</div>
					<span class="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[10px] font-mono-num font-semibold">
						{unbudgetedCategories.length} found
					</span>
				</div>

				<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
					{#each unbudgetedCategories as item}
						<div class="p-3.5 rounded-xl bg-slate-950/75 border border-slate-800/90 flex items-center justify-between gap-3">
							<div class="min-w-0">
								<div class="flex items-center gap-2 text-xs font-semibold text-white">
									<span
										class="w-2.5 h-2.5 rounded-full shrink-0"
										style="background-color: {item.category.color}"
									></span>
									<span class="truncate">{item.category.name}</span>
								</div>
								<div class="text-[11px] text-slate-400 font-mono-num mt-1 {privacyMode ? 'privacy-blur' : ''}">
									{formatMoney(item.spent, baseCcy)} · {item.count} {item.count === 1 ? 'tx' : 'txs'}
								</div>
							</div>
							<button
								type="button"
								onclick={() => openCreateModal(item.category.id, item.suggested)}
								class="shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-emerald-300 text-[11px] font-semibold cursor-pointer transition"
							>
								<Plus class="w-3 h-3" /> Cap
							</button>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>

<!-- 4. BUDGET CATEGORY INSPECTOR SLIDE-OVER DRAWER -->
<BudgetDetailDrawer
	budget={inspectedBudget}
	{overview}
	currency={baseCcy}
	{privacyMode}
	onClose={() => (inspectedBudgetId = null)}
	onUpdated={async () => {
		overview = await api.getBudgets(selectedMonth);
		successMsg = 'Budget updated.';
	}}
	onRequestDelete={(b) => (deleteTarget = b)}
/>

<!-- CREATE / EDIT BUDGET MODAL -->
{#if showCreateModal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-slate-700/80">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">
					{editingBudgetId ? 'Edit Category Budget' : 'Set Category Budget'}
				</h2>
				<button
					type="button"
					onclick={() => (showCreateModal = false)}
					class="text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleSaveBudget} class="space-y-4">
				<div>
					<label for="b-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
					<select
						id="b-cat"
						required
						disabled={editingBudgetId !== null}
						bind:value={formCategoryId}
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white disabled:opacity-60"
					>
						{#each expenseCategories as cat}
							<option value={cat.id}>{cat.name}</option>
						{/each}
					</select>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="b-amt" class="block text-xs font-medium text-slate-300 mb-1">
							Monthly Limit ({baseCcy})
						</label>
						<input
							id="b-amt"
							type="number"
							step="0.01"
							min="1"
							required
							bind:value={formAmount}
							placeholder="500.00"
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
						/>
					</div>
					<div>
						<label for="b-thresh" class="block text-xs font-medium text-slate-300 mb-1">
							Warning At (%)
						</label>
						<input
							id="b-thresh"
							type="number"
							min={10}
							max={100}
							bind:value={formThreshold}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
						/>
					</div>
				</div>

				<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
					<input type="checkbox" bind:checked={formRollover} class="rounded border-slate-700" />
					Rollover unused balance from previous month into next month
				</label>

				<div class="flex justify-end gap-2.5 pt-2">
					<button
						type="button"
						onclick={() => (showCreateModal = false)}
						class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{saving ? 'Saving...' : editingBudgetId ? 'Save Changes' : 'Save Budget'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- 5. SMARTER INCOME-AWARE 50/30/20 TEMPLATE MODAL -->
{#if showTemplateModal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-cyan-500/30">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<Sparkles class="w-4 h-4 text-cyan-400" />
					<h2 class="text-base font-semibold text-white">50/30/20 Smart Budget Setup</h2>
				</div>
				<button
					type="button"
					onclick={() => (showTemplateModal = false)}
					class="text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<p class="text-xs text-slate-400 leading-relaxed">
				Auto-generates balanced category limits from your take-home monthly income.
				{#if health && Number.parseFloat(health.cash_flow_ratios.avg_monthly_income) > 0}
					Pre-filled using your real 90-day average income.
				{/if}
			</p>

			<form onsubmit={handleApplyTemplate} class="space-y-4">
				<div>
					<label for="tpl-inc" class="block text-xs font-medium text-slate-300 mb-1">
						Monthly Net Income ({baseCcy})
					</label>
					<input
						id="tpl-inc"
						type="number"
						step="0.01"
						min="100"
						required
						bind:value={templateIncome}
						class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-base text-white font-mono-num font-semibold focus:outline-none focus:border-cyan-500"
					/>
				</div>

				<!-- Live 50/30/20 Breakdown Preview -->
				{#if templatePreview.valid}
					<div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
						<div class="h-2.5 rounded-full overflow-hidden flex gap-0.5">
							<div class="bg-emerald-400 h-full" style="width: 50%"></div>
							<div class="bg-cyan-400 h-full" style="width: 30%"></div>
							<div class="bg-violet-400 h-full" style="width: 20%"></div>
						</div>
						<div class="grid grid-cols-3 gap-2 text-xs">
							<div>
								<div class="text-[10px] text-emerald-300 font-semibold">50% Needs</div>
								<div class="font-mono-num font-bold text-white mt-0.5">
									{formatMoney(templatePreview.needs, baseCcy)}
								</div>
							</div>
							<div>
								<div class="text-[10px] text-cyan-300 font-semibold">30% Wants</div>
								<div class="font-mono-num font-bold text-white mt-0.5">
									{formatMoney(templatePreview.wants, baseCcy)}
								</div>
							</div>
							<div>
								<div class="text-[10px] text-violet-300 font-semibold">20% Savings</div>
								<div class="font-mono-num font-bold text-white mt-0.5">
									{formatMoney(templatePreview.savings, baseCcy)}
								</div>
							</div>
						</div>
					</div>
				{/if}

				<div class="flex justify-end gap-2.5">
					<button
						type="button"
						onclick={() => (showTemplateModal = false)}
						class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving || !templatePreview.valid}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{saving ? 'Applying...' : 'Generate Budgets'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- SAFE DELETE MODAL -->
{#if deleteTarget}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-sm p-6 space-y-4 border border-rose-500/35">
			<div class="flex items-start gap-3">
				<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
					<AlertTriangle class="w-5 h-5" />
				</div>
				<div>
					<h2 class="text-base font-semibold text-white">Remove "{deleteTarget.category_name}" Budget?</h2>
					<p class="text-xs text-slate-400 mt-0.5">
						This removes the {formatMoney(deleteTarget.amount, baseCcy)}/mo limit. Your existing transactions will not be deleted.
					</p>
				</div>
			</div>
			<div class="flex items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={deleting}
					onclick={() => (deleteTarget = null)}
					class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={deleting}
					onclick={confirmDelete}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Trash2 class="w-3.5 h-3.5" />
					{deleting ? 'Removing...' : 'Remove Budget'}
				</button>
			</div>
		</div>
	</div>
{/if}
