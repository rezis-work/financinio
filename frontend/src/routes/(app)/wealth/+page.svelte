<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type {
		DebtInput,
		DebtPayoffComparison,
		FinancialGoal,
		FinancialHealthProfile,
		GoalType,
		NetWorthOverview,
		WhatIfResponse
	} from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import LineChart from '$lib/components/LineChart.svelte';
	import GoalContributeModal from '$lib/components/wealth/GoalContributeModal.svelte';
	import GoalDetailDrawer from '$lib/components/wealth/GoalDetailDrawer.svelte';
	import FireCalculator from '$lib/components/wealth/FireCalculator.svelte';
	import {
		Target,
		TrendingUp,
		Calculator,
		Camera,
		Plus,
		Trash2,
		CheckCircle2,
		X,
		Sparkles,
		Eye,
		EyeOff,
		Shield,
		PiggyBank,
		CreditCard,
		ShoppingBag,
		Flag,
		AlertTriangle,
		Check,
		Download
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';
	const GOAL_COLORS = ['#10b981', '#06b6d4', '#6366f1', '#8b5cf6', '#f97316', '#ec4899', '#eab308', '#14b8a6'];

	let activeTab = $state<'net_worth' | 'goals' | 'simulators'>('net_worth');
	let netWorth = $state<NetWorthOverview | null>(null);
	let goals = $state<FinancialGoal[]>([]);
	let health = $state<FinancialHealthProfile | null>(null);

	let loading = $state(true);
	let privacyMode = $state(false);
	let error = $state<string | null>(null);
	let statusMsg = $state<string | null>(null);
	let baseCcy = $derived(auth.user?.base_currency || 'USD');

	// Net Worth snapshot state
	let capturingSnapshot = $state(false);

	// Goal Create Modal
	let showGoalModal = $state(false);
	let goalName = $state('');
	let goalType = $state<GoalType>('emergency_fund');
	let goalTarget = $state('10000.00');
	let goalCurrent = $state('0.00');
	let goalMonthly = $state('500.00');
	let goalTargetDate = $state('');
	let goalColor = $state('#10b981');
	let savingGoal = $state(false);

	// Goal Contribute, Inspector Drawer & Delete Modal
	let contributeModalOpen = $state(false);
	let contributeGoal = $state<FinancialGoal | null>(null);
	let inspectedGoalId = $state<string | null>(null);
	let inspectedGoal = $derived(goals.find((g) => g.id === inspectedGoalId) ?? null);
	let deleteGoalTarget = $state<FinancialGoal | null>(null);
	let deletingGoal = $state(false);

	// Debt Payoff Simulator state
	let debts = $state<DebtInput[]>([
		{ name: 'Credit Card', balance: '4500', apr: '22.9', min_payment: '135' },
		{ name: 'Car Loan', balance: '9200', apr: '6.5', min_payment: '260' }
	]);
	let extraPayment = $state('250');
	let debtResult = $state<DebtPayoffComparison | null>(null);
	let runningDebtSim = $state(false);

	// What-If Simulator state
	let wiStarting = $state('5000');
	let wiIncome = $state('5500');
	let wiExpenses = $state('3800');
	let wiIncomeDelta = $state('0');
	let wiExpenseDelta = $state('-300');
	let wiOneTime = $state('0');
	let wiReturnPct = $state(7.0);
	let wiHorizon = $state(24);
	let whatIfResult = $state<WhatIfResponse | null>(null);
	let runningWhatIf = $state(false);

	async function loadAll(silent = false) {
		if (!silent) loading = true;
		error = null;
		try {
			const [nw, gls, dash, hlth] = await Promise.all([
				api.getNetWorth(),
				api.listGoals(),
				api.dashboardSummary(1).catch(() => null),
				api.financialHealthScore().catch(() => null)
			]);
			netWorth = nw;
			goals = gls;
			health = hlth;
			if (!silent) {
				if (Number.parseFloat(nw.current_assets) > 0) wiStarting = nw.current_assets;
				const avgInc = hlth ? Number.parseFloat(hlth.cash_flow_ratios.avg_monthly_income) : 0;
				const avgExp = hlth ? Number.parseFloat(hlth.cash_flow_ratios.avg_monthly_expenses) : 0;
				if (avgInc > 0) wiIncome = avgInc.toFixed(2);
				else if (dash && Number.parseFloat(dash.period_income) > 0) wiIncome = dash.period_income;
				if (avgExp > 0) wiExpenses = avgExp.toFixed(2);
				else if (dash && Number.parseFloat(dash.period_expenses) > 0) wiExpenses = dash.period_expenses;
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load wealth data';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadAll();
	});

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	// 1. Net Worth Cockpit Metrics & Next Milestone
	let nwStats = $derived.by(() => {
		if (!netWorth) {
			return {
				nw: 0,
				assets: 0,
				liabilities: 0,
				liquid: 0,
				invested: 0,
				debtToAssetPct: 0,
				liquidPct: 0,
				investedPct: 0,
				debtPct: 0,
				nextMilestone: 10000,
				milestonePct: 0,
				milestoneGap: 10000
			};
		}
		const nw = Number.parseFloat(netWorth.current_net_worth) || 0;
		const assets = Number.parseFloat(netWorth.current_assets) || 0;
		const liabilities = Number.parseFloat(netWorth.current_liabilities) || 0;

		let liquid = 0;
		let invested = 0;
		for (const acc of netWorth.accounts) {
			const b = Number.parseFloat(acc.balance) || 0;
			if (b <= 0) continue;
			if (acc.type === 'investment') invested += b;
			else liquid += b;
		}
		const gross = liquid + invested + liabilities;
		const liquidPct = gross > 0 ? Math.round((liquid / gross) * 100) : 0;
		const investedPct = gross > 0 ? Math.round((invested / gross) * 100) : 0;
		const debtPct = gross > 0 ? Math.max(0, 100 - liquidPct - investedPct) : 0;
		const debtToAssetPct = assets > 0 ? Math.round((liabilities / assets) * 1000) / 10 : 0;

		const milestones = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000, 2500000];
		const nextMilestone = milestones.find((m) => m > Math.max(0, nw)) ?? Math.ceil(nw * 1.5);
		const milestonePct =
			nw > 0 ? Math.min(100, Math.round((nw / nextMilestone) * 1000) / 10) : 0;
		const milestoneGap = Math.max(0, nextMilestone - nw);

		return {
			nw,
			assets,
			liabilities,
			liquid,
			invested,
			debtToAssetPct,
			liquidPct,
			investedPct,
			debtPct,
			nextMilestone,
			milestonePct,
			milestoneGap
		};
	});

	// 2. Goals Portfolio Summary Bar
	let goalsSummary = $derived.by(() => {
		let totalSaved = 0;
		let totalTarget = 0;
		let totalMonthly = 0;
		let completedCount = 0;
		for (const g of goals) {
			totalSaved += Number.parseFloat(g.current_amount) || 0;
			totalTarget += Number.parseFloat(g.target_amount) || 0;
			if (g.is_completed) completedCount++;
			else totalMonthly += Number.parseFloat(g.monthly_contribution) || 0;
		}
		const realSurplus = health ? Number.parseFloat(health.cash_flow_ratios.avg_monthly_surplus) || 0 : 0;
		const unallocated = realSurplus - totalMonthly;
		return {
			totalSaved,
			totalTarget,
			remaining: Math.max(0, totalTarget - totalSaved),
			totalMonthly,
			completedCount,
			realSurplus,
			unallocated
		};
	});

	function goalPaceStatus(g: FinancialGoal): { label: string; cls: string } | null {
		if (g.is_completed) return null;
		const req = g.required_monthly ? Number.parseFloat(g.required_monthly) : null;
		const planned = Number.parseFloat(g.monthly_contribution) || 0;
		if (req !== null && req > 0) {
			if (planned >= req) {
				return { label: 'On Track', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' };
			}
			return { label: 'Behind Pace', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' };
		}
		return null;
	}

	// Smart Goal Presets (auto-calculates 6-month emergency fund from real monthly expenses!)
	let goalPresets = $derived.by(() => {
		const avgExp = health ? Number.parseFloat(health.cash_flow_ratios.avg_monthly_expenses) || 0 : 0;
		const efTarget = avgExp > 0 ? Math.ceil((avgExp * 6) / 100) * 100 : 10000;
		return [
			{ label: '6-Mo Emergency Fund', name: '6-Month Emergency Fund', type: 'emergency_fund' as GoalType, target: efTarget.toFixed(2), monthly: Math.max(100, Math.round(efTarget / 18)).toFixed(2), color: '#10b981' },
			{ label: 'Travel Fund', name: 'Dream Vacation', type: 'purchase' as GoalType, target: '3000.00', monthly: '250.00', color: '#06b6d4' },
			{ label: 'Home Down Payment', name: 'Home Down Payment', type: 'savings' as GoalType, target: '50000.00', monthly: '1000.00', color: '#6366f1' },
			{ label: 'Debt-Free Sprint', name: 'Zero Credit Card Debt', type: 'debt_payoff' as GoalType, target: '5000.00', monthly: '400.00', color: '#f97316' },
			{ label: 'Investment Portfolio', name: 'Index Fund Milestone', type: 'investment' as GoalType, target: '25000.00', monthly: '500.00', color: '#8b5cf6' }
		];
	});

	function applyGoalPreset(p: (typeof goalPresets)[number]) {
		goalName = p.name;
		goalType = p.type;
		goalTarget = p.target;
		goalMonthly = p.monthly;
		goalColor = p.color;
	}

	// Load Real Debt Accounts into Debt Payoff Simulator
	let realDebtAccounts = $derived(
		(netWorth?.accounts ?? []).filter(
			(a) => a.classification === 'liability' && Math.abs(Number.parseFloat(a.balance) || 0) > 0
		)
	);

	function loadRealDebtsIntoSim() {
		if (realDebtAccounts.length === 0) return;
		debts = realDebtAccounts.map((a) => {
			const bal = Math.abs(Number.parseFloat(a.balance) || 0);
			const defaultApr = a.type === 'credit' ? '22.0' : '8.5';
			const defaultMin = Math.max(25, Math.round(bal * 0.03)).toFixed(0);
			return {
				name: a.name,
				balance: bal.toFixed(2),
				apr: defaultApr,
				min_payment: defaultMin
			};
		});
		debtResult = null;
		statusMsg = `Loaded ${debts.length} real debt ${debts.length === 1 ? 'account' : 'accounts'} from your ledger — adjust APRs and click Compare.`;
	}

	// 1-Click What-If Scenario Presets
	function applyWhatIfPreset(kind: 'cut' | 'raise' | 'purchase' | 'invest' | 'sabbatical') {
		if (kind === 'cut') {
			wiIncomeDelta = '0';
			wiExpenseDelta = '-300';
			wiOneTime = '0';
			wiReturnPct = 7.0;
			wiHorizon = 36;
		} else if (kind === 'raise') {
			const inc = Number.parseFloat(wiIncome) || 4000;
			wiIncomeDelta = Math.round(inc * 0.15).toString();
			wiExpenseDelta = '0';
			wiOneTime = '0';
			wiReturnPct = 7.0;
			wiHorizon = 24;
		} else if (kind === 'purchase') {
			wiIncomeDelta = '0';
			wiExpenseDelta = '0';
			wiOneTime = '-3000';
			wiReturnPct = 5.0;
			wiHorizon = 24;
		} else if (kind === 'invest') {
			wiIncomeDelta = '0';
			wiExpenseDelta = '-200';
			wiOneTime = '0';
			wiReturnPct = 8.0;
			wiHorizon = 60;
		} else {
			const inc = Number.parseFloat(wiIncome) || 4000;
			wiIncomeDelta = (-Math.round(inc * 0.6)).toString();
			wiExpenseDelta = '-400';
			wiOneTime = '0';
			wiReturnPct = 4.0;
			wiHorizon = 12;
		}
		runWhatIfSim();
	}

	async function handleSnapshot() {
		capturingSnapshot = true;
		error = null;
		try {
			await api.captureNetWorthSnapshot();
			netWorth = await api.getNetWorth();
			statusMsg = 'Net worth snapshot captured and saved to history.';
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to capture snapshot';
		} finally {
			capturingSnapshot = false;
		}
	}

	async function handleCreateGoal(e: SubmitEvent) {
		e.preventDefault();
		savingGoal = true;
		error = null;
		try {
			await api.createGoal({
				name: goalName.trim(),
				goal_type: goalType,
				target_amount: goalTarget,
				current_amount: goalCurrent || '0.00',
				monthly_contribution: goalMonthly || '0.00',
				target_date: goalTargetDate || null,
				color: goalColor
			});
			showGoalModal = false;
			goalName = '';
			goals = await api.listGoals();
			statusMsg = 'Financial goal created.';
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not create goal';
		} finally {
			savingGoal = false;
		}
	}

	async function confirmDeleteGoal() {
		if (!deleteGoalTarget || deletingGoal) return;
		const target = deleteGoalTarget;
		deletingGoal = true;
		error = null;
		try {
			await api.deleteGoal(target.id);
			if (inspectedGoalId === target.id) inspectedGoalId = null;
			deleteGoalTarget = null;
			goals = goals.filter((g) => g.id !== target.id);
			statusMsg = `Deleted goal "${target.name}".`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete goal';
		} finally {
			deletingGoal = false;
		}
	}

	async function runDebtSim() {
		runningDebtSim = true;
		error = null;
		try {
			debtResult = await api.simulateDebtPayoff(debts, extraPayment || '0');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Debt simulation failed';
		} finally {
			runningDebtSim = false;
		}
	}

	async function runWhatIfSim() {
		runningWhatIf = true;
		error = null;
		try {
			whatIfResult = await api.simulateWhatIf({
				starting_savings: wiStarting || '0',
				monthly_income: wiIncome || '0',
				monthly_expenses: wiExpenses || '0',
				income_delta_monthly: wiIncomeDelta || '0',
				expense_delta_monthly: wiExpenseDelta || '0',
				one_time_impact: wiOneTime || '0',
				annual_return_pct: wiReturnPct.toFixed(1),
				horizon_months: wiHorizon
			});
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'What-If simulation failed';
		} finally {
			runningWhatIf = false;
		}
	}

	function addDebtRow() {
		debts = [...debts, { name: 'New Debt', balance: '2000', apr: '15.0', min_payment: '60' }];
	}

	function removeDebtRow(idx: number) {
		if (debts.length <= 1) return;
		debts = debts.filter((_, i) => i !== idx);
	}

	let netWorthChart = $derived.by(() => {
		if (!netWorth || netWorth.snapshots.length === 0) return null;
		return {
			labels: netWorth.snapshots.map((s) => formatDate(s.snapshot_date)),
			series: [
				{
					name: 'Net Worth',
					color: '#34d399',
					values: netWorth.snapshots.map((s) => Number.parseFloat(s.net_worth))
				},
				{
					name: 'Assets',
					color: '#22d3ee',
					dashed: true,
					values: netWorth.snapshots.map((s) => Number.parseFloat(s.total_assets))
				},
				{
					name: 'Liabilities',
					color: '#fb7185',
					dashed: true,
					values: netWorth.snapshots.map((s) => Number.parseFloat(s.total_liabilities))
				}
			]
		};
	});

	let debtChart = $derived.by(() => {
		if (!debtResult) return null;
		const monthSet = new Set<number>();
		for (const p of debtResult.snowball.monthly_balance_curve) monthSet.add(p.month);
		for (const p of debtResult.avalanche.monthly_balance_curve) monthSet.add(p.month);
		const monthsList = [...monthSet].sort((a, b) => a - b);
		const snowMap = new Map(debtResult.snowball.monthly_balance_curve.map((p) => [p.month, p.total_balance]));
		const avalMap = new Map(debtResult.avalanche.monthly_balance_curve.map((p) => [p.month, p.total_balance]));
		let lastSnow = debtResult.snowball.monthly_balance_curve[0]?.total_balance ?? 0;
		let lastAval = debtResult.avalanche.monthly_balance_curve[0]?.total_balance ?? 0;
		const snowVals: number[] = [];
		const avalVals: number[] = [];
		for (const m of monthsList) {
			if (snowMap.has(m)) lastSnow = snowMap.get(m)!;
			else if (m > debtResult.snowball.months_to_payoff) lastSnow = 0;
			if (avalMap.has(m)) lastAval = avalMap.get(m)!;
			else if (m > debtResult.avalanche.months_to_payoff) lastAval = 0;
			snowVals.push(lastSnow);
			avalVals.push(lastAval);
		}
		return {
			labels: monthsList.map((m) => (m === 0 ? 'Now' : `Mo ${m}`)),
			series: [
				{ name: 'Avalanche', color: '#34d399', values: avalVals },
				{ name: 'Snowball', color: '#22d3ee', dashed: true, values: snowVals }
			]
		};
	});

	let whatIfChart = $derived.by(() => {
		if (!whatIfResult) return null;
		return {
			labels: whatIfResult.points.map((p) => p.label),
			series: [
				{
					name: 'What-If Scenario',
					color: '#34d399',
					values: whatIfResult.points.map((p) => Number.parseFloat(p.scenario_balance))
				},
				{
					name: 'Baseline',
					color: '#94a3b8',
					dashed: true,
					values: whatIfResult.points.map((p) => Number.parseFloat(p.baseline_balance))
				}
			]
		};
	});
</script>

<div class="space-y-6">
	<!-- HEADER & TABS -->
	<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">Wealth, Goals & Simulators</h1>
			<p class="text-xs sm:text-sm text-slate-400 mt-0.5">
				Net worth milestones, goal pace accelerators, Snowball/Avalanche payoff, What-If modeling & 4% FI tracker.
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
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

			<button
				type="button"
				onclick={() =>
					goto(
						`/advisor?q=${encodeURIComponent(
							'Run a Senior Personal CFO Wealth Review on my net worth, asset allocation, debt-to-asset ratio, and active goals — give me my top 3 wealth-building moves.'
						)}`
					)}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-emerald-300 transition cursor-pointer"
			>
				<Sparkles class="w-3.5 h-3.5" />
				<span class="hidden sm:inline">Wealth Review</span>
			</button>

			<div class="inline-flex p-1 rounded-xl bg-slate-900 border border-slate-800">
				<button
					type="button"
					onclick={() => (activeTab = 'net_worth')}
					class="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition {activeTab === 'net_worth'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<TrendingUp class="w-3.5 h-3.5" /> Net Worth
				</button>
				<button
					type="button"
					onclick={() => (activeTab = 'goals')}
					class="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition {activeTab === 'goals'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<Target class="w-3.5 h-3.5" /> Goals ({goals.length})
				</button>
				<button
					type="button"
					onclick={() => (activeTab = 'simulators')}
					class="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition {activeTab === 'simulators'
						? 'bg-emerald-500/20 text-emerald-300'
						: 'text-slate-400 hover:text-white'}"
				>
					<Calculator class="w-3.5 h-3.5" /> Simulators & FI
				</button>
			</div>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
			<span>{error}</span>
			<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}
	{#if statusMsg}
		<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3">
			<span class="flex items-center gap-2">
				<CheckCircle2 class="w-4 h-4 shrink-0" />
				{statusMsg}
			</span>
			<button type="button" onclick={() => (statusMsg = null)} class="text-emerald-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each Array(4) as _}
				<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
			{/each}
		</div>
		<div class="card-surface rounded-2xl h-64 animate-pulse"></div>
	{:else if activeTab === 'net_worth' && netWorth}
		<!-- 1. EXECUTIVE NET WORTH COCKPIT & WEALTH MILESTONES -->
		<div class="space-y-5">
			<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
				<div class="card-surface rounded-2xl p-5 border-emerald-500/20">
					<div class="text-xs text-slate-400">Current Net Worth</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(netWorth.current_net_worth, netWorth.base_currency)}
					</div>
					{#if netWorth.change_amount !== null}
						<div class="text-[11px] font-mono-num mt-1 {Number.parseFloat(netWorth.change_amount) >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
							<span class={privacyMode ? 'privacy-blur' : ''}>
								{Number.parseFloat(netWorth.change_amount) >= 0 ? '+' : ''}{formatMoney(netWorth.change_amount, netWorth.base_currency)}
							</span>
							{#if netWorth.change_pct !== null}({netWorth.change_pct}%){/if}
						</div>
					{:else}
						<div class="text-[11px] text-slate-500 mt-1">Capture snapshots to track growth</div>
					{/if}
				</div>

				<div class="card-surface rounded-2xl p-5">
					<div class="text-xs text-slate-400">Total Assets</div>
					<div class="text-2xl font-bold font-mono-num text-emerald-400 mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(netWorth.current_assets, netWorth.base_currency)}
					</div>
					<div class="text-[11px] text-slate-400 font-mono-num mt-1 truncate {privacyMode ? 'privacy-blur' : ''}">
						Cash {formatMoney(nwStats.liquid, netWorth.base_currency)} · Inv {formatMoney(nwStats.invested, netWorth.base_currency)}
					</div>
				</div>

				<div class="card-surface rounded-2xl p-5">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Total Liabilities</span>
						<span
							class="text-[10px] font-mono-num px-1.5 py-0.5 rounded-full {nwStats.debtToAssetPct <= 30
								? 'bg-emerald-500/15 text-emerald-300'
								: 'bg-rose-500/15 text-rose-300'}"
						>
							{nwStats.debtToAssetPct}% D/A
						</span>
					</div>
					<div class="text-2xl font-bold font-mono-num text-rose-400 mt-1.5 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(netWorth.current_liabilities, netWorth.base_currency)}
					</div>
					<div class="text-[11px] text-slate-500 mt-1">Debt-to-Asset benchmark: &lt;30%</div>
				</div>

				<div class="card-surface rounded-2xl p-5 flex flex-col justify-between gap-2">
					<div class="flex items-center justify-between text-xs text-slate-400">
						<span>Emergency Runway</span>
						<Shield class="w-4 h-4 text-cyan-400" />
					</div>
					<div class="flex items-center justify-between gap-2">
						<span class="text-2xl font-bold font-mono-num text-cyan-300">
							{health ? `${health.cash_flow_ratios.emergency_runway_months} mo` : '—'}
						</span>
						<button
							type="button"
							disabled={capturingSnapshot}
							onclick={handleSnapshot}
							class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
						>
							<Camera class="w-3.5 h-3.5" />
							{capturingSnapshot ? 'Saving...' : 'Snapshot'}
						</button>
					</div>
				</div>
			</div>

			<!-- Allocation Bar + Next Wealth Milestone Tracker -->
			<div class="grid lg:grid-cols-12 gap-5">
				<div class="lg:col-span-6 card-surface rounded-2xl p-5 space-y-3">
					<div class="flex items-center justify-between text-xs">
						<span class="font-semibold text-white">Asset vs. Liability Allocation</span>
						<span class="font-mono-num text-slate-400">
							{nwStats.liquidPct}% Cash · {nwStats.investedPct}% Inv · {nwStats.debtPct}% Debt
						</span>
					</div>
					<div class="h-3 rounded-full bg-slate-900 overflow-hidden flex gap-0.5">
						{#if nwStats.liquidPct > 0}
							<div class="h-full bg-emerald-400 transition-all" style="width: {nwStats.liquidPct}%"></div>
						{/if}
						{#if nwStats.investedPct > 0}
							<div class="h-full bg-cyan-400 transition-all" style="width: {nwStats.investedPct}%"></div>
						{/if}
						{#if nwStats.debtPct > 0}
							<div class="h-full bg-rose-400 transition-all" style="width: {nwStats.debtPct}%"></div>
						{/if}
					</div>
					<div class="flex items-center gap-4 text-[11px] text-slate-400">
						<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-emerald-400"></span>Liquid Cash</span>
						<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-cyan-400"></span>Investments</span>
						<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-xs bg-rose-400"></span>Debt</span>
					</div>
				</div>

				<div class="lg:col-span-6 card-surface rounded-2xl p-5 space-y-3 border-cyan-500/20">
					<div class="flex items-center justify-between text-xs">
						<span class="font-semibold text-white flex items-center gap-1.5">
							<Flag class="w-3.5 h-3.5 text-cyan-400" /> Next Wealth Milestone
						</span>
						<span class="font-mono-num font-bold text-cyan-300 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(nwStats.nextMilestone, netWorth.base_currency)}
						</span>
					</div>
					<div class="h-3 rounded-full bg-slate-900 overflow-hidden">
						<div
							class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400 transition-all duration-700"
							style="width: {nwStats.milestonePct}%"
						></div>
					</div>
					<div class="flex items-center justify-between text-[11px] font-mono-num text-slate-400">
						<span><strong class="text-white">{nwStats.milestonePct}%</strong> reached</span>
						<span class={privacyMode ? 'privacy-blur' : ''}>
							{formatMoney(nwStats.milestoneGap, netWorth.base_currency)} to go
						</span>
					</div>
				</div>
			</div>

			{#if netWorthChart}
				<div class="card-surface rounded-2xl p-6 space-y-3">
					<h2 class="text-base font-semibold text-white">Net Worth Trend</h2>
					<LineChart
						labels={netWorthChart.labels}
						series={netWorthChart.series}
						currency={netWorth.base_currency}
						height={210}
					/>
				</div>
			{/if}

			<div class="grid lg:grid-cols-2 gap-6">
				<div class="card-surface rounded-2xl p-6 space-y-4">
					<h2 class="text-base font-semibold text-white">Assets & Liabilities Breakdown</h2>
					{#if netWorth.accounts.length === 0}
						<p class="text-sm text-slate-400">Add accounts to see your balance sheet breakdown.</p>
					{:else}
						<div class="divide-y divide-slate-800/70">
							{#each netWorth.accounts as acc}
								<div class="py-2.5 flex items-center justify-between text-sm">
									<div>
										<span class="font-medium text-white">{acc.name}</span>
										<span class="text-xs text-slate-400 ml-2 capitalize">({acc.type})</span>
									</div>
									<span class="font-mono-num font-semibold {acc.classification === 'liability' ? 'text-rose-400' : 'text-emerald-400'} {privacyMode ? 'privacy-blur' : ''}">
										{formatMoney(acc.balance, acc.currency)}
									</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<div class="card-surface rounded-2xl p-6 space-y-4">
					<h2 class="text-base font-semibold text-white">Historical Snapshots</h2>
					{#if netWorth.snapshots.length === 0}
						<p class="text-sm text-slate-400">
							Click <strong>Snapshot</strong> above to record today's net worth and start building your wealth curve.
						</p>
					{:else}
						<div class="divide-y divide-slate-800/70">
							{#each [...netWorth.snapshots].reverse() as snap}
								<div class="py-2.5 flex items-center justify-between text-xs font-mono-num">
									<span class="text-slate-300">{formatDate(snap.snapshot_date)}</span>
									<div class="flex items-center gap-3 sm:gap-4 {privacyMode ? 'privacy-blur' : ''}">
										<span class="text-emerald-400/80 hidden sm:inline">A: {formatMoney(snap.total_assets, netWorth.base_currency)}</span>
										<span class="text-rose-400/80 hidden sm:inline">L: {formatMoney(snap.total_liabilities, netWorth.base_currency)}</span>
										<span class="font-semibold text-white">NW: {formatMoney(snap.net_worth, netWorth.base_currency)}</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	{:else if activeTab === 'goals'}
		<!-- 2. UPGRADED FINANCIAL GOALS HUB -->
		<div class="space-y-5">
			<!-- Goals Portfolio Summary Bar -->
			<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
				<div class="card-surface rounded-2xl p-4">
					<div class="text-xs text-slate-400">Total Saved Across Goals</div>
					<div class="text-2xl font-bold font-mono-num text-emerald-400 mt-1 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(goalsSummary.totalSaved, baseCcy)}
					</div>
					<div class="text-[11px] text-slate-500 mt-1">
						{goalsSummary.completedCount} of {goals.length} completed
					</div>
				</div>

				<div class="card-surface rounded-2xl p-4">
					<div class="text-xs text-slate-400">Remaining to Fund</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-1 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(goalsSummary.remaining, baseCcy)}
					</div>
					<div class="text-[11px] text-slate-500 font-mono-num mt-1 {privacyMode ? 'privacy-blur' : ''}">
						Target total: {formatMoney(goalsSummary.totalTarget, baseCcy)}
					</div>
				</div>

				<div class="card-surface rounded-2xl p-4">
					<div class="text-xs text-slate-400">Monthly Goal Commitment</div>
					<div class="text-2xl font-bold font-mono-num text-cyan-300 mt-1 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(goalsSummary.totalMonthly, baseCcy)}/mo
					</div>
					<div class="text-[11px] font-mono-num mt-1 {goalsSummary.unallocated < 0 ? 'text-amber-300' : 'text-emerald-400'}">
						{#if health && goalsSummary.realSurplus > 0}
							{goalsSummary.unallocated >= 0
								? `${formatMoney(goalsSummary.unallocated, baseCcy)} unallocated surplus`
								: `${formatMoney(Math.abs(goalsSummary.unallocated), baseCcy)} above avg surplus`}
						{:else}
							Active monthly plan
						{/if}
					</div>
				</div>

				<div class="card-surface rounded-2xl p-4 flex flex-col justify-center gap-2">
					<button
						type="button"
						onclick={() => (showGoalModal = true)}
						class="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs flex items-center justify-center gap-1.5 cursor-pointer"
					>
						<Plus class="w-4 h-4" /> New Financial Goal
					</button>
					<button
						type="button"
						onclick={() =>
							goto(
								`/advisor?q=${encodeURIComponent(
									'Review all my active financial goals vs my monthly surplus and tell me how to optimize my monthly contributions.'
								)}`
							)}
						class="w-full py-1.5 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-emerald-300 text-[11px] font-semibold flex items-center justify-center gap-1.5 cursor-pointer"
					>
						<Sparkles class="w-3 h-3" /> Optimize with Luna
					</button>
				</div>
			</div>

			{#if goals.length === 0}
				<div class="card-surface rounded-2xl p-12 text-center space-y-3">
					<Target class="w-10 h-10 text-emerald-400 mx-auto" />
					<h2 class="text-lg font-semibold text-white">Set your first financial goal</h2>
					<p class="text-sm text-slate-400 max-w-md mx-auto">
						Start with a 1-click 6-Month Emergency Fund auto-calculated from your real spending, or track a Travel, Home, or Investment milestone.
					</p>
					<button
						type="button"
						onclick={() => (showGoalModal = true)}
						class="mt-2 inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer"
					>
						<Plus class="w-4 h-4" /> Create First Goal
					</button>
				</div>
			{:else}
				<div class="grid md:grid-cols-2 gap-4">
					{#each goals as g}
						{@const pace = goalPaceStatus(g)}
						<div
							role="button"
							tabindex="0"
							onclick={() => (inspectedGoalId = g.id)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									inspectedGoalId = g.id;
								}
							}}
							class="card-surface card-surface-hover rounded-2xl p-5 space-y-4 relative overflow-hidden text-left cursor-pointer group outline-none focus:ring-2 focus:ring-emerald-500/50"
						>
							<div
								class="absolute top-0 inset-x-0 h-1"
								style="background-color: {g.color || '#10b981'}"
							></div>

							<div class="flex items-start justify-between gap-3">
								<div class="flex items-center gap-3 min-w-0">
									<div
										class="h-10 w-10 rounded-xl flex items-center justify-center border border-white/10 shrink-0"
										style="background-color: {(g.color || '#10b981')}22; color: {g.color || '#10b981'}"
									>
										{#if g.goal_type === 'emergency_fund'}
											<Shield class="w-5 h-5" />
										{:else if g.goal_type === 'debt_payoff'}
											<CreditCard class="w-5 h-5" />
										{:else if g.goal_type === 'investment' || g.goal_type === 'retirement'}
											<TrendingUp class="w-5 h-5" />
										{:else if g.goal_type === 'purchase'}
											<ShoppingBag class="w-5 h-5" />
										{:else}
											<PiggyBank class="w-5 h-5" />
										{/if}
									</div>
									<div class="min-w-0">
										<div class="flex items-center gap-2 flex-wrap">
											<span class="font-semibold text-white truncate">{g.name}</span>
											{#if g.is_completed}
												<span class="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 font-semibold">
													<CheckCircle2 class="w-3 h-3" /> Completed
												</span>
											{:else if pace}
												<span class="text-[10px] px-2 py-0.5 rounded-full border font-semibold {pace.cls}">
													{pace.label}
												</span>
											{/if}
										</div>
										<div class="text-xs text-slate-400 capitalize mt-0.5">
											{g.goal_type.replace('_', ' ')}
											{#if g.target_date}· Target {formatDate(g.target_date)}{/if}
										</div>
									</div>
								</div>

								<div class="flex items-center gap-1 shrink-0">
									{#if !g.is_completed}
										<button
											type="button"
											onclick={(e) => {
												e.stopPropagation();
												contributeGoal = g;
												contributeModalOpen = true;
											}}
											class="px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer"
										>
											+ Contribute
										</button>
									{/if}
									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											deleteGoalTarget = g;
										}}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										title="Delete goal"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</div>
							</div>

							<div class="space-y-1.5">
								<div class="flex items-center justify-between text-xs font-mono-num">
									<span class="text-white font-semibold {privacyMode ? 'privacy-blur' : ''}">
										{formatMoney(g.current_amount, baseCcy)}
									</span>
									<span class="text-slate-400">
										Target <span class={privacyMode ? 'privacy-blur' : ''}>{formatMoney(g.target_amount, baseCcy)}</span> ({g.progress_pct}%)
									</span>
								</div>
								<div class="h-2.5 rounded-full bg-slate-800 overflow-hidden">
									<div
										class="h-full rounded-full transition-all duration-500"
										style="width: {Math.min(100, g.progress_pct)}%; background-color: {g.color || '#10b981'}"
									></div>
								</div>
							</div>

							<div class="flex items-center justify-between pt-1 border-t border-slate-800/70 text-[11px] text-slate-400 font-mono-num">
								<div>
									Plan: <span class="text-slate-200 {privacyMode ? 'privacy-blur' : ''}">{formatMoney(g.monthly_contribution, baseCcy)}/mo</span>
									{#if g.required_monthly && Number.parseFloat(g.required_monthly) > Number.parseFloat(g.monthly_contribution)}
										<span class="text-amber-300 ml-1">(need {formatMoney(g.required_monthly, baseCcy)})</span>
									{/if}
								</div>
								<div class="flex items-center gap-2">
									{#if g.projected_completion_date}
										<span class="text-cyan-300">Est. {formatDate(g.projected_completion_date)}</span>
									{/if}
									<span class="text-[10px] text-slate-500 group-hover:text-emerald-400 transition">Edit →</span>
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{:else if activeTab === 'simulators'}
		<!-- 4 & 5. UPGRADED SIMULATORS + FI CALCULATOR -->
		<div class="space-y-6">
			<div class="grid lg:grid-cols-2 gap-6">
				<!-- Debt Payoff Comparator -->
				<div class="card-surface rounded-2xl p-6 space-y-4">
					<div class="flex flex-wrap items-start justify-between gap-2">
						<div>
							<h2 class="text-base font-semibold text-white">Debt Payoff: Snowball vs. Avalanche</h2>
							<p class="text-xs text-slate-400">Deterministic month-by-month amortization simulator.</p>
						</div>
						<div class="flex items-center gap-2">
							{#if realDebtAccounts.length > 0}
								<button
									type="button"
									onclick={loadRealDebtsIntoSim}
									class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 text-cyan-200 text-[11px] font-semibold cursor-pointer"
								>
									<Download class="w-3 h-3" /> Load My Debts ({realDebtAccounts.length})
								</button>
							{/if}
							<button type="button" onclick={addDebtRow} class="text-xs text-emerald-400 hover:text-emerald-300 font-semibold cursor-pointer">
								+ Add Debt
							</button>
						</div>
					</div>

					<div class="space-y-2">
						<div class="grid grid-cols-12 gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 px-1">
							<span class="col-span-4">Debt Name</span>
							<span class="col-span-3">Balance</span>
							<span class="col-span-2">APR %</span>
							<span class="col-span-2">Min/mo</span>
							<span class="col-span-1"></span>
						</div>
						{#each debts as debt, i}
							<div class="grid grid-cols-12 gap-2 items-center">
								<input bind:value={debt.name} placeholder="Name" class="col-span-4 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white" />
								<input type="number" bind:value={debt.balance} placeholder="Balance" class="col-span-3 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
								<input type="number" step="0.1" bind:value={debt.apr} placeholder="APR %" class="col-span-2 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
								<input type="number" bind:value={debt.min_payment} placeholder="Min" class="col-span-2 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
								<button type="button" onclick={() => removeDebtRow(i)} class="col-span-1 text-slate-500 hover:text-rose-400 cursor-pointer flex justify-center">
									<Trash2 class="w-3.5 h-3.5" />
								</button>
							</div>
						{/each}
					</div>

					<div class="flex items-end gap-3">
						<div class="flex-1">
							<label for="extra-pay" class="block text-[11px] text-slate-400 mb-1">Extra Monthly Payment ({baseCcy})</label>
							<input id="extra-pay" type="number" bind:value={extraPayment} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
						</div>
						<button
							type="button"
							disabled={runningDebtSim}
							onclick={runDebtSim}
							class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50"
						>
							{runningDebtSim ? 'Simulating...' : 'Compare'}
						</button>
					</div>

					{#if debtResult}
						<div class="grid grid-cols-2 gap-3 pt-2">
							<div class="p-3.5 rounded-xl bg-slate-950/70 border {debtResult.recommended_strategy === 'avalanche' ? 'border-emerald-500/40' : 'border-slate-800'}">
								<div class="text-xs font-semibold text-emerald-300 flex items-center justify-between">
									<span>Avalanche (Highest APR)</span>
									{#if debtResult.recommended_strategy === 'avalanche'}<Sparkles class="w-3.5 h-3.5" />{/if}
								</div>
								<div class="text-lg font-bold font-mono-num text-white mt-1">{debtResult.avalanche.months_to_payoff} months</div>
								<div class="text-xs text-slate-400 font-mono-num">Interest: {formatMoney(debtResult.avalanche.total_interest_paid, baseCcy)}</div>
							</div>

							<div class="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
								<div class="text-xs font-semibold text-cyan-300">Snowball (Smallest Balance)</div>
								<div class="text-lg font-bold font-mono-num text-white mt-1">{debtResult.snowball.months_to_payoff} months</div>
								<div class="text-xs text-slate-400 font-mono-num">Interest: {formatMoney(debtResult.snowball.total_interest_paid, baseCcy)}</div>
							</div>
						</div>
						<div class="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/25 rounded-xl p-3 font-mono-num space-y-1">
							<div>
								Avalanche saves <strong>{formatMoney(debtResult.interest_saved_by_avalanche, baseCcy)}</strong> in interest
								{#if debtResult.months_saved_by_avalanche > 0}and {debtResult.months_saved_by_avalanche} months{/if}.
							</div>
							<div class="text-[11px] text-slate-300">
								Payoff Order: {debtResult.avalanche.payoff_order.join(' → ')}
							</div>
						</div>
						{#if debtChart}
							<div class="pt-2">
								<LineChart labels={debtChart.labels} series={debtChart.series} currency={baseCcy} height={180} />
							</div>
						{/if}
					{/if}
				</div>

				<!-- What-If Cash Flow Simulator -->
				<div class="card-surface rounded-2xl p-6 space-y-4">
					<div>
						<h2 class="text-base font-semibold text-white">What-If Cash Flow & Wealth Simulator</h2>
						<p class="text-xs text-slate-400">Try a 1-click scenario preset or customize sliders below.</p>
					</div>

					<!-- 1-Click Scenario Presets -->
					<div class="flex flex-wrap gap-1.5">
						<button type="button" onclick={() => applyWhatIfPreset('cut')} class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] text-emerald-300 cursor-pointer">
							Cut -300/mo
						</button>
						<button type="button" onclick={() => applyWhatIfPreset('raise')} class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] text-cyan-300 cursor-pointer">
							+15% Raise
						</button>
						<button type="button" onclick={() => applyWhatIfPreset('purchase')} class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] text-amber-300 cursor-pointer">
							Buy 3,000 Item
						</button>
						<button type="button" onclick={() => applyWhatIfPreset('invest')} class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] text-violet-300 cursor-pointer">
							Invest @ 8% (5 Yrs)
						</button>
						<button type="button" onclick={() => applyWhatIfPreset('sabbatical')} class="px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] text-rose-300 cursor-pointer">
							Sabbatical
						</button>
					</div>

					<div class="grid grid-cols-2 gap-3 text-xs">
						<div>
							<label for="wi-start" class="block text-slate-400 mb-1">Starting Savings</label>
							<input id="wi-start" type="number" bind:value={wiStarting} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
						</div>
						<div>
							<label for="wi-one" class="block text-slate-400 mb-1">One-Time Impact (+/-)</label>
							<input id="wi-one" type="number" bind:value={wiOneTime} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
						</div>
						<div>
							<label for="wi-inc" class="block text-slate-400 mb-1">Current Monthly Income</label>
							<input id="wi-inc" type="number" bind:value={wiIncome} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
						</div>
						<div>
							<label for="wi-exp" class="block text-slate-400 mb-1">Current Monthly Expenses</label>
							<input id="wi-exp" type="number" bind:value={wiExpenses} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
						</div>
						<div>
							<label for="wi-dinc" class="block text-emerald-300 mb-1">Income Delta (+/- mo)</label>
							<input id="wi-dinc" type="number" bind:value={wiIncomeDelta} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-emerald-500/30 text-white font-mono-num" />
						</div>
						<div>
							<label for="wi-dexp" class="block text-cyan-300 mb-1">Expense Delta (+/- mo)</label>
							<input id="wi-dexp" type="number" bind:value={wiExpenseDelta} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-cyan-500/30 text-white font-mono-num" />
						</div>
					</div>

					<!-- Interactive Horizon & Return Sliders -->
					<div class="grid grid-cols-2 gap-4 pt-1">
						<div class="space-y-1">
							<div class="flex items-center justify-between text-[11px]">
								<span class="text-slate-400">Horizon</span>
								<span class="font-mono-num font-semibold text-white">{wiHorizon} mo</span>
							</div>
							<input type="range" min={6} max={120} step={6} bind:value={wiHorizon} class="w-full accent-emerald-400 cursor-pointer" />
						</div>
						<div class="space-y-1">
							<div class="flex items-center justify-between text-[11px]">
								<span class="text-slate-400">Annual Return</span>
								<span class="font-mono-num font-semibold text-cyan-300">{wiReturnPct.toFixed(1)}%</span>
							</div>
							<input type="range" min={0} max={12} step={0.5} bind:value={wiReturnPct} class="w-full accent-cyan-400 cursor-pointer" />
						</div>
					</div>

					<button
						type="button"
						disabled={runningWhatIf}
						onclick={runWhatIfSim}
						class="w-full py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{runningWhatIf ? 'Running Projection...' : 'Run What-If Projection'}
					</button>

					{#if whatIfResult}
						<div class="grid grid-cols-3 gap-2.5 text-xs pt-1">
							<div class="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
								<div class="text-slate-400 text-[10px]">Baseline End</div>
								<div class="font-mono-num font-semibold text-slate-200 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									{formatMoney(whatIfResult.baseline_end_balance, baseCcy)}
								</div>
							</div>
							<div class="p-3 rounded-xl bg-slate-950/70 border border-emerald-500/30">
								<div class="text-emerald-300 text-[10px]">Scenario End</div>
								<div class="font-mono-num font-bold text-emerald-400 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
									{formatMoney(whatIfResult.scenario_end_balance, baseCcy)}
								</div>
							</div>
							<div class="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
								<div class="text-slate-400 text-[10px]">Net Impact</div>
								<div
									class="font-mono-num font-bold mt-0.5 {Number.parseFloat(whatIfResult.net_impact) >= 0
										? 'text-cyan-300'
										: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
								>
									{Number.parseFloat(whatIfResult.net_impact) >= 0 ? '+' : ''}{formatMoney(whatIfResult.net_impact, baseCcy)}
								</div>
							</div>
						</div>
						{#if whatIfChart}
							<div class="pt-2">
								<LineChart labels={whatIfChart.labels} series={whatIfChart.series} currency={baseCcy} height={180} />
							</div>
						{/if}
					{/if}
				</div>
			</div>

			<!-- 5. BONUS CFP TOOL: FINANCIAL INDEPENDENCE (FI / 4% RULE) CALCULATOR -->
			<FireCalculator
				initialNetWorth={nwStats.nw}
				initialAnnualExpenses={(Number.parseFloat(wiExpenses) || 2000) * 12}
				initialMonthlySavings={Math.max(
					200,
					(Number.parseFloat(wiIncome) || 3000) - (Number.parseFloat(wiExpenses) || 2000)
				)}
				currency={baseCcy}
				{privacyMode}
			/>
		</div>
	{/if}
</div>

<!-- QUICK-CONTRIBUTE MODAL (replaces prompt) -->
<GoalContributeModal
	bind:open={contributeModalOpen}
	goal={contributeGoal}
	currency={baseCcy}
	onContributed={async (updated) => {
		goals = goals.map((g) => (g.id === updated.id ? updated : g));
		statusMsg = `Added contribution to "${updated.name}" (${updated.progress_pct}% complete)!`;
	}}
/>

<!-- 3. GOAL INSPECTOR & PACE ACCELERATOR DRAWER -->
<GoalDetailDrawer
	goal={inspectedGoal}
	currency={baseCcy}
	{privacyMode}
	onClose={() => (inspectedGoalId = null)}
	onSaved={async () => {
		goals = await api.listGoals();
		statusMsg = 'Goal updated.';
	}}
	onContribute={(g) => {
		contributeGoal = g;
		contributeModalOpen = true;
	}}
	onRequestDelete={(g) => (deleteGoalTarget = g)}
/>

<!-- CREATE GOAL MODAL WITH SMART PRESETS -->
{#if showGoalModal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
		<div class="card-surface rounded-2xl w-full max-w-lg p-6 space-y-5 border border-slate-700/80 my-auto">
			<div class="flex items-center justify-between">
				<div>
					<h2 class="text-base font-semibold text-white">Create Financial Goal</h2>
					<p class="text-[11px] text-slate-400">Pick a smart preset (auto-sized from your ledger) or build custom.</p>
				</div>
				<button type="button" onclick={() => (showGoalModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<div class="space-y-2">
				<div class="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
					<Sparkles class="w-3 h-3 text-emerald-400" /> Smart Goal Presets
				</div>
				<div class="flex flex-wrap gap-1.5">
					{#each goalPresets as p}
						<button
							type="button"
							onclick={() => applyGoalPreset(p)}
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-950 hover:bg-slate-900 border border-slate-800 text-[11px] text-slate-200 cursor-pointer"
						>
							<span class="w-2 h-2 rounded-full" style="background-color: {p.color}"></span>
							{p.label}
						</button>
					{/each}
				</div>
			</div>

			<form onsubmit={handleCreateGoal} class="space-y-4">
				<div>
					<label for="g-name" class="block text-xs font-medium text-slate-300 mb-1">Goal Name</label>
					<input
						id="g-name"
						type="text"
						required
						bind:value={goalName}
						placeholder="e.g., 6-Month Emergency Fund"
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="g-type" class="block text-xs font-medium text-slate-300 mb-1">Goal Type</label>
						<select id="g-type" bind:value={goalType} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="emergency_fund">Emergency Fund</option>
							<option value="savings">Savings</option>
							<option value="debt_payoff">Debt Payoff</option>
							<option value="investment">Investment</option>
							<option value="purchase">Major Purchase</option>
							<option value="retirement">Retirement</option>
						</select>
					</div>
					<div>
						<label for="g-date" class="block text-xs font-medium text-slate-300 mb-1">Target Date (optional)</label>
						<input id="g-date" type="date" bind:value={goalTargetDate} class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white" />
					</div>
				</div>

				<div class="grid grid-cols-3 gap-3">
					<div>
						<label for="g-tgt" class="block text-xs font-medium text-slate-300 mb-1">Target ({baseCcy})</label>
						<input id="g-tgt" type="number" step="0.01" min="1" required bind:value={goalTarget} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
					<div>
						<label for="g-cur" class="block text-xs font-medium text-slate-300 mb-1">Already Saved</label>
						<input id="g-cur" type="number" step="0.01" min="0" bind:value={goalCurrent} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
					<div>
						<label for="g-mo" class="block text-xs font-medium text-slate-300 mb-1">Monthly Plan</label>
						<input id="g-mo" type="number" step="0.01" min="0" bind:value={goalMonthly} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
				</div>

				<div class="space-y-1.5">
					<span class="block text-xs font-medium text-slate-300">Accent Color</span>
					<div class="flex items-center gap-2 flex-wrap">
						{#each GOAL_COLORS as c}
							<button
								type="button"
								onclick={() => (goalColor = c)}
								class="h-6 w-6 rounded-lg flex items-center justify-center cursor-pointer border-2 {goalColor === c
									? 'border-white scale-110'
									: 'border-transparent opacity-80'}"
								style="background-color: {c}"
								aria-label="Color {c}"
							>
								{#if goalColor === c}
									<Check class="w-3 h-3 text-slate-950 stroke-[3]" />
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<div class="flex justify-end gap-2.5 pt-2">
					<button type="button" onclick={() => (showGoalModal = false)} class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={savingGoal} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50">
						{savingGoal ? 'Saving...' : 'Create Goal'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- SAFE DELETE GOAL MODAL -->
{#if deleteGoalTarget}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-sm p-6 space-y-4 border border-rose-500/35">
			<div class="flex items-start gap-3">
				<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
					<AlertTriangle class="w-5 h-5" />
				</div>
				<div>
					<h2 class="text-base font-semibold text-white">Delete "{deleteGoalTarget.name}"?</h2>
					<p class="text-xs text-slate-400 mt-0.5">
						Removes this goal ({formatMoney(deleteGoalTarget.current_amount, baseCcy)} / {formatMoney(deleteGoalTarget.target_amount, baseCcy)}). Your bank account balances remain unchanged.
					</p>
				</div>
			</div>
			<div class="flex items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={deletingGoal}
					onclick={() => (deleteGoalTarget = null)}
					class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={deletingGoal}
					onclick={confirmDeleteGoal}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Trash2 class="w-3.5 h-3.5" />
					{deletingGoal ? 'Deleting...' : 'Delete Goal'}
				</button>
			</div>
		</div>
	</div>
{/if}
