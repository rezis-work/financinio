<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Account, RecurringItem } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import { X, CheckCircle2, ArrowRight } from 'lucide-svelte';

	let {
		open = $bindable(false),
		item = null,
		accounts,
		onDone
	}: {
		open: boolean;
		item: RecurringItem | null;
		accounts: Account[];
		onDone: (msg: string) => Promise<void> | void;
	} = $props();

	let logToLedger = $state(true);
	let accountId = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	function computeNextDue(iso: string, cadence: RecurringItem['cadence']): string {
		const [y, m, d] = iso.split('-').map(Number);
		const dt = new Date(y, m - 1, d);
		if (cadence === 'weekly') dt.setDate(dt.getDate() + 7);
		else if (cadence === 'biweekly') dt.setDate(dt.getDate() + 14);
		else if (cadence === 'monthly') dt.setMonth(dt.getMonth() + 1);
		else if (cadence === 'quarterly') dt.setMonth(dt.getMonth() + 3);
		else if (cadence === 'yearly') dt.setFullYear(dt.getFullYear() + 1);
		return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
	}

	let nextDue = $derived(item ? computeNextDue(item.next_due_date, item.cadence) : '');

	$effect(() => {
		if (open && item) {
			error = null;
			logToLedger = accounts.length > 0;
			const matching =
				accounts.find((a) => a.id === item.account_id) ??
				accounts.find((a) => a.currency.toUpperCase() === item.currency.toUpperCase()) ??
				accounts[0];
			accountId = matching?.id ?? '';
		}
	});

	async function handleConfirm() {
		if (!item || saving) return;
		saving = true;
		error = null;
		try {
			await api.updateRecurring(item.id, { next_due_date: nextDue });
			if (logToLedger && accountId) {
				await api.createTransaction({
					account_id: accountId,
					category_id: item.category_id,
					amount: Number.parseFloat(item.amount).toFixed(2),
					direction: item.direction,
					occurred_at: new Date().toISOString().slice(0, 10),
					merchant: item.merchant_name,
					notes: `Recurring ${item.cadence} payment`
				});
			}
			const msg = logToLedger && accountId
				? `Marked "${item.merchant_name}" paid, logged to ledger, and advanced due date to ${formatDate(nextDue)}.`
				: `Marked "${item.merchant_name}" paid and advanced due date to ${formatDate(nextDue)}.`;
			open = false;
			await onDone(msg);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not mark bill paid';
		} finally {
			saving = false;
		}
	}
</script>

{#if open && item}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-emerald-500/35">
			<div class="flex items-start justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-10 w-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
						<CheckCircle2 class="w-5 h-5" />
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">Mark "{item.merchant_name}" Paid?</h2>
						<p class="text-xs text-slate-400 font-mono-num">
							{formatMoney(item.amount, item.currency)} · {item.cadence}
						</p>
					</div>
				</div>
				<button
					type="button"
					disabled={saving}
					onclick={() => (open = false)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
					{error}
				</div>
			{/if}

			<div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between text-xs font-mono-num">
				<div>
					<div class="text-[10px] text-slate-500">Current Due</div>
					<div class="text-slate-300 mt-0.5">{formatDate(item.next_due_date)}</div>
				</div>
				<ArrowRight class="w-4 h-4 text-emerald-400" />
				<div class="text-right">
					<div class="text-[10px] text-slate-500">Next Due</div>
					<div class="text-emerald-300 font-semibold mt-0.5">{formatDate(nextDue)}</div>
				</div>
			</div>

			{#if accounts.length > 0}
				<div class="space-y-2.5">
					<label class="flex items-center gap-2 text-xs text-slate-200 cursor-pointer">
						<input type="checkbox" bind:checked={logToLedger} class="rounded border-slate-700" />
						Also record this payment in my ledger today
					</label>
					{#if logToLedger}
						<select
							bind:value={accountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							{#each accounts as acc}
								<option value={acc.id}>{acc.name} ({acc.currency})</option>
							{/each}
						</select>
					{/if}
				</div>
			{/if}

			<div class="flex items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={saving}
					onclick={() => (open = false)}
					class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				<button
					type="button"
					disabled={saving}
					onclick={handleConfirm}
					class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<CheckCircle2 class="w-3.5 h-3.5" />
					{saving ? 'Updating...' : 'Confirm Paid'}
				</button>
			</div>
		</div>
	</div>
{/if}
