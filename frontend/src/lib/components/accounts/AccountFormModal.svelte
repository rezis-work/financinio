<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Account, AccountType } from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { X, Check, Landmark, Wallet, CreditCard, Sparkles } from 'lucide-svelte';

	let {
		open = $bindable(false),
		editingAccount = null,
		onSaved
	}: {
		open: boolean;
		editingAccount?: Account | null;
		onSaved: () => Promise<void> | void;
	} = $props();

	const ACCOUNT_TYPES: Array<{ value: AccountType; label: string }> = [
		{ value: 'checking', label: 'Checking' },
		{ value: 'savings', label: 'Savings' },
		{ value: 'credit', label: 'Credit Card' },
		{ value: 'cash', label: 'Cash Wallet' },
		{ value: 'investment', label: 'Investment' },
		{ value: 'loan', label: 'Loan / Debt' }
	];

	const CURRENCIES = ['GEL', 'USD', 'EUR', 'GBP', 'CHF', 'TRY'];

	const COLOR_SWATCHES = [
		{ hex: '#f97316', label: 'BOG Orange' },
		{ hex: '#06b6d4', label: 'TBC Cyan' },
		{ hex: '#10b981', label: 'Emerald' },
		{ hex: '#6366f1', label: 'Indigo' },
		{ hex: '#8b5cf6', label: 'Violet' },
		{ hex: '#ec4899', label: 'Rose' },
		{ hex: '#eab308', label: 'Amber' },
		{ hex: '#64748b', label: 'Slate' }
	];

	const BANK_PRESETS: Array<{
		label: string;
		name: string;
		type: AccountType;
		currency: string;
		institution: string;
		color: string;
	}> = [
		{
			label: 'Bank of Georgia',
			name: 'BOG Main Card',
			type: 'checking',
			currency: 'GEL',
			institution: 'Bank of Georgia',
			color: '#f97316'
		},
		{
			label: 'TBC Bank',
			name: 'TBC Checking',
			type: 'checking',
			currency: 'GEL',
			institution: 'TBC Bank',
			color: '#06b6d4'
		},
		{
			label: 'Revolut',
			name: 'Revolut Multi-Currency',
			type: 'checking',
			currency: 'EUR',
			institution: 'Revolut',
			color: '#6366f1'
		},
		{
			label: 'Wise',
			name: 'Wise Account',
			type: 'checking',
			currency: 'USD',
			institution: 'Wise',
			color: '#10b981'
		},
		{
			label: 'Cash Wallet',
			name: 'Cash Wallet',
			type: 'cash',
			currency: 'GEL',
			institution: 'Cash',
			color: '#eab308'
		},
		{
			label: 'Credit Card',
			name: 'Credit Card',
			type: 'credit',
			currency: 'GEL',
			institution: 'Bank of Georgia',
			color: '#ec4899'
		}
	];

	let name = $state('');
	let type = $state<AccountType>('checking');
	let currency = $state(auth.user?.base_currency || 'GEL');
	let customCurrency = $state(false);
	let initialBalance = $state('0.00');
	let institution = $state('');
	let color = $state('#10b981');
	let saving = $state(false);
	let error = $state<string | null>(null);

	let isEdit = $derived(editingAccount !== null);

	$effect(() => {
		if (open) {
			error = null;
			if (editingAccount) {
				name = editingAccount.name;
				type = editingAccount.type;
				currency = editingAccount.currency;
				customCurrency = !CURRENCIES.includes(editingAccount.currency);
				initialBalance = editingAccount.initial_balance;
				institution = editingAccount.institution || '';
				color = editingAccount.color || '#10b981';
			} else {
				name = '';
				type = 'checking';
				currency = auth.user?.base_currency || 'GEL';
				customCurrency = !CURRENCIES.includes(currency);
				initialBalance = '0.00';
				institution = '';
				color = '#10b981';
			}
		}
	});

	function applyPreset(preset: (typeof BANK_PRESETS)[number]) {
		name = preset.name;
		type = preset.type;
		currency = preset.currency;
		customCurrency = !CURRENCIES.includes(preset.currency);
		institution = preset.institution;
		color = preset.color;
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = null;
		try {
			const cleanBal = initialBalance === '' ? '0.00' : String(initialBalance);
			if (editingAccount) {
				await api.updateAccount(editingAccount.id, {
					name: name.trim(),
					type,
					institution: institution.trim() || null,
					color,
					initial_balance: cleanBal
				});
			} else {
				await api.createAccount({
					name: name.trim(),
					type,
					currency: currency.trim().toUpperCase().slice(0, 3) || 'USD',
					initial_balance: cleanBal,
					institution: institution.trim() || undefined,
					color
				});
			}
			open = false;
			await onSaved();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save account';
		} finally {
			saving = false;
		}
	}
