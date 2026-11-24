<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Account } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { X, ArrowLeftRight, ArrowRight } from 'lucide-svelte';

	let {
		open = $bindable(false),
		accounts,
		initialFromId = '',
		onTransferred
	}: {
		open: boolean;
		accounts: Account[];
		initialFromId?: string;
		onTransferred: () => Promise<void> | void;
	} = $props();

	let fromId = $state('');
	let toId = $state('');
	let amount = $state('');
	let occurredAt = $state(new Date().toISOString().slice(0, 10));
	let notes = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	let activeAccounts = $derived(accounts.filter((a) => !a.is_archived));
	let fromAcc = $derived(activeAccounts.find((a) => a.id === fromId) ?? null);
	let toAcc = $derived(activeAccounts.find((a) => a.id === toId) ?? null);

	$effect(() => {
		if (open) {
			error = null;
			const first =
				activeAccounts.find((a) => a.id === initialFromId) ?? activeAccounts[0] ?? null;
			const second = activeAccounts.find((a) => a.id !== first?.id) ?? null;
			fromId = first?.id ?? '';
			toId = second?.id ?? '';
			amount = '';
			notes = '';
			occurredAt = new Date().toISOString().slice(0, 10);
		}
	});

	function swapAccounts() {
		const tmp = fromId;
		fromId = toId;
		toId = tmp;
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!fromId || !toId || fromId === toId) {
			error = 'Select two different accounts for the transfer.';
			return;
		}
		const num = Number.parseFloat(amount);
		if (!num || num <= 0) {
			error = 'Enter a valid positive transfer amount.';
			return;
		}
		saving = true;
		error = null;
		try {
			await api.createTransaction({
				account_id: fromId,
				transfer_account_id: toId,
				is_transfer: true,
				direction: 'outflow',
				amount: num.toFixed(2),
				occurred_at: occurredAt,
				merchant: `Transfer to ${toAcc?.name || 'Account'}`,
				notes: notes.trim() || undefined
			});
			open = false;
			await onTransferred();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Transfer failed';
		} finally {
			saving = false;
		}
	}
</script>

{#if open}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-cyan-500/30">
			<div class="flex items-center justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-9 w-9 rounded-xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-300">
						<ArrowLeftRight class="w-4 h-4" />
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">Transfer Between Accounts</h2>
						<p class="text-[11px] text-slate-400">
							Excluded from spending & income stats automatically.
						</p>
					</div>
				</div>
				<button
					type="button"
					onclick={() => (open = false)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
					aria-label="Close transfer modal"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
					{error}
				</div>
			{/if}

			{#if activeAccounts.length < 2}
				<p class="text-xs text-slate-400 py-4 text-center">
					You need at least 2 active accounts to record an internal transfer.
				</p>
			{:else}
				<form onsubmit={handleSubmit} class="space-y-4">
					<div class="space-y-2">
						<div>
							<label for="tr-from" class="block text-xs font-medium text-slate-300 mb-1">From Account</label>
							<select
								id="tr-from"
								bind:value={fromId}
								class="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-cyan-500"
							>
								{#each activeAccounts as acc}
									<option value={acc.id}>
										{acc.name} ({formatMoney(acc.current_balance, acc.currency)})
									</option>
								{/each}
							</select>
						</div>

						<div class="flex justify-center">
							<button
								type="button"
								onclick={swapAccounts}
								class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-900 hover:bg-slate-800 border border-slate-700 text-[11px] text-slate-300 cursor-pointer transition"
							>
								<ArrowLeftRight class="w-3 h-3 text-cyan-400" /> Swap
							</button>
						</div>

						<div>
							<label for="tr-to" class="block text-xs font-medium text-slate-300 mb-1">To Account</label>
							<select
								id="tr-to"
								bind:value={toId}
								class="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-cyan-500"
							>
								{#each activeAccounts as acc}
									<option value={acc.id}>
										{acc.name} ({formatMoney(acc.current_balance, acc.currency)})
									</option>
								{/each}
							</select>
						</div>
					</div>

					{#if fromAcc && toAcc && fromAcc.currency !== toAcc.currency}
						<div class="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-[11px] text-amber-200">
							Note: {fromAcc.name} is {fromAcc.currency} and {toAcc.name} is {toAcc.currency}. Both legs will post using the entered nominal amount.
						</div>
					{/if}

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="tr-amt" class="block text-xs font-medium text-slate-300 mb-1">
								Amount ({fromAcc?.currency || 'USD'})
							</label>
							<input
								id="tr-amt"
								type="number"
								step="0.01"
								min="0.01"
								required
								bind:value={amount}
								placeholder="0.00"
								class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-base font-mono-num font-semibold text-white focus:outline-none focus:border-cyan-500"
							/>
						</div>
						<div>
							<label for="tr-date" class="block text-xs font-medium text-slate-300 mb-1">Date</label>
							<input
								id="tr-date"
								type="date"
								required
								bind:value={occurredAt}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-cyan-500"
							/>
						</div>
					</div>

					<div>
						<label for="tr-note" class="block text-xs font-medium text-slate-300 mb-1">Memo (optional)</label>
						<input
							id="tr-note"
							type="text"
							bind:value={notes}
							placeholder="e.g., Monthly savings sweep, credit card payoff..."
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
						/>
					</div>

					<div class="flex items-center justify-end gap-2.5 pt-1">
						<button
							type="button"
							onclick={() => (open = false)}
							class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
						>
							Cancel
						</button>
						<button
							type="submit"
							disabled={saving || fromId === toId}
							class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
						>
							{saving ? 'Recording...' : 'Record Transfer'}
							<ArrowRight class="w-3.5 h-3.5" />
						</button>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}
