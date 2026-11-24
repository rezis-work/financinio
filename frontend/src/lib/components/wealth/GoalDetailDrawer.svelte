<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError } from '$lib/api/client';
	import type { FinancialGoal, GoalType } from '$lib/api/types';
	import { formatMoney } from '$lib/utils/format';
	import { X, Save, Trash2, Sparkles, Check, Rocket, Plus } from 'lucide-svelte';

	let {
		goal = null,
		currency = 'USD',
		privacyMode = false,
		onClose,
		onSaved,
		onContribute,
		onRequestDelete
	}: {
		goal: FinancialGoal | null;
		currency: string;
		privacyMode?: boolean;
		onClose: () => void;
		onSaved: () => Promise<void> | void;
		onContribute: (g: FinancialGoal) => void;
		onRequestDelete: (g: FinancialGoal) => void;
	} = $props();

	const COLORS = ['#10b981', '#06b6d4', '#6366f1', '#8b5cf6', '#f97316', '#ec4899', '#eab308', '#14b8a6'];

	let name = $state('');
	let goalType = $state<GoalType>('savings');
	let targetAmount = $state('');
	let currentAmount = $state('');
	let monthlyContribution = $state('');
	let targetDate = $state('');
	let color = $state('#10b981');
	let isCompleted = $state(false);
	let boostExtra = $state(0);

	let saving = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		if (goal) {
			name = goal.name;
			goalType = goal.goal_type;
			targetAmount = goal.target_amount;
			currentAmount = goal.current_amount;
			monthlyContribution = goal.monthly_contribution;
			targetDate = goal.target_date ?? '';
			color = goal.color || '#10b981';
			isCompleted = goal.is_completed;
			boostExtra = 0;
			error = null;
		}
	});

	let paceSim = $derived.by(() => {
		const target = Number.parseFloat(targetAmount) || 0;
		const current = Number.parseFloat(currentAmount) || 0;
		const rem = Math.max(0, target - current);
		const baseMo = Math.max(0, Number.parseFloat(monthlyContribution) || 0);
		const boostedMo = baseMo + boostExtra;

		const baseMonths = baseMo > 0 ? Math.ceil(rem / baseMo) : null;
		const boostedMonths = boostedMo > 0 ? Math.ceil(rem / boostedMo) : null;
		const monthsSaved =
			baseMonths !== null && boostedMonths !== null ? Math.max(0, baseMonths - boostedMonths) : 0;

		const finishDate = (months: number | null): string | null => {
			if (months === null) return null;
			const d = new Date();
			d.setMonth(d.getMonth() + months);
			return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
		};

		return {
			rem,
			baseMo,
			boostedMo,
			baseMonths,
			boostedMonths,
			monthsSaved,
			baseFinish: finishDate(baseMonths),
			boostedFinish: finishDate(boostedMonths)
		};
	});

	function applyBoostToForm() {
		monthlyContribution = paceSim.boostedMo.toFixed(2);
		boostExtra = 0;
	}

	async function handleSave(e: SubmitEvent) {
		e.preventDefault();
		if (!goal) return;
		saving = true;
		error = null;
		try {
			await api.updateGoal(goal.id, {
				name: name.trim(),
				goal_type: goalType,
				target_amount: (Number.parseFloat(targetAmount) || 0).toFixed(2),
				current_amount: (Number.parseFloat(currentAmount) || 0).toFixed(2),
				monthly_contribution: (Number.parseFloat(monthlyContribution) || 0).toFixed(2),
				target_date: targetDate || null,
				color,
				is_completed: isCompleted
			});
			await onSaved();
			onClose();
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to update goal';
		} finally {
			saving = false;
		}
	}
</script>

