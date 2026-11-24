<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api/client';
	import type { Account, Category, Transaction } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import { Plus, Search, Trash2, X, Sparkles, ArrowLeftRight } from 'lucide-svelte';

	let transactions = $state<Transaction[]>([]);
	let total = $state(0);
	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Filters
	let search = $state('');
	let filterAccount = $state('');
	let filterCategory = $state('');
	let filterDirection = $state('');

	// Quick-add modal
	let showModal = $state(false);
	let formAccountId = $state('');
	let formCategoryId = $state('');
	let formDirection = $state<'outflow' | 'inflow'>('outflow');
	let formAmount = $state('');
	let formDate = $state(new Date().toISOString().slice(0, 10));
	let formMerchant = $state('');
	let formNotes = $state('');
	let formIsTransfer = $state(false);
	let formTransferAccountId = $state('');
	let saving = $state(false);

	let accountsMap = $derived(new Map(accounts.map((a) => [a.id, a])));

	async function loadAll() {
		loading = true;
		error = null;
		const paramAccId = page.url.searchParams.get('account');
		if (paramAccId && !filterAccount) {
			filterAccount = paramAccId;
		}
		try {
			const [accs, cats, txRes] = await Promise.all([
				api.listAccounts(),
				api.listCategories(),
				api.listTransactions({
					search,
					account_id: filterAccount || undefined,
					category_id: filterCategory || undefined,
					direction: filterDirection || undefined,
					limit: 100
				})
			]);
			accounts = accs;
			categories = cats;
			transactions = txRes.items;
			total = txRes.total;
			if (!formAccountId && accs.length > 0) formAccountId = accs[0].id;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load transactions';
		} finally {
			loading = false;
		}
	}

	async function loadFiltered() {
		try {
			const txRes = await api.listTransactions({
				search,
				account_id: filterAccount || undefined,
				category_id: filterCategory || undefined,
				direction: filterDirection || undefined,
				limit: 100
			});
			transactions = txRes.items;
			total = txRes.total;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Filter failed';
		}
	}

	onMount(loadAll);

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		if (!formAccountId) {
			error = 'Please create an account first.';
			return;
		}
		saving = true;
		error = null;
		try {
			await api.createTransaction({
				account_id: formAccountId,
				category_id: formCategoryId || null,
				amount: formAmount,
				direction: formDirection,
				occurred_at: formDate,
				merchant: formMerchant,
				notes: formNotes || undefined,
				is_transfer: formIsTransfer,
				transfer_account_id: formIsTransfer && formTransferAccountId ? formTransferAccountId : null
			});
			showModal = false;
			formAmount = '';
			formMerchant = '';
			formNotes = '';
			formIsTransfer = false;
			formTransferAccountId = '';
			await loadFiltered();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save transaction';
		} finally {
			saving = false;
		}
	}

	async function handleCategoryChange(tx: Transaction, newCategoryId: string) {
		try {
			const updated = await api.updateTransaction(tx.id, {
				category_id: newCategoryId || null
			});
			transactions = transactions.map((t) => (t.id === tx.id ? updated : t));
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Category update failed';
		}
	}

	async function handleDelete(tx: Transaction) {
		if (!confirm(`Delete "${tx.merchant_clean}"?`)) return;
		await api.deleteTransaction(tx.id);
		await loadFiltered();
	}
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Transactions</h1>
			<p class="text-sm text-slate-400 mt-0.5">
				{total} ledger {total === 1 ? 'entry' : 'entries'} · Editing a category teaches Upstash Vector memory automatically.
			</p>
		</div>
		<button
			type="button"
			onclick={() => (showModal = true)}
			class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer"
		>
			<Plus class="w-4 h-4" />
			Quick Add
		</button>
	</div>

	<!-- Filters bar -->
	<div class="card-surface rounded-2xl p-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
		<div class="relative">
			<Search class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
			<input
				type="text"
				bind:value={search}
				oninput={loadFiltered}
				placeholder="Search merchant, notes..."
				class="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
			/>
		</div>
		<select
			bind:value={filterAccount}
			onchange={loadFiltered}
			class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
		>
			<option value="">All Accounts</option>
			{#each accounts as acc}
				<option value={acc.id}>{acc.name}</option>
			{/each}
		</select>
		<select
			bind:value={filterCategory}
			onchange={loadFiltered}
			class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
		>
			<option value="">All Categories</option>
			{#each categories as cat}
				<option value={cat.id}>{cat.name}</option>
			{/each}
		</select>
		<select
			bind:value={filterDirection}
			onchange={loadFiltered}
			class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
		>
			<option value="">All Directions</option>
			<option value="outflow">Expenses (Outflow)</option>
			<option value="inflow">Income (Inflow)</option>
		</select>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}

	<!-- Ledger Table -->
	<div class="card-surface rounded-2xl overflow-hidden">
		{#if loading}
			<div class="p-10 text-center text-sm text-slate-400">Loading ledger...</div>
		{:else if transactions.length === 0}
			<div class="p-12 text-center space-y-2">
				<p class="text-sm text-slate-400">No transactions match these filters.</p>
				<a href="/imports" class="text-xs font-semibold text-emerald-400 hover:underline">
					Import a CSV, Excel, or PDF bank statement →
				</a>
			</div>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-left border-collapse">
					<thead>
						<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400">
							<th class="py-3 px-4">Date</th>
							<th class="py-3 px-4">Merchant</th>
							<th class="py-3 px-4">Account</th>
							<th class="py-3 px-4">Category</th>
							<th class="py-3 px-4 text-right">Amount</th>
							<th class="py-3 px-4 text-right"></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-slate-800/60 text-sm">
						{#each transactions as tx}
							{@const acc = accountsMap.get(tx.account_id)}
							<tr class="hover:bg-slate-900/50 transition">
								<td class="py-3 px-4 text-slate-400 whitespace-nowrap text-xs font-mono-num">
									{formatDate(tx.occurred_at)}
								</td>
								<td class="py-3 px-4">
									<div class="flex items-center gap-2">
										<span class="font-medium text-white">{tx.merchant_clean}</span>
										{#if tx.is_transfer}
											<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300">
												<ArrowLeftRight class="w-2.5 h-2.5" /> Transfer
											</span>
										{/if}
										{#if tx.source_document_id}
											<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-emerald-500/10 text-[10px] text-emerald-300">
												<Sparkles class="w-2.5 h-2.5" /> AI Import
											</span>
										{/if}
									</div>
									{#if tx.merchant_raw !== tx.merchant_clean}
										<div class="text-[11px] text-slate-500 truncate max-w-xs">{tx.merchant_raw}</div>
									{/if}
								</td>
								<td class="py-3 px-4 text-xs text-slate-300 whitespace-nowrap">
									{acc?.name ?? '—'}
								</td>
								<td class="py-3 px-4">
									<select
										value={tx.category_id ?? ''}
										onchange={(e) => handleCategoryChange(tx, (e.currentTarget as HTMLSelectElement).value)}
										class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
									>
										<option value="">Uncategorized</option>
										{#each categories as cat}
											<option value={cat.id}>{cat.name}</option>
										{/each}
									</select>
								</td>
								<td
									class="py-3 px-4 text-right font-mono-num font-semibold whitespace-nowrap {tx.direction === 'inflow'
										? 'text-emerald-400'
										: 'text-slate-100'}"
								>
									{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
								</td>
								<td class="py-3 px-4 text-right">
									<button
										type="button"
										onclick={() => handleDelete(tx)}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										title="Delete transaction"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
</div>

{#if showModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Add Transaction</h2>
				<button
					type="button"
					onclick={() => (showModal = false)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleCreate} class="space-y-4">
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-950 border border-slate-800">
					<button
						type="button"
						onclick={() => (formDirection = 'outflow')}
						class="py-1.5 text-xs font-semibold rounded-lg {formDirection === 'outflow'
							? 'bg-rose-500/20 text-rose-300'
							: 'text-slate-400'}"
					>
						Expense (Outflow)
					</button>
					<button
						type="button"
						onclick={() => (formDirection = 'inflow')}
						class="py-1.5 text-xs font-semibold rounded-lg {formDirection === 'inflow'
							? 'bg-emerald-500/20 text-emerald-300'
							: 'text-slate-400'}"
					>
						Income (Inflow)
					</button>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="tx-amount" class="block text-xs font-medium text-slate-300 mb-1">Amount</label>
						<input
							id="tx-amount"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={formAmount}
							placeholder="0.00"
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
						/>
					</div>
					<div>
						<label for="tx-date" class="block text-xs font-medium text-slate-300 mb-1">Date</label>
						<input
							id="tx-date"
							type="date"
							required
							bind:value={formDate}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<div>
					<label for="tx-merchant" class="block text-xs font-medium text-slate-300 mb-1">Merchant / Payee</label>
					<input
						id="tx-merchant"
						type="text"
						required
						bind:value={formMerchant}
						placeholder="e.g., Whole Foods Market"
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="tx-acc" class="block text-xs font-medium text-slate-300 mb-1">Account</label>
						<select
							id="tx-acc"
							required
							bind:value={formAccountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						>
							{#each accounts as acc}
								<option value={acc.id}>{acc.name}</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="tx-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
						<select
							id="tx-cat"
							bind:value={formCategoryId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						>
							<option value="">Uncategorized</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>
				</div>

				<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
					<input type="checkbox" bind:checked={formIsTransfer} class="rounded border-slate-700" />
					Mark as internal transfer (exclude from income/expense totals)
				</label>

				{#if formIsTransfer}
					<div>
						<label for="tx-peer" class="block text-xs font-medium text-slate-300 mb-1">Link Counterparty Account (optional)</label>
						<select
							id="tx-peer"
							bind:value={formTransferAccountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white"
						>
							<option value="">None (single-sided transfer)</option>
							{#each accounts.filter((a) => a.id !== formAccountId) as acc}
								<option value={acc.id}>{acc.name}</option>
							{/each}
						</select>
					</div>
				{/if}

				<div>
					<label for="tx-notes" class="block text-xs font-medium text-slate-300 mb-1">Notes</label>
					<input
						id="tx-notes"
						type="text"
						bind:value={formNotes}
						placeholder="Optional memo..."
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="flex items-center justify-end gap-2.5 pt-2">
					<button
						type="button"
						onclick={() => (showModal = false)}
						class="px-4 py-2 rounded-xl text-sm text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer disabled:opacity-50"
					>
						{saving ? 'Saving...' : 'Save Transaction'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
