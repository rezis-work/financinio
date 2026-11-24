<script lang="ts">
	import { api, ApiError } from '$lib/api/client';
	import type { FinancialGoal } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { X, Plus, Sparkles, CheckCircle2 } from 'lucide-svelte';

	let {
		open = $bindable(false),
		goal = null,
		currency = 'USD',
		onContributed
	}: {
		open: boolean;
		goal: FinancialGoal | null;
		currency: string;
		onContributed: (updated: FinancialGoal) => Promise<void> | void;
	} = $props();

	let amount = $state('250');
	let saving = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (open && goal) {
			const monthly = Number.parseFloat(goal.monthly_contribution) || 0;
			const rem = Number.parseFloat(goal.remaining_amount) || 0;
			amount = monthly > 0 ? Math.min(monthly, rem || monthly).toFixed(2) : Math.min(250, rem || 250).toFixed(2);
			error = null;
		}
	});

	let preview = $derived.by(() => {
		if (!goal) return { cur: 0, target: 1, next: 0, pctBefore: 0, pctAfter: 0, completes: false };
		const cur = Number.parseFloat(goal.current_amount) || 0;
		const target = Math.max(1, Number.parseFloat(goal.target_amount) || 1);
		const add = Math.max(0, Number.parseFloat(amount) || 0);
		const next = cur + add;
		const pctBefore = Math.min(100, Math.round((cur / target) * 1000) / 10);
		const pctAfter = Math.min(100, Math.round((next / target) * 1000) / 10);
		return { cur, target, next, pctBefore, pctAfter, completes: next >= target };
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!goal) return;
		const num = Number.parseFloat(amount);
		if (!num || num <= 0) {
			error = 'Enter a valid positive contribution amount.';
			return;
		}
		saving = true;
		error = null;
		try {
			const updated = await api.contributeGoal(goal.id, num.toFixed(2));
			open = false;
			await onContributed(updated);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Contribution failed';
		} finally {
			saving = false;
		}
	}
</script>

{#if open && goal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-emerald-500/35">
			<div class="flex items-start justify-between gap-3">
				<div>
					<h2 class="text-base font-semibold text-white">Contribute to "{goal.name}"</h2>
					<p class="text-xs text-slate-400 font-mono-num mt-0.5">
						{formatMoney(goal.remaining_amount, currency)} remaining to reach target
					</p>
				</div>
				<button
					type="button"
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

			<form onsubmit={handleSubmit} class="space-y-4">
				<!-- Quick-Add Pills -->
				<div class="flex flex-wrap gap-1.5">
					{#each [50, 100, 250, 500] as preset}
						<button
							type="button"
							onclick={() => (amount = preset.toFixed(2))}
							class="px-3 py-1.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs font-mono-num font-semibold text-slate-200 cursor-pointer transition"
						>
							+{preset}
						</button>
					{/each}
					{#if Number.parseFloat(goal.remaining_amount) > 0}
						<button
							type="button"
							onclick={() => (amount = Number.parseFloat(goal.remaining_amount).toFixed(2))}
							class="px-3 py-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-xs font-semibold text-emerald-300 cursor-pointer transition"
						>
							Finish Goal
						</button>
					{/if}
				</div>

				<div>
					<label for="gc-amt" class="block text-xs font-medium text-slate-300 mb-1">
						Contribution Amount ({currency})
					</label>
					<input
						id="gc-amt"
						type="number"
						step="0.01"
						min="0.01"
						required
						bind:value={amount}
						class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-lg font-mono-num font-bold text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<!-- Live Before -> After Progress Preview -->
				<div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2">
					<div class="flex items-center justify-between text-xs font-mono-num">
						<span class="text-slate-400">Progress Preview</span>
						<span class="text-emerald-300 font-semibold">
							{preview.pctBefore}% → {preview.pctAfter}%
						</span>
					</div>
					<div class="relative h-2.5 rounded-full bg-slate-800 overflow-hidden">
						<div
							class="absolute inset-y-0 left-0 rounded-full bg-emerald-400/35 transition-all"
							style="width: {preview.pctAfter}%"
						></div>
						<div
							class="absolute inset-y-0 left-0 rounded-full bg-emerald-400 transition-all"
							style="width: {preview.pctBefore}%"
						></div>
					</div>
					<div class="flex items-center justify-between text-[11px] font-mono-num text-slate-400">
						<span>New saved: <strong class="text-white">{formatMoney(preview.next, currency)}</strong></span>
						{#if preview.completes}
							<span class="inline-flex items-center gap-1 text-emerald-300 font-semibold">
								<Sparkles class="w-3 h-3" /> Goal Completed!
							</span>
						{:else}
							<span>{formatMoney(Math.max(0, preview.target - preview.next), currency)} left</span>
						{/if}
					</div>
				</div>

				<div class="flex items-center justify-end gap-2 pt-1">
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
						class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{#if preview.completes}
							<CheckCircle2 class="w-3.5 h-3.5" />
						{:else}
							<Plus class="w-3.5 h-3.5" />
						{/if}
						{saving ? 'Saving...' : 'Add Contribution'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
