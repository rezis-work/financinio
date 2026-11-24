<script lang="ts">
	import { goto } from '$app/navigation';
	import { formatMoney } from '$lib/utils/format';
	import { Flame, Sparkles } from 'lucide-svelte';

	let {
		initialNetWorth = 0,
		initialAnnualExpenses = 24000,
		initialMonthlySavings = 1000,
		currency = 'USD',
		privacyMode = false
	}: {
		initialNetWorth?: number;
		initialAnnualExpenses?: number;
		initialMonthlySavings?: number;
		currency: string;
		privacyMode?: boolean;
	} = $props();

	let currentPortfolio = $state(0);
	let annualExpenses = $state(24000);
	let monthlySavings = $state(1000);
	let expectedReturnPct = $state(7.0);
	let swrPct = $state(4.0);
	let initialized = $state(false);

	$effect(() => {
		if (!initialized) {
			currentPortfolio = Math.max(0, Math.round(initialNetWorth));
			annualExpenses = Math.max(1200, Math.round(initialAnnualExpenses || 24000));
			monthlySavings = Math.max(0, Math.round(initialMonthlySavings || 1000));
			initialized = true;
		}
	});

	let fiCalc = $derived.by(() => {
		const mult = swrPct > 0 ? 100 / swrPct : 25;
		const fiNumber = annualExpenses * mult;
		const progressPct = fiNumber > 0 ? Math.min(100, Math.round((currentPortfolio / fiNumber) * 1000) / 10) : 0;

		if (currentPortfolio >= fiNumber && fiNumber > 0) {
			return { fiNumber, progressPct: 100, yearsToFi: 0, targetYear: new Date().getFullYear(), reachable: true };
		}

		const monthlyRate = expectedReturnPct / 100 / 12;
		let bal = currentPortfolio;
		let months = 0;
		const maxMonths = 60 * 12;

		while (bal < fiNumber && months < maxMonths) {
			bal = bal * (1 + monthlyRate) + monthlySavings;
			months += 1;
			if (monthlySavings <= 0 && monthlyRate <= 0) break;
		}

		const reachable = bal >= fiNumber;
		const yearsToFi = reachable ? Math.round((months / 12) * 10) / 10 : null;
		const targetYear = reachable ? new Date().getFullYear() + Math.ceil(months / 12) : null;
		return { fiNumber, progressPct, yearsToFi, targetYear, reachable };
	});
</script>

<div class="card-surface rounded-2xl p-6 space-y-5 border-violet-500/25">
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
		<div>
			<div class="flex items-center gap-2">
				<Flame class="w-4 h-4 text-violet-400" />
				<h2 class="text-base font-semibold text-white">Financial Independence (FI / 4% Rule)</h2>
			</div>
			<p class="text-xs text-slate-400 mt-0.5">
				Deterministic CFP projection of your 25× FI Number and years to work-optional freedom.
			</p>
		</div>
		<button
			type="button"
			onclick={() =>
				goto(
					`/advisor?q=${encodeURIComponent(
						`Build a personalized Financial Independence roadmap for me: my target FI number is ${Math.round(fiCalc.fiNumber)} ${currency} (${annualExpenses}/yr expenses at ${swrPct}% SWR), saving ${monthlySavings}/mo at ${expectedReturnPct}% return.`
					)}`
				)}
			class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/35 text-violet-200 text-xs font-semibold cursor-pointer shrink-0"
		>
			<Sparkles class="w-3.5 h-3.5" /> Ask Luna FI Plan
		</button>
	</div>

	<div class="grid lg:grid-cols-12 gap-6 items-center">
		<!-- Inputs & Sliders -->
		<div class="lg:col-span-7 space-y-4">
			<div class="grid sm:grid-cols-3 gap-3 text-xs">
				<div>
					<label for="fi-port" class="block text-slate-400 mb-1">Current Portfolio ({currency})</label>
					<input
						id="fi-port"
						type="number"
						min="0"
						bind:value={currentPortfolio}
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white font-mono-num"
					/>
				</div>
				<div>
					<label for="fi-exp" class="block text-slate-400 mb-1">Annual Expenses ({currency})</label>
					<input
						id="fi-exp"
						type="number"
						min="1200"
						step="500"
						bind:value={annualExpenses}
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white font-mono-num"
					/>
				</div>
				<div>
					<label for="fi-swr" class="block text-slate-400 mb-1">Withdrawal Rate</label>
					<select
						id="fi-swr"
						bind:value={swrPct}
						class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white font-mono-num"
					>
						<option value={3.5}>3.5% (Conservative · 28.6×)</option>
						<option value={4.0}>4.0% (Classic · 25×)</option>
						<option value={4.5}>4.5% (Flexible · 22.2×)</option>
					</select>
				</div>
			</div>

			<div class="grid sm:grid-cols-2 gap-4">
				<div class="space-y-1.5">
					<div class="flex items-center justify-between text-xs">
						<span class="text-slate-400">Monthly Investment</span>
						<span class="font-mono-num font-semibold text-emerald-300 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(monthlySavings, currency)}/mo
						</span>
					</div>
					<input
						type="range"
						min={0}
						max={Math.max(5000, monthlySavings * 2)}
						step={50}
						bind:value={monthlySavings}
						class="w-full accent-emerald-400 cursor-pointer"
					/>
				</div>

				<div class="space-y-1.5">
					<div class="flex items-center justify-between text-xs">
						<span class="text-slate-400">Real Annual Return</span>
						<span class="font-mono-num font-semibold text-cyan-300">{expectedReturnPct.toFixed(1)}%</span>
					</div>
					<input
						type="range"
						min={3}
						max={10}
						step={0.5}
						bind:value={expectedReturnPct}
						class="w-full accent-cyan-400 cursor-pointer"
					/>
				</div>
			</div>
		</div>

		<!-- Results Card -->
		<div class="lg:col-span-5 p-4 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-3.5">
			<div class="flex items-baseline justify-between gap-2">
				<div>
					<div class="text-[11px] text-slate-400">Your FI Number</div>
					<div class="text-2xl font-bold font-mono-num text-white mt-0.5 {privacyMode ? 'privacy-blur' : ''}">
						{formatMoney(fiCalc.fiNumber, currency)}
					</div>
				</div>
				<div class="text-right">
					<div class="text-[11px] text-slate-400">Est. Time to FI</div>
					<div class="text-xl font-bold font-mono-num text-violet-300 mt-0.5">
						{#if fiCalc.yearsToFi === 0}
							Reached!
						{:else if fiCalc.yearsToFi !== null}
							{fiCalc.yearsToFi} yrs
						{:else}
							60+ yrs
						{/if}
					</div>
				</div>
			</div>

			<div class="space-y-1.5">
				<div class="flex items-center justify-between text-[11px] font-mono-num">
					<span class="text-slate-400">Progress to FI</span>
					<span class="text-emerald-300 font-semibold">{fiCalc.progressPct}%</span>
				</div>
				<div class="h-2 rounded-full bg-slate-800 overflow-hidden">
					<div
						class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-violet-400 transition-all"
						style="width: {fiCalc.progressPct}%"
					></div>
				</div>
			</div>

			<div class="text-[11px] text-slate-400 font-mono-num flex items-center justify-between pt-1 border-t border-slate-800/80">
				<span>Target FI Year</span>
				<span class="text-white font-semibold">
					{fiCalc.targetYear ? fiCalc.targetYear : 'Increase monthly savings'}
				</span>
			</div>
		</div>
	</div>
</div>