</script>

{#if open}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
		<div class="card-surface rounded-2xl w-full max-w-lg p-6 space-y-5 border border-slate-700/80 my-auto">
			<div class="flex items-center justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div
						class="h-9 w-9 rounded-xl flex items-center justify-center border border-white/10"
						style="background-color: {color}22; color: {color}"
					>
						{#if type === 'credit'}
							<CreditCard class="w-4 h-4" />
						{:else if type === 'loan' || type === 'investment'}
							<Landmark class="w-4 h-4" />
						{:else}
							<Wallet class="w-4 h-4" />
						{/if}
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">
							{isEdit ? 'Edit Account' : 'Add New Account'}
						</h2>
						<p class="text-[11px] text-slate-400">
							{isEdit
								? 'Update account details, brand color, or starting balance.'
								: 'Pick a quick bank preset or configure a custom account.'}
						</p>
					</div>
				</div>
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

			{#if !isEdit}
				<div class="space-y-2">
					<div class="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
						<Sparkles class="w-3 h-3 text-emerald-400" /> Quick Bank Presets
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each BANK_PRESETS as preset}
							<button
								type="button"
								onclick={() => applyPreset(preset)}
								class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-slate-950/80 hover:bg-slate-900 border border-slate-800 hover:border-slate-600 text-xs text-slate-200 transition cursor-pointer"
							>
								<span class="w-2 h-2 rounded-full" style="background-color: {preset.color}"></span>
								<span>{preset.label}</span>
								<span class="text-[10px] font-mono-num text-slate-500">{preset.currency}</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<label for="acc-name" class="block text-xs font-medium text-slate-300 mb-1">Account Name</label>
					<input
						id="acc-name"
						type="text"
						required
						bind:value={name}
						placeholder="e.g., BOG Student Card, Savings Vault..."
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
						<div class="flex items-center justify-between mb-1">
							<label for="acc-ccy" class="block text-xs font-medium text-slate-300">Currency</label>
							{#if !isEdit}
								<button
									type="button"
									onclick={() => (customCurrency = !customCurrency)}
									class="text-[10px] text-emerald-400 hover:text-emerald-300 cursor-pointer"
								>
									{customCurrency ? 'List' : 'Custom'}
								</button>
							{/if}
						</div>
						{#if isEdit}
							<input
								id="acc-ccy"
								type="text"
								value={currency}
								disabled
								class="w-full px-3.5 py-2 rounded-xl bg-slate-950/60 border border-slate-800 text-sm text-slate-400 font-mono-num uppercase cursor-not-allowed"
							/>
						{:else if customCurrency}
							<input
								id="acc-ccy"
								type="text"
								maxlength={3}
								minlength={3}
								required
								bind:value={currency}
								placeholder="GEL"
								class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num uppercase focus:outline-none focus:border-emerald-500"
							/>
						{:else}
							<select
								id="acc-ccy"
								bind:value={currency}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
							>
								{#each CURRENCIES as c}
									<option value={c}>{c}</option>
								{/each}
							</select>
						{/if}
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="acc-bal" class="block text-xs font-medium text-slate-300 mb-1">
							Starting Balance
						</label>
						<input
							id="acc-bal"
							type="number"
							step="0.01"
							bind:value={initialBalance}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
						/>
						<p class="text-[10px] text-slate-500 mt-1">
							{isEdit
								? 'Updating recalculates live balance'
								: 'Use negative for credit card debt'}
						</p>
					</div>
					<div>
						<label for="acc-inst" class="block text-xs font-medium text-slate-300 mb-1">Institution</label>
						<input
							id="acc-inst"
							type="text"
							bind:value={institution}
							placeholder="Bank of Georgia, TBC, Revolut..."
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<!-- Color Swatch Picker -->
				<div class="space-y-1.5">
					<span class="block text-xs font-medium text-slate-300">Accent Color</span>
					<div class="flex items-center gap-2 flex-wrap">
						{#each COLOR_SWATCHES as sw}
							<button
								type="button"
								title={sw.label}
								onclick={() => (color = sw.hex)}
								class="h-7 w-7 rounded-lg flex items-center justify-center transition cursor-pointer border-2 {color === sw.hex
									? 'border-white scale-110'
									: 'border-transparent opacity-80 hover:opacity-100'}"
								style="background-color: {sw.hex}"
								aria-label={sw.label}
							>
								{#if color === sw.hex}
									<Check class="w-3.5 h-3.5 text-slate-950 stroke-[3]" />
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<div class="flex items-center justify-end gap-2.5 pt-2">
					<button
						type="button"
						onclick={() => (open = false)}
						class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Account'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
