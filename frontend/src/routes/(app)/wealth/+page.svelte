<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type {
		DebtInput,
		DebtPayoffComparison,
		FinancialGoal,
		GoalType,
		NetWorthOverview,
		WhatIfResponse
	} from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		Target,
		TrendingUp,
		Calculator,
		Camera,
		Plus,
		Trash2,
		CheckCircle2,
		X,
		Sparkles
	} from 'lucide-svelte';

	let activeTab = $state<'net_worth' | 'goals' | 'simulators'>('net_worth');
	let netWorth = $state<NetWorthOverview | null>(null);
	let goals = $state<FinancialGoal[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let baseCcy = $derived(auth.user?.base_currency || 'USD');

	// Net Worth snapshot state
	let capturingSnapshot = $state(false);

	// Goal modal
	let showGoalModal = $state(false);
	let goalName = $state('');
	let goalType = $state<GoalType>('emergency_fund');
	let goalTarget = $state('10000.00');
	let goalCurrent = $state('0.00');
	let goalMonthly = $state('500.00');
	let goalTargetDate = $state('');
	let savingGoal = $state(false);

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
	let wiIncomeDelta = $state('400');
	let wiExpenseDelta = $state('-250');
	let wiOneTime = $state('0');
	let wiReturnPct = $state('5.0');
	let wiHorizon = $state(24);
	let whatIfResult = $state<WhatIfResponse | null>(null);
	let runningWhatIf = $state(false);

	async function loadAll() {
		loading = true;
		error = null;
		try {
			const [nw, gls, dash] = await Promise.all([
				api.getNetWorth(),
				api.listGoals(),
				api.dashboardSummary(1)
			]);
			netWorth = nw;
			goals = gls;
			// Pre-fill What-If simulator from actual user ledger when available
			if (Number.parseFloat(nw.current_assets) > 0) wiStarting = nw.current_assets;
			if (Number.parseFloat(dash.period_income) > 0) wiIncome = dash.period_income;
			if (Number.parseFloat(dash.period_expenses) > 0) wiExpenses = dash.period_expenses;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load wealth data';
		} finally {
			loading = false;
		}
	}

	onMount(loadAll);

	async function handleSnapshot() {
		capturingSnapshot = true;
		error = null;
		try {
			await api.captureNetWorthSnapshot();
			netWorth = await api.getNetWorth();
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
				name: goalName,
				goal_type: goalType,
				target_amount: goalTarget,
				current_amount: goalCurrent || '0.00',
				monthly_contribution: goalMonthly || '0.00',
				target_date: goalTargetDate || null
			});
			showGoalModal = false;
			goalName = '';
			goals = await api.listGoals();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not create goal';
		} finally {
			savingGoal = false;
		}
	}

	async function handleContribute(goal: FinancialGoal) {
		const raw = prompt(`Add contribution to "${goal.name}" (${baseCcy}):`, '250');
		if (!raw) return;
		const num = Number.parseFloat(raw);
		if (Number.isNaN(num) || num <= 0) return;
		await api.contributeGoal(goal.id, num.toFixed(2));
		goals = await api.listGoals();
	}

	async function handleDeleteGoal(goal: FinancialGoal) {
		if (!confirm(`Delete goal "${goal.name}"?`)) return;
		await api.deleteGoal(goal.id);
		goals = goals.filter((g) => g.id !== goal.id);
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
				annual_return_pct: wiReturnPct || '0',
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
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Wealth, Goals & Simulators</h1>
			<p class="text-sm text-slate-400 mt-0.5">
				Track net worth over time, fund milestones, and run deterministic Snowball/Avalanche & What-If projections.
			</p>
		</div>

		<!-- Tabs -->
		<div class="inline-flex p-1 rounded-xl bg-slate-900 border border-slate-800">
			<button
				type="button"
				onclick={() => (activeTab = 'net_worth')}
				class="px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer {activeTab === 'net_worth'
					? 'bg-emerald-500/20 text-emerald-300'
					: 'text-slate-400 hover:text-white'}"
			>
				<TrendingUp class="w-3.5 h-3.5" /> Net Worth
			</button>
			<button
				type="button"
				onclick={() => (activeTab = 'goals')}
				class="px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer {activeTab === 'goals'
					? 'bg-emerald-500/20 text-emerald-300'
					: 'text-slate-400 hover:text-white'}"
			>
				<Target class="w-3.5 h-3.5" /> Goals ({goals.length})
			</button>
			<button
				type="button"
				onclick={() => (activeTab = 'simulators')}
				class="px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer {activeTab === 'simulators'
					? 'bg-emerald-500/20 text-emerald-300'
					: 'text-slate-400 hover:text-white'}"
			>
				<Calculator class="w-3.5 h-3.5" /> Simulators
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}

	{#if loading}
		<div class="card-surface rounded-2xl h-64 animate-pulse"></div>
	{:else if activeTab === 'net_worth' && netWorth}
		<!-- NET WORTH TAB -->
		<div class="space-y-6">
			<div class="grid sm:grid-cols-3 gap-4">
				<div class="card-surface rounded-2xl p-5">
					<div class="text-xs text-slate-400">Current Net Worth</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-1.5">
						{formatMoney(netWorth.current_net_worth, netWorth.base_currency)}
					</div>
					{#if netWorth.change_amount !== null}
						<div class="text-xs font-mono-num mt-1 {Number.parseFloat(netWorth.change_amount) >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
							{Number.parseFloat(netWorth.change_amount) >= 0 ? '+' : ''}{formatMoney(netWorth.change_amount, netWorth.base_currency)}
							{#if netWorth.change_pct !== null}({netWorth.change_pct}%){/if} since first snapshot
						</div>
					{/if}
				</div>
				<div class="card-surface rounded-2xl p-5">
					<div class="text-xs text-slate-400">Total Assets</div>
					<div class="text-2xl font-bold font-mono-num text-emerald-400 mt-1.5">
						{formatMoney(netWorth.current_assets, netWorth.base_currency)}
					</div>
				</div>
				<div class="card-surface rounded-2xl p-5 flex items-center justify-between gap-4">
					<div>
						<div class="text-xs text-slate-400">Total Liabilities</div>
						<div class="text-2xl font-bold font-mono-num text-rose-400 mt-1.5">
							{formatMoney(netWorth.current_liabilities, netWorth.base_currency)}
						</div>
					</div>
					<button
						type="button"
						disabled={capturingSnapshot}
						onclick={handleSnapshot}
						class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						<Camera class="w-3.5 h-3.5" />
						{capturingSnapshot ? 'Saving...' : 'Capture Snapshot'}
					</button>
				</div>
			</div>

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
									<span class="font-mono-num font-semibold {acc.classification === 'liability' ? 'text-rose-400' : 'text-emerald-400'}">
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
							Click <strong>Capture Snapshot</strong> to record today's net worth and start building your wealth curve.
						</p>
					{:else}
						<div class="divide-y divide-slate-800/70">
							{#each [...netWorth.snapshots].reverse() as snap}
								<div class="py-2.5 flex items-center justify-between text-xs font-mono-num">
									<span class="text-slate-300">{formatDate(snap.snapshot_date)}</span>
									<div class="flex items-center gap-4">
										<span class="text-emerald-400/80">A: {formatMoney(snap.total_assets, netWorth.base_currency)}</span>
										<span class="text-rose-400/80">L: {formatMoney(snap.total_liabilities, netWorth.base_currency)}</span>
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
		<!-- FINANCIAL GOALS TAB -->
		<div class="space-y-4">
			<div class="flex justify-end">
				<button
					type="button"
					onclick={() => (showGoalModal = true)}
					class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer"
				>
					<Plus class="w-4 h-4" /> New Goal
				</button>
			</div>

			{#if goals.length === 0}
				<div class="card-surface rounded-2xl p-12 text-center space-y-3">
					<Target class="w-9 h-9 text-slate-500 mx-auto" />
					<h2 class="text-base font-semibold text-white">Set your first financial goal</h2>
					<p class="text-xs text-slate-400 max-w-md mx-auto">
						Track your Emergency Fund, House Down Payment, Debt-Free target, or Travel savings with automatic monthly pace projections.
					</p>
				</div>
			{:else}
				<div class="grid md:grid-cols-2 gap-4">
					{#each goals as g}
						<div class="card-surface rounded-2xl p-5 space-y-4">
							<div class="flex items-start justify-between gap-3">
								<div>
									<div class="flex items-center gap-2">
										<span class="font-semibold text-white">{g.name}</span>
										{#if g.is_completed}
											<span class="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 font-semibold">
												<CheckCircle2 class="w-3 h-3" /> Completed
											</span>
										{/if}
									</div>
									<div class="text-xs text-slate-400 capitalize mt-0.5">{g.goal_type.replace('_', ' ')}</div>
								</div>
								<div class="flex items-center gap-1.5">
									{#if !g.is_completed}
										<button
											type="button"
											onclick={() => handleContribute(g)}
											class="px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-xs font-semibold cursor-pointer"
										>
											+ Contribute
										</button>
									{/if}
									<button
										type="button"
										onclick={() => handleDeleteGoal(g)}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</div>
							</div>

							<div class="space-y-1.5">
								<div class="flex items-center justify-between text-xs font-mono-num">
									<span class="text-white font-semibold">{formatMoney(g.current_amount, baseCcy)}</span>
									<span class="text-slate-400">Target {formatMoney(g.target_amount, baseCcy)} ({g.progress_pct}%)</span>
								</div>
								<div class="h-2.5 rounded-full bg-slate-800 overflow-hidden">
									<div class="h-full rounded-full bg-emerald-400 transition-all" style="width: {g.progress_pct}%"></div>
								</div>
							</div>

							<div class="grid grid-cols-2 gap-2 pt-1 text-[11px] text-slate-400 font-mono-num">
								<div>
									Monthly plan: <span class="text-slate-200">{formatMoney(g.monthly_contribution, baseCcy)}/mo</span>
								</div>
								<div class="text-right">
									{#if g.projected_completion_date}
										Projected: <span class="text-cyan-300">{formatDate(g.projected_completion_date)}</span>
									{:else if g.required_monthly}
										Need: <span class="text-amber-300">{formatMoney(g.required_monthly, baseCcy)}/mo</span>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{:else if activeTab === 'simulators'}
		<!-- DETERMINISTIC SIMULATORS TAB -->
		<div class="grid lg:grid-cols-2 gap-6">
			<!-- Debt Payoff Comparator -->
			<div class="card-surface rounded-2xl p-6 space-y-4">
				<div class="flex items-center justify-between">
					<div>
						<h2 class="text-base font-semibold text-white">Debt Payoff: Snowball vs. Avalanche</h2>
						<p class="text-xs text-slate-400">Deterministic month-by-month amortization simulator.</p>
					</div>
					<button type="button" onclick={addDebtRow} class="text-xs text-emerald-400 hover:text-emerald-300 font-semibold cursor-pointer">
						+ Add Debt
					</button>
				</div>

				<div class="space-y-2.5">
					{#each debts as debt, i}
						<div class="grid grid-cols-12 gap-2 items-center">
							<input bind:value={debt.name} placeholder="Name" class="col-span-4 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white" />
							<input type="number" bind:value={debt.balance} placeholder="Balance" class="col-span-3 px-2 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
							<input type="number" step="0.1" bind:value={debt.apr} placeholder="APR %" class="col-span-2 px-2 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
							<input type="number" bind:value={debt.min_payment} placeholder="Min" class="col-span-2 px-2 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white font-mono-num" />
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
					<div class="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/25 rounded-xl p-3 font-mono-num">
						Avalanche saves <strong>{formatMoney(debtResult.interest_saved_by_avalanche, baseCcy)}</strong> in interest
						{#if debtResult.months_saved_by_avalanche > 0}and {debtResult.months_saved_by_avalanche} months{/if}.
						Order: {debtResult.avalanche.payoff_order.join(' → ')}
					</div>
				{/if}
			</div>

			<!-- What-If Cash Flow Simulator -->
			<div class="card-surface rounded-2xl p-6 space-y-4">
				<div>
					<h2 class="text-base font-semibold text-white">What-If Cash Flow & Wealth Simulator</h2>
					<p class="text-xs text-slate-400">Model raises, expense cuts, or major purchases over time.</p>
				</div>

				<div class="grid grid-cols-2 gap-3 text-xs">
					<div>
						<label for="wi-start" class="block text-slate-400 mb-1">Starting Savings</label>
						<input id="wi-start" type="number" bind:value={wiStarting} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
					</div>
					<div>
						<label for="wi-hor" class="block text-slate-400 mb-1">Horizon (Months)</label>
						<input id="wi-hor" type="number" min={1} max={120} bind:value={wiHorizon} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
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
						<label for="wi-dinc" class="block text-emerald-300 mb-1">Income Change (+/- per mo)</label>
						<input id="wi-dinc" type="number" bind:value={wiIncomeDelta} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-emerald-500/30 text-white font-mono-num" />
					</div>
					<div>
						<label for="wi-dexp" class="block text-cyan-300 mb-1">Expense Change (+/- per mo)</label>
						<input id="wi-dexp" type="number" bind:value={wiExpenseDelta} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-cyan-500/30 text-white font-mono-num" />
					</div>
					<div>
						<label for="wi-one" class="block text-slate-400 mb-1">One-Time Impact (+/-)</label>
						<input id="wi-one" type="number" bind:value={wiOneTime} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
					</div>
					<div>
						<label for="wi-ret" class="block text-slate-400 mb-1">Annual Yield (%)</label>
						<input id="wi-ret" type="number" step="0.1" bind:value={wiReturnPct} class="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono-num" />
					</div>
				</div>

				<button
					type="button"
					disabled={runningWhatIf}
					onclick={runWhatIfSim}
					class="w-full py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50"
				>
					{runningWhatIf ? 'Projecting...' : 'Run Projection'}
				</button>

				{#if whatIfResult}
					<div class="grid grid-cols-2 gap-3 pt-1">
						<div class="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
							<div class="text-[11px] text-slate-400">Baseline ({wiHorizon} mo)</div>
							<div class="text-lg font-bold font-mono-num text-slate-200 mt-0.5">
								{formatMoney(whatIfResult.baseline_end_balance, baseCcy)}
							</div>
							<div class="text-[11px] text-slate-500 font-mono-num">
								{formatMoney(whatIfResult.baseline_monthly_net, baseCcy)}/mo net
							</div>
						</div>
						<div class="p-3.5 rounded-xl bg-slate-950/70 border border-emerald-500/35">
							<div class="text-[11px] text-emerald-300">What-If Scenario ({wiHorizon} mo)</div>
							<div class="text-lg font-bold font-mono-num text-white mt-0.5">
								{formatMoney(whatIfResult.scenario_end_balance, baseCcy)}
							</div>
							<div class="text-[11px] text-emerald-400 font-mono-num">
								{formatMoney(whatIfResult.scenario_monthly_net, baseCcy)}/mo net
							</div>
						</div>
					</div>

					<div class="p-3 rounded-xl text-xs font-mono-num {Number.parseFloat(whatIfResult.net_impact) >= 0 ? 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-300' : 'bg-rose-500/10 border border-rose-500/25 text-rose-300'}">
						Net {wiHorizon}-month impact:
						<strong>
							{Number.parseFloat(whatIfResult.net_impact) >= 0 ? '+' : ''}{formatMoney(whatIfResult.net_impact, baseCcy)}
						</strong>
						{#if whatIfResult.scenario_runway_months !== null}
							· Cash runway: <strong>{whatIfResult.scenario_runway_months} months</strong>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<!-- Create Goal Modal -->
{#if showGoalModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Create Financial Goal</h2>
				<button type="button" onclick={() => (showGoalModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleCreateGoal} class="space-y-4">
				<div>
					<label for="g-name" class="block text-xs font-medium text-slate-300 mb-1">Goal Name</label>
					<input id="g-name" type="text" required bind:value={goalName} placeholder="e.g., 6-Month Emergency Fund" class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white" />
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="g-type" class="block text-xs font-medium text-slate-300 mb-1">Type</label>
						<select id="g-type" bind:value={goalType} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white">
							<option value="emergency_fund">Emergency Fund</option>
							<option value="savings">General Savings</option>
							<option value="purchase">Major Purchase</option>
							<option value="debt_payoff">Debt Payoff</option>
							<option value="investment">Investment</option>
							<option value="retirement">Retirement</option>
						</select>
					</div>
					<div>
						<label for="g-date" class="block text-xs font-medium text-slate-300 mb-1">Target Date (opt.)</label>
						<input id="g-date" type="date" bind:value={goalTargetDate} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white" />
					</div>
				</div>

				<div class="grid grid-cols-3 gap-2.5">
					<div>
						<label for="g-target" class="block text-xs font-medium text-slate-300 mb-1">Target</label>
						<input id="g-target" type="number" step="0.01" min="1" required bind:value={goalTarget} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
					<div>
						<label for="g-curr" class="block text-xs font-medium text-slate-300 mb-1">Saved Now</label>
						<input id="g-curr" type="number" step="0.01" min="0" bind:value={goalCurrent} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
					<div>
						<label for="g-mo" class="block text-xs font-medium text-slate-300 mb-1">Monthly Plan</label>
						<input id="g-mo" type="number" step="0.01" min="0" bind:value={goalMonthly} class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num" />
					</div>
				</div>

				<div class="flex justify-end gap-2.5 pt-2">
					<button type="button" onclick={() => (showGoalModal = false)} class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={savingGoal} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50">
						{savingGoal ? 'Creating...' : 'Create Goal'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