{#if goal}
	<div class="fixed inset-0 z-50 flex justify-end">
		<button
			type="button"
			onclick={onClose}
			aria-label="Close goal inspector"
			class="fixed inset-0 bg-black/65 backdrop-blur-xs cursor-pointer"
		></button>

		<aside class="relative z-10 w-full max-w-md bg-slate-950 border-l border-slate-800/90 h-dvh flex flex-col shadow-2xl overflow-hidden">
			<div class="h-1.5 w-full shrink-0" style="background-color: {color}"></div>

			<div class="p-5 border-b border-slate-800/80 flex items-start justify-between gap-3 shrink-0">
				<div class="min-w-0">
					<h2 class="text-base font-bold text-white truncate">{goal.name}</h2>
					<div class="text-xs text-slate-400 font-mono-num mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(goal.current_amount, currency)} / {formatMoney(goal.target_amount, currency)} ({goal.progress_pct}%)
					</div>
				</div>
				<button
					type="button"
					onclick={onClose}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 cursor-pointer shrink-0"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<div class="flex-1 overflow-y-auto p-5 space-y-5">
				{#if error}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
						{error}
					</div>
				{/if}

				{#if !goal.is_completed}
					<button
						type="button"
						onclick={() => goal && onContribute(goal)}
						class="w-full py-2.5 px-4 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
					>
						<Plus class="w-4 h-4" /> Quick Contribute to This Goal
					</button>

					<!-- Interactive Pace Accelerator Slider -->
					<div class="p-4 rounded-2xl bg-slate-900/75 border border-cyan-500/25 space-y-3">
						<div class="flex items-center justify-between text-xs">
							<span class="font-semibold text-cyan-300 flex items-center gap-1.5">
								<Rocket class="w-3.5 h-3.5" /> Pace Accelerator
							</span>
							<span class="font-mono-num text-white font-semibold">
								+{formatMoney(boostExtra, currency)}/mo
							</span>
						</div>
						<input
							type="range"
							min={0}
							max={1000}
							step={25}
							bind:value={boostExtra}
							class="w-full accent-cyan-400 cursor-pointer"
						/>
						<div class="flex items-center justify-between text-[11px] font-mono-num text-slate-400">
							<span>
								New pace: <strong class="text-white">{formatMoney(paceSim.boostedMo, currency)}/mo</strong>
							</span>
							<span>
								{#if paceSim.boostedFinish}
									Est. <strong class="text-cyan-300">{paceSim.boostedFinish}</strong>
									{#if paceSim.monthsSaved > 0}
										<span class="text-emerald-400">(-{paceSim.monthsSaved} mo!)</span>
									{/if}
								{:else}
									Set a monthly amount
								{/if}
							</span>
						</div>
						{#if boostExtra > 0}
							<button
								type="button"
								onclick={applyBoostToForm}
								class="w-full py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 text-[11px] font-semibold cursor-pointer"
							>
								Apply {formatMoney(paceSim.boostedMo, currency)}/mo to Plan
							</button>
						{/if}
					</div>
				{/if}

				<!-- Full Inline Edit Form -->
				<form id="goal-edit-form" onsubmit={handleSave} class="p-4 rounded-2xl bg-slate-900/50 border border-slate-800/90 space-y-3.5">
					<div class="text-xs font-semibold text-white">Edit Goal Plan</div>

					<div>
						<label for="gd-name" class="block text-[11px] text-slate-400 mb-1">Goal Name</label>
						<input
							id="gd-name"
							type="text"
							required
							bind:value={name}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="gd-type" class="block text-[11px] text-slate-400 mb-1">Goal Type</label>
							<select
								id="gd-type"
								bind:value={goalType}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white"
							>
								<option value="emergency_fund">Emergency Fund</option>
								<option value="savings">Savings</option>
								<option value="debt_payoff">Debt Payoff</option>
								<option value="investment">Investment</option>
								<option value="purchase">Major Purchase</option>
								<option value="retirement">Retirement</option>
							</select>
						</div>
						<div>
							<label for="gd-date" class="block text-[11px] text-slate-400 mb-1">Target Date</label>
							<input
								id="gd-date"
								type="date"
								bind:value={targetDate}
								class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white"
							/>
						</div>
					</div>

					<div class="grid grid-cols-3 gap-2">
						<div>
							<label for="gd-tgt" class="block text-[10px] text-slate-400 mb-1">Target ({currency})</label>
							<input
								id="gd-tgt"
								type="number"
								step="0.01"
								min="1"
								required
								bind:value={targetAmount}
								class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white"
							/>
						</div>
						<div>
							<label for="gd-cur" class="block text-[10px] text-slate-400 mb-1">Saved ({currency})</label>
							<input
								id="gd-cur"
								type="number"
								step="0.01"
								min="0"
								bind:value={currentAmount}
								class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white"
							/>
						</div>
						<div>
							<label for="gd-mo" class="block text-[10px] text-slate-400 mb-1">Monthly</label>
							<input
								id="gd-mo"
								type="number"
								step="0.01"
								min="0"
								bind:value={monthlyContribution}
								class="w-full px-2.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono-num text-white"
							/>
						</div>
					</div>

					<!-- Color Swatches -->
					<div class="space-y-1.5">
						<span class="block text-[11px] text-slate-400">Color</span>
						<div class="flex items-center gap-2 flex-wrap">
							{#each COLORS as c}
								<button
									type="button"
									onclick={() => (color = c)}
									class="h-6 w-6 rounded-lg flex items-center justify-center cursor-pointer border-2 {color === c
										? 'border-white scale-110'
										: 'border-transparent opacity-80'}"
									style="background-color: {c}"
									aria-label="Color {c}"
								>
									{#if color === c}
										<Check class="w-3 h-3 text-slate-950 stroke-[3]" />
									{/if}
								</button>
							{/each}
						</div>
					</div>

					<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer pt-1">
						<input type="checkbox" bind:checked={isCompleted} class="rounded border-slate-700" />
						Mark goal as completed
					</label>

					<button
						type="submit"
						disabled={saving}
						class="w-full inline-flex items-center justify-center gap-1.5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-50"
					>
						<Save class="w-3.5 h-3.5" />
						{saving ? 'Saving...' : 'Save Goal Changes'}
					</button>
				</form>
			</div>

			<div class="p-4 border-t border-slate-800/80 bg-slate-950 flex items-center justify-between gap-2 shrink-0">
				<button
					type="button"
					onclick={() =>
						goal &&
						goto(
							`/advisor?q=${encodeURIComponent(
								`Help me accelerate my "${goal.name}" goal (${goal.current_amount} saved of ${goal.target_amount} ${currency}, currently contributing ${goal.monthly_contribution}/mo). Where can I free up extra monthly cash flow to hit it faster?`
							)}`
						)}
					class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 text-xs font-semibold cursor-pointer"
				>
					<Sparkles class="w-3.5 h-3.5" /> Accelerate with Luna
				</button>
				<button
					type="button"
					onclick={() => goal && onRequestDelete(goal)}
					class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-semibold cursor-pointer"
				>
					<Trash2 class="w-3.5 h-3.5" /> Delete
				</button>
			</div>
		</aside>
	</div>
{/if}
