<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { Account, AccountType } from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatMoney } from '$lib/utils/format';
	import { Plus, Wallet, CreditCard, Landmark, Trash2, X } from 'lucide-svelte';

	let accounts = $state<Account[]>([]);
	let loading = $state(true);
	let showModal = $state(false);
	let error = $state<string | null>(null);

	// New account form state
	let name = $state('');
	let type = $state<AccountType>('checking');
	let currency = $state(auth.user?.base_currency || 'USD');
	let initialBalance = $state('0.00');
	let institution = $state('');
	let color = $state('#10b981');
	let saving = $state(false);

	const ACCOUNT_TYPES: Array<{ value: AccountType; label: string }> = [
		{ value: 'checking', label: 'Checking' },
		{ value: 'savings', label: 'Savings' },
		{ value: 'credit', label: 'Credit Card' },
		{ value: 'cash', label: 'Cash' },
		{ value: 'investment', label: 'Investment' },
		{ value: 'loan', label: 'Loan / Debt' }
	];

	async function loadAccounts() {
		loading = true;
		try {
			accounts = await api.listAccounts();
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load accounts';
		} finally {
			loading = false;
		}
	}

	onMount(loadAccounts);

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		try {
			await api.createAccount({
				name,
				type,
				currency,
				initial_balance: initialBalance || '0.00',
				institution: institution || undefined,
				color
			});
			showModal = false;
			name = '';
			initialBalance = '0.00';
			institution = '';
			await loadAccounts();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not create account';
		} finally {
			saving = false;
		}
	}

	async function handleDelete(acc: Account) {
		if (!confirm(`Delete "${acc.name}" and all of its transactions?`)) return;
		await api.deleteAccount(acc.id);
		await loadAccounts();
	}

	let totalBalance = $derived(
		accounts.reduce((sum, a) => sum + Number.parseFloat(a.current_balance), 0)
	);
</script>

<div class="space-y-6">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-white">Accounts</h1>
			<p class="text-sm text-slate-400 mt-0.5">
				Combined balance across {accounts.length} active {accounts.length === 1 ? 'account' : 'accounts'}:
				<span class="font-mono-num font-semibold text-emerald-400">
					{formatMoney(totalBalance, auth.user?.base_currency || 'USD')}
				</span>
			</p>
		</div>
		<button
			type="button"
			onclick={() => (showModal = true)}
			class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition cursor-pointer"
		>
			<Plus class="w-4 h-4" />
			Add Account
		</button>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">{error}</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<div class="card-surface rounded-2xl h-40 animate-pulse"></div>
			{/each}
		</div>
	{:else if accounts.length === 0}
		<div class="card-surface rounded-2xl p-12 text-center space-y-3">
			<Wallet class="w-10 h-10 text-slate-500 mx-auto" />
			<h2 class="text-lg font-semibold text-white">No accounts yet</h2>
			<p class="text-sm text-slate-400 max-w-md mx-auto">
				Add your checking, savings, credit cards, or cash wallets to track balances and import statements.
			</p>
			<button
				type="button"
				onclick={() => (showModal = true)}
				class="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer"
			>
				<Plus class="w-4 h-4" />
				Create First Account
			</button>
		</div>
	{:else}
		<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each accounts as acc}
				{@const bal = Number.parseFloat(acc.current_balance)}
				<div class="card-surface card-surface-hover rounded-2xl p-5 flex flex-col justify-between gap-5">
					<div class="flex items-start justify-between gap-3">
						<div class="flex items-center gap-3">
							<div
								class="h-10 w-10 rounded-xl flex items-center justify-center border border-white/10"
								style="background-color: {acc.color}22; color: {acc.color}"
							>
								{#if acc.type === 'credit'}
									<CreditCard class="w-5 h-5" />
								{:else if acc.type === 'loan' || acc.type === 'investment'}
									<Landmark class="w-5 h-5" />
								{:else}
									<Wallet class="w-5 h-5" />
								{/if}
							</div>
							<div>
								<div class="font-semibold text-white">{acc.name}</div>
								<div class="text-xs text-slate-400 capitalize">
									{acc.type}{acc.institution ? ` · ${acc.institution}` : ''}
								</div>
							</div>
						</div>
						<button
							type="button"
							onclick={() => handleDelete(acc)}
							class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer"
							title="Delete account"
						>
							<Trash2 class="w-4 h-4" />
						</button>
					</div>

					<div>
						<div class="text-xs text-slate-400">Current Balance</div>
						<div class="text-2xl font-bold font-mono-num mt-0.5 {bal < 0 ? 'text-rose-400' : 'text-white'}">
							{formatMoney(acc.current_balance, acc.currency)}
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if showModal}
	<div class="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Add Account</h2>
				<button
					type="button"
					onclick={() => (showModal = false)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleCreate} class="space-y-4">
				<div>
					<label for="acc-name" class="block text-xs font-medium text-slate-300 mb-1">Account Name</label>
					<input
						id="acc-name"
						type="text"
						required
						bind:value={name}
						placeholder="e.g., Main Checking"
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="acc-type" class="block text-xs font-medium text-slate-300 mb-1">Type</label>
						<select
							id="acc-type"
							bind:value={type}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						>
							{#each ACCOUNT_TYPES as t}
								<option value={t.value}>{t.label}</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="acc-ccy" class="block text-xs font-medium text-slate-300 mb-1">Currency</label>
						<input
							id="acc-ccy"
							type="text"
							maxlength={3}
							required
							bind:value={currency}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white uppercase focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="acc-bal" class="block text-xs font-medium text-slate-300 mb-1">Starting Balance</label>
						<input
							id="acc-bal"
							type="number"
							step="0.01"
							bind:value={initialBalance}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
						/>
						<p class="text-[11px] text-slate-500 mt-1">Use negative for credit card debt</p>
					</div>
					<div>
						<label for="acc-inst" class="block text-xs font-medium text-slate-300 mb-1">Institution</label>
						<input
							id="acc-inst"
							type="text"
							bind:value={institution}
							placeholder="Chase, Revolut..."
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
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
						{saving ? 'Saving...' : 'Create Account'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
