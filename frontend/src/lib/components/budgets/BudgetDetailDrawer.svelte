<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type { BudgetOverview, BudgetStatus, Transaction } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		X,
		Save,
		Trash2,
		Sparkles,
		RefreshCw,
		Flame,
		TrendingUp,
		ArrowUpRight,
		CheckCircle2,
		AlertTriangle
	} from 'lucide-svelte';

	let {
		budget = null,
		overview = null,
		currency = 'USD',
		privacyMode = false,
		onClose,
		onUpdated,
		onRequestDelete
	}: {
		budget: BudgetStatus | null;
		overview: BudgetOverview | null;
		currency: string;
		privacyMode?: boolean;
		onClose: () => void;
		onUpdated: (nextOverview: BudgetOverview) => void;
		onRequestDelete: (b: BudgetStatus) => void;
	} = $props();

	let editAmount = $state('');
	let editRollover = $state(false);
	let editThreshold = $state(80);
	let saving = $state(false);
	let error = $state<string | null>(null);

	let txs = $state<Transaction[]>([]);
	let loadingTxs = $state(false);

	function monthRange(yyyyMm: string): { from: string; to: string } {
		const [yStr, mStr] = yyyyMm.split('-');
		const y = Number(yStr);
		const m = Number(mStr);
		const lastDay = new Date(y, m, 0).getDate();
		return {
			from: `${yStr}-${mStr}-01`,
			to: `${yStr}-${mStr}-${String(lastDay).padStart(2, '0')}`
		};
	}

	$effect(() => {
		if (!budget || !overview) {
			txs = [];
			return;
		}
		editAmount = budget.amount;
		editRollover = budget.rollover;
		editThreshold = budget.alert_threshold_pct;
		error = null;

		const catId = budget.category_id;
		const range = monthRange(overview.month);
		loadingTxs = true;
		api
			.listTransactions({
				category_id: catId,
				direction: 'outflow',
				date_from: range.from,
				date_to: range.to,
				limit: 50
			})
			.then((res) => {
				if (budget?.category_id === catId) {
					txs = res.items.filter((t) => !t.is_transfer);
				}
			})
			.catch(() => {
				txs = [];
			})
			.finally(() => {
				loadingTxs = false;
			});
	});

	let forecast = $derived.by(() => {
		if (!budget || !overview) {
			return { spent: 0, limit: 0, remaining: 0, dailyBurn: 0, dailyAllow: 0, projectedEom: 0, daysLeft: 1 };
		}
		const spent = Number.parseFloat(budget.spent) || 0;
		const limit = Number.parseFloat(budget.effective_limit) || 0;
		const remaining = Number.parseFloat(budget.remaining) || 0;
		const elapsed = Math.max(1, overview.days_elapsed);
		const daysLeft = Math.max(1, overview.days_in_month - overview.days_elapsed + 1);
		const dailyBurn = spent / elapsed;
		const dailyAllow = remaining / daysLeft;
		const projectedEom = dailyBurn * overview.days_in_month;
		return { spent, limit, remaining, dailyBurn, dailyAllow, projectedEom, daysLeft };
	});

	function nudgeLimit(factor: number) {
		const cur = Number.parseFloat(editAmount) || 0;
		if (cur <= 0) return;
		const next = Math.max(5, Math.round(cur * factor));
		editAmount = next.toFixed(2);
	}

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		if (!budget) return;
		const num = Number.parseFloat(editAmount);
		if (!num || num <= 0) {
			error = 'Enter a valid positive budget limit.';
			return;
		}
		saving = true;
		error = null;
		try {
			const updatedOv = await api.updateBudget(budget.id, {
				amount: num.toFixed(2),
				rollover: editRollover,
				alert_threshold_pct: editThreshold
			});
			onUpdated(updatedOv);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to update budget';
		} finally {
			saving = false;
		}
	}
</script>

