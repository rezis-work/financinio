<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { Account } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { X, Scale, CheckCircle2 } from 'lucide-svelte';

	let {
		open = $bindable(false),
		account,
		onReconciled
	}: {
		open: boolean;
		account: Account | null;
		onReconciled: () => Promise<void> | void;
	} = $props();

	let targetBalance = $state('');
	let mode = $state<'adjustment_tx' | 'initial_balance'>('adjustment_tx');
	let saving = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (open && account) {
			targetBalance = account.current_balance;
			mode = 'adjustment_tx';
			error = null;
		}
	});

	let currentBal = $derived(account ? Number.parseFloat(account.current_balance) || 0 : 0);
	let desiredBal = $derived(Number.parseFloat(targetBalance));
	let delta = $derived(
		!Number.isNaN(desiredBal) ? Math.round((desiredBal - currentBal) * 100) / 100 : 0
	);

	async function handleReconcile(e: SubmitEvent) {
		e.preventDefault();
		if (!account || Number.isNaN(desiredBal)) return;
		if (Math.abs(delta) < 0.01) {
			open = false;
			return;
		}
		saving = true;
		error = null;
		try {
			if (mode === 'adjustment_tx') {
				await api.createTransaction({
					account_id: account.id,
					amount: Math.abs(delta).toFixed(2),
					direction: delta > 0 ? 'inflow' : 'outflow',
					occurred_at: new Date().toISOString().slice(0, 10),
					merchant: 'Balance Reconciliation',
					notes: `Adjusted balance from ${currentBal.toFixed(2)} to ${desiredBal.toFixed(2)}`,
					is_transfer: true
				});
			} else {
				const oldInit = Number.parseFloat(account.initial_balance) || 0;
				const newInit = (oldInit + delta).toFixed(2);
				await api.updateAccount(account.id, { initial_balance: newInit });
			}
			open = false;
			await onReconciled();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Reconciliation failed';
		} finally {
			saving = false;
		}
	}
</script>

{#if open && account}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-emerald-500/30">
			<div class="flex items-center justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-9 w-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-300">
						<Scale class="w-4 h-4" />
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">Reconcile Balance</h2>
						<p class="text-[11px] text-slate-400">{account.name} ({account.currency})</p>
					</div>
				</div>
				<button
					type="button"
					onclick={() => (open = false)}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			{#if error}
				<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
					{error}
				</div>
			{/if}

			<form onsubmit={handleReconcile} class="space-y-4">
				<div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between text-xs">
					<span class="text-slate-400">Current Balance in Financinio</span>
					<span class="font-mono-num font-semibold text-white">
						{formatMoney(account.current_balance, account.currency)}
					</span>
				</div>

				<div>
					<label for="rec-target" class="block text-xs font-medium text-slate-300 mb-1">
						Actual Balance in Your Bank App ({account.currency})
					</label>
					<input
						id="rec-target"
						type="number"
						step="0.01"
						required
						bind:value={targetBalance}
						class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-lg font-mono-num font-bold text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<!-- Discrepancy Readout -->
				<div
					class="p-3.5 rounded-xl border text-xs flex items-center justify-between {Math.abs(delta) < 0.01
						? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
						: delta > 0
							? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-200'
							: 'bg-amber-500/10 border-amber-500/30 text-amber-200'}"
				>
					<span>Discrepancy</span>
					<span class="font-mono-num font-bold">
						{#if Math.abs(delta) < 0.01}
							Balanced (0.00) ✓
						{:else}
							{delta > 0 ? '+' : '-'}{formatMoney(Math.abs(delta), account.currency)}
						{/if}
					</span>
				</div>

				<div class="space-y-2">
					<span class="block text-xs font-medium text-slate-300">How should we reconcile?</span>
					<label
						class="flex items-start gap-2.5 p-3 rounded-xl border cursor-pointer transition {mode === 'adjustment_tx'
							? 'bg-emerald-500/10 border-emerald-500/35'
							: 'bg-slate-950/60 border-slate-800'}"
					>
						<input type="radio" bind:group={mode} value="adjustment_tx" class="mt-0.5" />
						<div class="text-xs">
							<div class="font-semibold text-white">Post Adjustment Entry (Recommended)</div>
							<div class="text-slate-400 text-[11px]">
								Adds a dated Balance Reconciliation record excluded from spending/income analytics.
							</div>
						</div>
					</label>
					<label
						class="flex items-start gap-2.5 p-3 rounded-xl border cursor-pointer transition {mode === 'initial_balance'
							? 'bg-emerald-500/10 border-emerald-500/35'
							: 'bg-slate-950/60 border-slate-800'}"
					>
						<input type="radio" bind:group={mode} value="initial_balance" class="mt-0.5" />
						<div class="text-xs">
							<div class="font-semibold text-white">Adjust Starting Balance</div>
							<div class="text-slate-400 text-[11px]">
								Quietly shifts this account's opening balance without adding a new transaction.
							</div>
						</div>
					</label>
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
						disabled={saving || Number.isNaN(desiredBal) || Math.abs(delta) < 0.01}
						class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-45"
					>
						<CheckCircle2 class="w-3.5 h-3.5" />
						{saving ? 'Reconciling...' : 'Apply Reconciliation'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
