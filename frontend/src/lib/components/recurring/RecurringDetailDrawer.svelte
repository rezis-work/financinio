<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type { Category, RecurringCadence, RecurringItem, Transaction } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import {
		X,
		Save,
		Trash2,
		Sparkles,
		CheckCircle2,
		Pause,
		Play,
		AlertTriangle,
		ArrowUpRight,
		ArrowDownRight,
		History
	} from 'lucide-svelte';

	let {
		item = null,
		categories,
		privacyMode = false,
		onClose,
		onSaved,
		onMarkPaid,
		onRequestDelete
	}: {
		item: RecurringItem | null;
		categories: Category[];
		privacyMode?: boolean;
		onClose: () => void;
		onSaved: () => Promise<void> | void;
		onMarkPaid: (item: RecurringItem) => void;
		onRequestDelete: (item: RecurringItem) => void;
	} = $props();

	let merchantName = $state('');
	let amount = $state('');
	let cadence = $state<RecurringCadence>('monthly');
	let nextDueDate = $state('');
	let categoryId = $state('');
	let isSubscription = $state(true);
	let isActive = $state(true);
	let saving = $state(false);
	let error = $state<string | null>(null);

	let historyTxs = $state<Transaction[]>([]);
	let loadingHistory = $state(false);

	$effect(() => {
		if (!item) {
			historyTxs = [];
			return;
		}
		merchantName = item.merchant_name;
		amount = item.amount;
		cadence = item.cadence;
		nextDueDate = item.next_due_date;
		categoryId = item.category_id ?? '';
		isSubscription = item.is_subscription;
		isActive = item.is_active;
		error = null;

		const query = item.merchant_name;
		const id = item.id;
		loadingHistory = true;
		api
			.listTransactions({ search: query, limit: 12 })
			.then((res) => {
				if (item?.id === id) historyTxs = res.items;
			})
			.catch(() => {
				historyTxs = [];
			})
			.finally(() => {
				loadingHistory = false;
			});
	});

	let costStats = $derived.by(() => {
		if (!item) return { monthly: 0, annual: 0, fiveYrOpp: 0 };
		const monthly = Number.parseFloat(item.monthly_equivalent) || 0;
		const annual = monthly * 12;
		const r = 0.07 / 12;
		const fiveYrOpp = monthly * ((Math.pow(1 + r, 60) - 1) / r);
		return { monthly, annual, fiveYrOpp };
	});

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		if (!item) return;
		const num = Number.parseFloat(amount);
		if (!num || num <= 0) {
			error = 'Enter a valid positive amount.';
			return;
		}
		saving = true;
		error = null;
		try {
			await api.updateRecurring(item.id, {
				merchant_name: merchantName.trim(),
				amount: num.toFixed(2),
				cadence,
				next_due_date: nextDueDate,
				category_id: categoryId || null,
				is_subscription: isSubscription,
				is_active: isActive
			});
			await onSaved();
			onClose();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to update recurring item';
		} finally {
			saving = false;
		}
	}
</script>