{#if budget && overview}
	<div class="fixed inset-0 z-50 flex justify-end">
		<button
			type="button"
			onclick={onClose}
			aria-label="Close budget inspector"
			class="fixed inset-0 bg-black/65 backdrop-blur-xs cursor-pointer"
		></button>

		<aside class="relative z-10 w-full max-w-md bg-slate-950 border-l border-slate-800/90 h-dvh flex flex-col shadow-2xl overflow-hidden">
			<div class="h-1.5 w-full shrink-0" style="background-color: {budget.category_color}"></div>

			<!-- Header -->
			<div class="p-5 border-b border-slate-800/80 flex items-start justify-between gap-3 shrink-0">
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full shrink-0" style="background-color: {budget.category_color}"></span>
						<h2 class="text-base font-bold text-white truncate">{budget.category_name}</h2>
					</div>
					<p class="text-xs text-slate-400 mt-0.5">
						{overview.month} · Day {overview.days_elapsed} of {overview.days_in_month} ({overview.pace_pct}% elapsed)
					</p>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer shrink-0"
					aria-label="Close drawer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<!-- Scrollable Content -->
			<div class="flex-1 overflow-y-auto p-5 space-y-5">
				{#if error}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
						{error}
					</div>
				{/if}

				<!-- Live Pace & Forecast Card -->
				<div class="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3.5">
					<div class="flex items-baseline justify-between gap-2">
						<div>
							<div class="text-[11px] text-slate-400">Spent vs. Effective Limit</div>
							<div class="text-2xl font-bold font-mono-num text-white mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(forecast.spent, currency)}
								<span class="text-sm font-normal text-slate-400">
									/ {formatMoney(forecast.limit, currency)}
								</span>
							</div>
						</div>
						<span
							class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border {budget.status === 'over_budget'
								? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
								: budget.status === 'warning' || budget.status === 'pacing_fast'
									? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
									: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'}"
						>
							{#if budget.status === 'on_track'}
								<CheckCircle2 class="w-3 h-3" /> On Track
							{:else if budget.status === 'over_budget'}
								<AlertTriangle class="w-3 h-3" /> Over
							{:else}
								<AlertTriangle class="w-3 h-3" /> Fast
							{/if}
						</span>
					</div>

					<!-- Pacing Bar -->
					<div class="space-y-1">
						<div class="relative h-2.5 rounded-full bg-slate-800 overflow-visible">
							<div
								class="h-full rounded-full transition-all"
								style="width: {Math.min(budget.percent_used, 100)}%; background-color: {budget.status === 'over_budget'
									? '#f43f5e'
									: budget.status === 'warning' || budget.status === 'pacing_fast'
										? '#f59e0b'
										: budget.category_color}"
							></div>
							<div
								title="Today's month pace ({overview.pace_pct}%)"
								class="absolute -top-1 w-0.5 h-4.5 bg-white/85 rounded-full"
								style="left: {Math.min(overview.pace_pct, 100)}%"
							></div>
						</div>
						<div class="flex items-center justify-between text-[10px] font-mono-num text-slate-400">
							<span>{budget.percent_used}% used</span>
							<span>Month pace {overview.pace_pct}%</span>
						</div>
					</div>

					<!-- 3 Forecast Metrics -->
					<div class="grid grid-cols-3 gap-2 pt-3 border-t border-slate-800/80 text-xs">
						<div>
							<div class="text-[10px] text-slate-500 flex items-center gap-1">
								<Flame class="w-3 h-3 text-amber-400" /> Burn/day
							</div>
							<div class="font-mono-num font-semibold text-slate-200 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
								{formatMoney(forecast.dailyBurn, currency)}
							</div>
						</div>
						<div>
							<div class="text-[10px] text-slate-500">Allow/day</div>
							<div
								class="font-mono-num font-semibold mt-0.5 {forecast.dailyAllow >= 0
									? 'text-emerald-400'
									: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{formatMoney(Math.max(0, forecast.dailyAllow), currency)}
							</div>
						</div>
						<div>
							<div class="text-[10px] text-slate-500 flex items-center gap-1">
								<TrendingUp class="w-3 h-3 text-cyan-400" /> EOM Est.
							</div>
							<div
								class="font-mono-num font-semibold mt-0.5 {forecast.projectedEom > forecast.limit
									? 'text-rose-400'
									: 'text-cyan-300'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{formatMoney(forecast.projectedEom, currency)}
							</div>
						</div>
					</div>
				</div>

				<!-- Inline Quick-Edit Form -->
				<form id="budget-inline-form" onsubmit={handleSave} class="p-4 rounded-2xl bg-slate-900/50 border border-slate-800/90 space-y-3.5">
					<div class="text-xs font-semibold text-white">Adjust Limit & Rules</div>

					<div class="space-y-1.5">
						<div class="flex items-center justify-between">
							<label for="dr-amt" class="text-[11px] text-slate-400">Monthly Limit ({currency})</label>
							<div class="flex items-center gap-1">
								<button
									type="button"
									onclick={() => nudgeLimit(0.9)}
									class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] font-mono-num text-slate-300 cursor-pointer"
								>
									-10%
								</button>
								<button
									type="button"
									onclick={() => nudgeLimit(1.1)}
									class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] font-mono-num text-slate-300 cursor-pointer"
								>
									+10%
								</button>
							</div>
						</div>
						<input
							id="dr-amt"
							type="number"
							step="0.01"
							min="1"
							required
							bind:value={editAmount}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono-num font-semibold text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>

					<div class="grid grid-cols-2 gap-3 items-center">
						<div>
							<label for="dr-thresh" class="block text-[11px] text-slate-400 mb-1">Warning Alert (%)</label>
							<input
								id="dr-thresh"
								type="number"
								min={10}
								max={100}
								bind:value={editThreshold}
								class="w-full px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white focus:outline-none focus:border-emerald-500"
							/>
						</div>
						<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer pt-4">
							<input type="checkbox" bind:checked={editRollover} class="rounded border-slate-700" />
							<RefreshCw class="w-3.5 h-3.5 text-cyan-400" />
							Rollover unused
						</label>
					</div>

					<button
						type="submit"
						disabled={saving}
						class="w-full inline-flex items-center justify-center gap-1.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
					>
						<Save class="w-3.5 h-3.5" />
						{saving ? 'Saving...' : 'Save Budget Changes'}
					</button>
				</form>

				<!-- Contributing Transactions This Month -->
				<div class="space-y-2.5">
					<div class="flex items-center justify-between">
						<h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400">
							{overview.month} Transactions ({txs.length})
						</h3>
						<a
							href="/transactions"
							class="text-xs font-medium text-emerald-400 hover:text-emerald-300"
						>
							Full Ledger →
						</a>
					</div>

					{#if loadingTxs}
						<div class="space-y-2">
							{#each Array(3) as _}
								<div class="h-11 rounded-xl bg-slate-900/70 animate-pulse"></div>
							{/each}
						</div>
					{:else if txs.length === 0}
						<div class="p-5 rounded-xl bg-slate-900/50 border border-slate-800/80 text-center text-xs text-slate-500">
							No expenses recorded in {budget.category_name} for {overview.month}.
						</div>
					{:else}
						<div class="divide-y divide-slate-800/70 rounded-xl bg-slate-900/50 border border-slate-800/80 px-3.5">
							{#each txs as tx}
								<div class="py-2.5 flex items-center justify-between gap-2.5">
									<div class="flex items-center gap-2.5 min-w-0">
										<div class="h-7 w-7 rounded-lg bg-slate-800 text-slate-300 flex items-center justify-center shrink-0">
											<ArrowUpRight class="w-3.5 h-3.5" />
										</div>
										<div class="min-w-0">
											<div class="text-xs font-medium text-white truncate">{tx.merchant_clean}</div>
											<div class="text-[10px] text-slate-400">{formatDate(tx.occurred_at)}</div>
										</div>
									</div>
									<span class="text-xs font-mono-num font-semibold text-slate-200 shrink-0 {privacyMode ? 'privacy-blur' : ''}">
										-{formatMoney(tx.amount, tx.currency)}
									</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Footer Actions -->
			<div class="p-4 border-t border-slate-800/80 bg-slate-950 flex items-center justify-between gap-2 shrink-0">
				<button
					type="button"
					onclick={() =>
						budget &&
						overview &&
						goto(
							`/advisor?q=${encodeURIComponent(
								`My "${budget.category_name}" budget is ${budget.percent_used}% used (${budget.spent} of ${budget.effective_limit} ${currency}) on Day ${overview.days_elapsed} of ${overview.days_in_month}. How should I adjust my spending or limit for the rest of the month?`
							)}`
						)}
					class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer"
				>
					<Sparkles class="w-3.5 h-3.5" /> Ask Luna to Optimize
				</button>
				<button
					type="button"
					onclick={() => budget && onRequestDelete(budget)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-semibold cursor-pointer"
				>
					<Trash2 class="w-3.5 h-3.5" /> Remove
				</button>
			</div>
		</aside>
	</div>
{/if}
