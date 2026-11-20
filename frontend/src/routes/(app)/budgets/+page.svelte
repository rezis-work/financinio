<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { BudgetOverview, BudgetStatus, Category } from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatMoney } from '$lib/utils/format';
	import {
		Plus,
		Sparkles,
		Trash2,
		AlertTriangle,
		CheckCircle2,
		RefreshCw,
		X
	} from 'lucide-svelte';

	let overview = $state<BudgetOverview | null>(null);
	let categories = $state<Category[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Modals
	let showCreateModal = $state(false);
	let showTemplateModal = $state(false);
	let formCategoryId = $state('');
	let formAmount = $state('');
	let formRollover = $state(false);
	let formThreshold = $state(80);
	let templateIncome = $state('5000.00');
	let saving = $state(false);

	let baseCcy = $derived(auth.user?.base_currency || 'USD');
	let expenseCategories = $derived(categories.filter((c) => c.kind === 'expense'));

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [ov, cats] = await Promise.all([api.getBudgets(), api.listCategories()]);
			overview = ov;
			categories = cats;
			if (!formCategoryId) {
				const firstExp = cats.find((c) => c.kind === 'expense');
				if (firstExp) formCategoryId = firstExp.id;
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load budgets';
		} finally {
			loading = false;
		}
	}

	onMount(loadData);

	async function handleSaveBudget(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		try {
			overview = await api.upsertBudget({
				category_id: formCategoryId,
				amount: formAmount,
				period: 'monthly',
				rollover: formRollover,
				alert_threshold_pct: formThreshold
			});
			showCreateModal = false;
			formAmount = '';
			formRollover = false;
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
		try {
			overview = await api.apply503020Template(templateIncome);
			showTemplateModal = false;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to apply 50/30/20 template';
		} finally {
			saving = false;
		}
	}

	async function handleDelete(b: BudgetStatus) {
		if (!confirm(`Remove monthly budget for "${b.category_name}"?`)) return;
		await api.deleteBudget(b.id);
		overview = await api.getBudgets();
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
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Monthly Budgets & Pacing</h1>
			<p class="text-sm text-slate-400 mt-0.5">
				Track category spending limits, unused rollover balances, and real-time month pacing.
			</p>
		</div>
		<div class="flex items-center gap-2.5">
			<button
				type="button"
				onclick={() => (showTemplateModal = true)}
				class="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-sm font-medium text-slate-200 transition cursor-pointer"
			>
				<Sparkles class="w-4 h-4 text-cyan-400" />
				50/30/20 Setup
			</button>
			<button
				type="button"
				onclick={() => (showCreateModal = true)}
				class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer"
			>
				<Plus class="w-4 h-4" />
				Set Budget
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<div class="card-surface rounded-2xl h-28 animate-pulse"></div>
			{/each}
		</div>
	{:else if overview}
		<!-- Summary KPIs -->
		<div class="grid sm:grid-cols-3 gap-4">
			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Total Budgeted ({overview.month})</div>
				<div class="text-2xl font-bold font-mono-num text-white mt-1.5">
					{formatMoney(overview.total_budgeted, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1">
					Day {overview.days_elapsed} of {overview.days_in_month} ({overview.pace_pct}% through month)
				</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Total Spent</div>
				<div class="text-2xl font-bold font-mono-num text-rose-400 mt-1.5">
					{formatMoney(overview.total_spent, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1">
					Across {overview.budgets.length} budgeted {overview.budgets.length === 1 ? 'category' : 'categories'}
				</div>
			</div>

			<div class="card-surface rounded-2xl p-5">
				<div class="text-xs text-slate-400">Remaining Safe-to-Spend</div>
				<div
					class="text-2xl font-bold font-mono-num mt-1.5 {Number.parseFloat(overview.total_remaining) < 0
						? 'text-rose-400'
						: 'text-emerald-400'}"
				>
					{formatMoney(overview.total_remaining, baseCcy)}
				</div>
				<div class="text-xs text-slate-400 mt-1">Includes active rollover carry</div>
			</div>
		</div>

		{#if overview.budgets.length === 0}
			<div class="card-surface rounded-2xl p-12 text-center space-y-3">
				<h2 class="text-lg font-semibold text-white">No budgets configured yet</h2>
				<p class="text-sm text-slate-400 max-w-md mx-auto">
					Set individual category limits or auto-generate a balanced 50/30/20 plan from your monthly income in one click.
				</p>
				<div class="flex items-center justify-center gap-3 pt-2">
					<button
						type="button"
						onclick={() => (showTemplateModal = true)}
						class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white cursor-pointer"
					>
						Apply 50/30/20 Template
					</button>
					<button
						type="button"
						onclick={() => (showCreateModal = true)}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-slate-950 cursor-pointer"
					>
						Create Custom Budget
					</button>
				</div>
			</div>
		{:else}
			<div class="grid md:grid-cols-2 gap-4">
				{#each overview.budgets as b}
					{@const pill = statusPill(b.status)}
					<div class="card-surface rounded-2xl p-5 space-y-4">
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-2.5">
								<span class="w-3 h-3 rounded-full shrink-0" style="background-color: {b.category_color}"></span>
								<div>
									<div class="font-semibold text-white flex items-center gap-2">
										{b.category_name}
										{#if b.rollover}
											<span class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300">
												<RefreshCw class="w-2.5 h-2.5" /> Rollover
											</span>
										{/if}
									</div>
									<div class="text-xs text-slate-400 font-mono-num mt-0.5">
										{formatMoney(b.spent, baseCcy)} of {formatMoney(b.effective_limit, baseCcy)}
										{#if Number.parseFloat(b.rollover_carry) > 0}
											<span class="text-cyan-400">(+{formatMoney(b.rollover_carry, baseCcy)} carried)</span>
										{/if}
									</div>
								</div>
							</div>

							<div class="flex items-center gap-2">
								<span class="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border {pill.cls}">
									{#if b.status === 'on_track'}
										<CheckCircle2 class="w-3 h-3" />
									{:else}
										<AlertTriangle class="w-3 h-3" />
									{/if}
									{pill.label}
								</span>
								<button
									type="button"
									onclick={() => handleDelete(b)}
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
								<!-- Pace marker showing today's position in the month -->
								<div
									title="Today's month pace: {b.pace_pct}%"
									class="absolute -top-1 w-0.5 h-4.5 bg-white/80 rounded-full"
									style="left: {Math.min(b.pace_pct, 100)}%"
								></div>
							</div>
							<div class="flex items-center justify-between text-[11px] text-slate-400 font-mono-num">
								<span>{b.percent_used}% used (pace {b.pace_pct}%)</span>
								<span class="{Number.parseFloat(b.remaining) < 0 ? 'text-rose-400 font-semibold' : 'text-emerald-400'}">
									{Number.parseFloat(b.remaining) < 0
										? `${formatMoney(Math.abs(Number.parseFloat(b.remaining)), baseCcy)} over`
										: `${formatMoney(b.remaining, baseCcy)} left`}
								</span>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<!-- Create / Upsert Budget Modal -->
{#if showCreateModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Set Category Budget</h2>
				<button type="button" onclick={() => (showCreateModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleSaveBudget} class="space-y-4">
				<div>
					<label for="b-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
					<select
						id="b-cat"
						required
						bind:value={formCategoryId}
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
					>
						{#each expenseCategories as cat}
							<option value={cat.id}>{cat.name}</option>
						{/each}
					</select>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="b-amt" class="block text-xs font-medium text-slate-300 mb-1">Monthly Limit ({baseCcy})</label>
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
						<label for="b-thresh" class="block text-xs font-medium text-slate-300 mb-1">Warning At (%)</label>
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
					<input type="checkbox" bind:checked={formRollover} />
					Rollover unused balance from previous month into next month
				</label>

				<div class="flex justify-end gap-2.5 pt-2">
					<button type="button" onclick={() => (showCreateModal = false)} class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={saving} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50">
						{saving ? 'Saving...' : 'Save Budget'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- 50/30/20 Template Modal -->
{#if showTemplateModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">50/30/20 Smart Budget Setup</h2>
				<button type="button" onclick={() => (showTemplateModal = false)} class="text-slate-400 hover:text-white cursor-pointer">
					<X class="w-5 h-5" />
				</button>
			</div>
			<p class="text-xs text-slate-400 leading-relaxed">
				Allocates 50% of your take-home income across Needs (Housing, Groceries, Utilities, Transit, Healthcare) and 30% across Wants (Dining, Shopping, Entertainment, Subscriptions, Travel), reserving 20% for Savings & Debt Payoff.
			</p>
			<form onsubmit={handleApplyTemplate} class="space-y-4">
				<div>
					<label for="tpl-inc" class="block text-xs font-medium text-slate-300 mb-1">Monthly Net Income ({baseCcy})</label>
					<input
						id="tpl-inc"
						type="number"
						step="0.01"
						min="100"
						required
						bind:value={templateIncome}
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num"
					/>
				</div>
				<div class="flex justify-end gap-2.5">
					<button type="button" onclick={() => (showTemplateModal = false)} class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer">
						Cancel
					</button>
					<button type="submit" disabled={saving} class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50">
						{saving ? 'Applying...' : 'Generate Budgets'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