{#if item}
	<div class="fixed inset-0 z-50 flex justify-end">
		<button
			type="button"
			onclick={onClose}
			aria-label="Close recurring inspector"
			class="fixed inset-0 bg-black/65 backdrop-blur-xs cursor-pointer"
		></button>

		<aside class="relative z-10 w-full max-w-md bg-slate-950 border-l border-slate-800/90 h-dvh flex flex-col shadow-2xl overflow-hidden">
			<!-- Header -->
			<div class="p-5 border-b border-slate-800/80 flex items-start justify-between gap-3 shrink-0">
				<div class="min-w-0">
					<div class="flex items-center gap-2 flex-wrap">
						<h2 class="text-base font-bold text-white truncate">{item.merchant_name}</h2>
						<span class="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] font-semibold text-slate-300 capitalize">
							{item.cadence}
						</span>
						{#if !item.is_active}
							<span class="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 text-[10px] font-semibold">
								Paused
							</span>
						{/if}
					</div>
					<div
						class="text-2xl font-bold font-mono-num mt-1 {item.direction === 'inflow'
							? 'text-emerald-400'
							: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
					>
						{item.direction === 'inflow' ? '+' : '-'}{formatMoney(item.amount, item.currency)}
					</div>
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

			<!-- Scrollable Body -->
			<div class="flex-1 overflow-y-auto p-5 space-y-5">
				{#if error}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
						{error}
					</div>
				{/if}

				{#if item.price_change_pct && Number.parseFloat(item.price_change_pct) > 1}
					<div class="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 flex items-start gap-2.5">
						<AlertTriangle class="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
						<div>
							<div class="font-semibold">Price Hike Detected (+{item.price_change_pct}%)</div>
							<div class="text-[11px] text-amber-200/80 mt-0.5">
								Previously {formatMoney(item.previous_amount || '0', item.currency)} → now {formatMoney(item.amount, item.currency)}.
							</div>
						</div>
					</div>
				{/if}

				<!-- Cost Breakdown & 5-Yr Opportunity Cost -->
				<div class="grid grid-cols-3 gap-2 p-3.5 rounded-2xl bg-slate-900/75 border border-slate-800 text-xs">
					<div>
						<div class="text-[10px] text-slate-500">Monthly Eq.</div>
						<div class="font-mono-num font-semibold text-white mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(costStats.monthly, item.currency)}
						</div>
					</div>
					<div>
						<div class="text-[10px] text-slate-500">Annual Cost</div>
						<div class="font-mono-num font-semibold text-slate-200 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(costStats.annual, item.currency)}
						</div>
					</div>
					<div>
						<div class="text-[10px] text-slate-500">5-Yr @ 7%</div>
						<div class="font-mono-num font-semibold text-amber-300 mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(costStats.fiveYrOpp, item.currency)}
						</div>
					</div>
				</div>

				<!-- 1-Click Mark Paid -->
				{#if item.is_active}
					<button
						type="button"
						onclick={() => item && onMarkPaid(item)}
						class="w-full py-2.5 px-4 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-2 transition cursor-pointer"
					>
						<CheckCircle2 class="w-4 h-4" />
						Mark Paid & Advance Next Due Date
					</button>
				{/if}

				<!-- Inline Edit Form -->
				<form id="rec-edit-form" onsubmit={handleSave} class="p-4 rounded-2xl bg-slate-900/50 border border-slate-800/90 space-y-3.5">
					<div class="text-xs font-semibold text-white">Edit Schedule & Details</div>

					<div>
						<label for="dr-rec-name" class="block text-[11px] text-slate-400 mb-1">Merchant / Name</label>
						<input
							id="dr-rec-name"
							type="text"
							required
							bind:value={merchantName}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="dr-rec-amt" class="block text-[11px] text-slate-400 mb-1">
								Amount ({item.currency})
							</label>
							<input
								id="dr-rec-amt"
								type="number"
								step="0.01"
								min="0.01"
								required
								bind:value={amount}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white focus:outline-none focus:border-emerald-500"
							/>
						</div>
						<div>
							<label for="dr-rec-cad" class="block text-[11px] text-slate-400 mb-1">Cadence</label>
							<select
								id="dr-rec-cad"
								bind:value={cadence}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							>
								<option value="weekly">Weekly</option>
								<option value="biweekly">Bi-Weekly</option>
								<option value="monthly">Monthly</option>
								<option value="quarterly">Quarterly</option>
								<option value="yearly">Yearly</option>
							</select>
						</div>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="dr-rec-due" class="block text-[11px] text-slate-400 mb-1">Next Due Date</label>
							<input
								id="dr-rec-due"
								type="date"
								required
								bind:value={nextDueDate}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							/>
						</div>
						<div>
							<label for="dr-rec-cat" class="block text-[11px] text-slate-400 mb-1">Category</label>
							<select
								id="dr-rec-cat"
								bind:value={categoryId}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
							>
								<option value="">Uncategorized</option>
								{#each categories as cat}
									<option value={cat.id}>{cat.name}</option>
								{/each}
							</select>
						</div>
					</div>

					<div class="flex items-center justify-between gap-3 pt-1 text-xs">
						<label class="flex items-center gap-2 text-slate-300 cursor-pointer">
							<input type="checkbox" bind:checked={isSubscription} class="rounded border-slate-700" />
							Subscription
						</label>
						<button
							type="button"
							onclick={() => (isActive = !isActive)}
							class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border text-[11px] font-semibold cursor-pointer {isActive
								? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
								: 'bg-amber-500/10 border-amber-500/30 text-amber-300'}"
						>
							{#if isActive}
								<Pause class="w-3 h-3" /> Active
							{:else}
								<Play class="w-3 h-3" /> Paused
							{/if}
						</button>
					</div>

					<button
						type="submit"
						disabled={saving}
						class="w-full inline-flex items-center justify-center gap-1.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
					>
						<Save class="w-3.5 h-3.5" />
						{saving ? 'Saving...' : 'Save Changes'}
					</button>
				</form>

				<!-- Real Payment History from Ledger -->
				<div class="space-y-2.5">
					<div class="flex items-center justify-between">
						<h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
							<History class="w-3.5 h-3.5" /> Ledger Charge History ({historyTxs.length})
						</h3>
					</div>

					{#if loadingHistory}
						<div class="space-y-2">
							{#each Array(3) as _}
								<div class="h-10 rounded-xl bg-slate-900/70 animate-pulse"></div>
							{/each}
						</div>
					{:else if historyTxs.length === 0}
						<div class="p-4 rounded-xl bg-slate-900/50 border border-slate-800/80 text-center text-xs text-slate-500">
							No matching historical transactions found for "{item.merchant_name}".
						</div>
					{:else}
						<div class="divide-y divide-slate-800/70 rounded-xl bg-slate-900/50 border border-slate-800/80 px-3.5">
							{#each historyTxs as tx}
								<div class="py-2.5 flex items-center justify-between gap-2.5">
									<div class="flex items-center gap-2 min-w-0">
										<div
											class="h-6 w-6 rounded-md flex items-center justify-center shrink-0 {tx.direction === 'inflow'
												? 'bg-emerald-500/15 text-emerald-400'
												: 'bg-slate-800 text-slate-300'}"
										>
											{#if tx.direction === 'inflow'}
												<ArrowDownRight class="w-3 h-3" />
											{:else}
												<ArrowUpRight class="w-3 h-3" />
											{/if}
										</div>
										<div class="min-w-0">
											<div class="text-xs font-medium text-white truncate">{tx.merchant_clean}</div>
											<div class="text-[10px] text-slate-400">{formatDate(tx.occurred_at)}</div>
										</div>
									</div>
									<span class="text-xs font-mono-num font-semibold text-slate-200 shrink-0 {privacyMode ? 'privacy-blur' : ''}">
										{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
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
						item &&
						goto(
							`/advisor?q=${encodeURIComponent(
								`Is my "${item.merchant_name}" recurring ${item.is_subscription ? 'subscription' : 'bill'} (${item.monthly_equivalent} ${item.currency}/mo, ${costStats.annual.toFixed(2)}/yr) worth keeping given my current savings rate and budget? Suggest cheaper alternatives if possible.`
							)}`
						)}
					class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer"
				>
					<Sparkles class="w-3.5 h-3.5" /> Audit with Luna
				</button>
				<button
					type="button"
					onclick={() => item && onRequestDelete(item)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-semibold cursor-pointer"
				>
					<Trash2 class="w-3.5 h-3.5" /> Delete
				</button>
			</div>
		</aside>
	</div>
{/if}
