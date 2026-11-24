<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Account, Category } from '$lib/api/types';
	import { X, Plus, ArrowUpRight, ArrowDownRight } from 'lucide-svelte';

	let {
		open = $bindable(false),
		accounts,
		categories,
		onCreated
	}: {
		open: boolean;
		accounts: Account[];
		categories: Category[];
		onCreated: () => Promise<void> | void;
	} = $props();

	let direction = $state<'outflow' | 'inflow'>('outflow');
	let accountId = $state('');
	let categoryId = $state('');
	let amount = $state('');
	let merchant = $state('');
	let occurredAt = $state(new Date().toISOString().slice(0, 10));
	let notes = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (open && !accountId && accounts.length > 0) {
			accountId = accounts[0].id;
		}
	});

	let filteredCategories = $derived(
		categories.filter((c) => (direction === 'inflow' ? c.kind === 'income' : c.kind !== 'income'))
	);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!accountId) {
			error = 'Create an account first before adding a transaction.';
			return;
		}
		const num = Number.parseFloat(amount);
		if (!num || num <= 0) {
			error = 'Enter a valid positive amount.';
			return;
		}
		saving = true;
		error = null;
		try {
			await api.createTransaction({
				account_id: accountId,
				category_id: categoryId || null,
				amount: num.toFixed(2),
				direction,
				occurred_at: occurredAt,
				merchant: merchant.trim(),
				notes: notes.trim() || undefined
			});
			amount = '';
			merchant = '';
			notes = '';
			categoryId = '';
			open = false;
			await onCreated();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to create transaction';
		} finally {
			saving = false;
		}
	}
</script>

{#if open}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-slate-700/80">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Quick-Add Transaction</h2>
				<button
					type="button"
					onclick={() => (open = false)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
					aria-label="Close modal"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
					{error}
				</div>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4">
				<!-- Expense / Income Segmented Switch -->
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-950 border border-slate-800">
					<button
						type="button"
						onclick={() => {
							direction = 'outflow';
							categoryId = '';
						}}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {direction === 'outflow'
							? 'bg-rose-500/20 text-rose-300 border border-rose-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowUpRight class="w-3.5 h-3.5" /> Expense
					</button>
					<button
						type="button"
						onclick={() => {
							direction = 'inflow';
							categoryId = '';
						}}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {direction === 'inflow'
							? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowDownRight class="w-3.5 h-3.5" /> Income
					</button>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="qa-amount" class="block text-xs font-medium text-slate-300 mb-1">Amount</label>
						<input
							id="qa-amount"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={amount}
							placeholder="0.00"
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-base font-mono-num font-semibold text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
					<div>
						<label for="qa-date" class="block text-xs font-medium text-slate-300 mb-1">Date</label>
						<input
							id="qa-date"
							type="date"
							required
							bind:value={occurredAt}
							class="w-full px-3 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<div>
					<label for="qa-merchant" class="block text-xs font-medium text-slate-300 mb-1">
						{direction === 'inflow' ? 'Source / Payer' : 'Merchant'}
					</label>
					<input
						id="qa-merchant"
						type="text"
						required
						bind:value={merchant}
						placeholder={direction === 'inflow' ? 'e.g., Monthly Salary' : 'e.g., Yandex Go, Carrefour, Wolt...'}
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="qa-account" class="block text-xs font-medium text-slate-300 mb-1">Account</label>
						<select
							id="qa-account"
							bind:value={accountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							{#if accounts.length === 0}
								<option value="">No accounts</option>
							{:else}
								{#each accounts as acc}
									<option value={acc.id}>{acc.name} ({acc.currency})</option>
								{/each}
							{/if}
						</select>
					</div>
					<div>
						<label for="qa-category" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
						<select
							id="qa-category"
							bind:value={categoryId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							<option value="">Uncategorized</option>
							{#each filteredCategories as cat}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>
				</div>

				<div>
					<label for="qa-notes" class="block text-xs font-medium text-slate-300 mb-1">Notes (optional)</label>
					<input
						id="qa-notes"
						type="text"
						bind:value={notes}
						placeholder="Optional memo..."
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="flex items-center justify-end gap-2.5 pt-1">
					<button
						type="button"
						onclick={() => (open = false)}
						class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving || accounts.length === 0}
						class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
					>
						<Plus class="w-4 h-4" />
						{saving ? 'Saving...' : 'Save Transaction'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
