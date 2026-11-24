<script lang="ts">
	import type { FinancialHealthProfile } from '$lib/api/types';
	import { ShieldCheck, Sparkles, ArrowRight } from 'lucide-svelte';

	let {
		profile,
		onAskLuna
	}: {
		profile: FinancialHealthProfile;
		onAskLuna: (prompt: string) => void;
	} = $props();

	const R = 48;
	const CIRC = 2 * Math.PI * R;

	let score = $derived(profile.health_score.overall);
	let dashOffset = $derived(CIRC * (1 - Math.min(100, Math.max(0, score)) / 100));

	let ringStroke = $derived(score >= 75 ? '#34d399' : score >= 50 ? '#fbbf24' : '#fb7185');
	let gradeBadgeClass = $derived(
		score >= 75
			? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
			: score >= 50
				? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
				: 'bg-rose-500/15 text-rose-300 border-rose-500/30'
	);

	let pillars = $derived([
		{
			key: 'cash_flow_and_savings',
			label: 'Cash Flow',
			score: profile.health_score.pillars.cash_flow_and_savings.score,
			max: profile.health_score.pillars.cash_flow_and_savings.max,
			prompt: 'Analyze my cash flow & savings rate pillar and tell me how to push my savings rate above 20%.'
		},
		{
			key: 'emergency_runway',
			label: 'Runway',
			score: profile.health_score.pillars.emergency_runway.score,
			max: profile.health_score.pillars.emergency_runway.max,
			prompt: 'Evaluate my emergency fund runway and build a concrete plan to reach 6 months of expenses.'
		},
		{
			key: 'debt_health',
			label: 'Debt Health',
			score: profile.health_score.pillars.debt_health.score,
			max: profile.health_score.pillars.debt_health.max,
			prompt: 'Review my debt health pillar and recommend the fastest payoff strategy.'
		},
		{
			key: 'budget_and_goals',
			label: 'Budgets & Goals',
			score: profile.health_score.pillars.budget_and_goals.score,
			max: profile.health_score.pillars.budget_and_goals.max,
			prompt: 'Audit my budget discipline and active goals, and suggest smart adjustments.'
		}
	]);
</script>

<div class="card-surface rounded-2xl p-5 sm:p-6 flex flex-col justify-between gap-5 border-emerald-500/20">
	<div class="flex items-center justify-between gap-2">
		<div class="flex items-center gap-2">
			<ShieldCheck class="w-4 h-4 text-emerald-400" />
			<h2 class="text-sm font-semibold text-white">CFP Financial Health</h2>
		</div>
		<span class="px-2.5 py-0.5 rounded-full border text-[10px] font-semibold {gradeBadgeClass}">
			{profile.health_score.grade}
		</span>
	</div>

	<div class="flex flex-col sm:flex-row items-center gap-5">
		<!-- Circular Score Gauge -->
		<button
			type="button"
			onclick={() =>
				onAskLuna(
					'Run a full Senior Financial Advisor checkup on my Financial Health Score and give me my top 3 priorities.'
				)}
			class="relative w-32 h-32 shrink-0 group cursor-pointer"
			title="Click for full CFP Health Checkup with Luna"
		>
			<svg viewBox="0 0 120 120" class="w-full h-full -rotate-90" role="img" aria-label="Financial health score {score} out of 100">
				<circle
					cx="60"
					cy="60"
					r={R}
					fill="none"
					stroke="rgba(148, 163, 184, 0.14)"
					stroke-width="10"
				/>
				<circle
					cx="60"
					cy="60"
					r={R}
					fill="none"
					stroke={ringStroke}
					stroke-width="10"
					stroke-linecap="round"
					stroke-dasharray={CIRC}
					stroke-dashoffset={dashOffset}
					class="transition-all duration-700"
				/>
			</svg>
			<div class="absolute inset-0 flex flex-col items-center justify-center">
				<span class="text-3xl font-bold text-white font-mono-num leading-none">{score}</span>
				<span class="text-[10px] text-slate-400 font-mono-num mt-1">out of 100</span>
			</div>
		</button>

		<!-- 4 Interactive Pillar Bars -->
		<div class="flex-1 w-full space-y-2.5">
			{#each pillars as p}
				{@const pct = Math.round((p.score / p.max) * 100)}
				<button
					type="button"
					onclick={() => onAskLuna(p.prompt)}
					class="w-full text-left group cursor-pointer space-y-1"
				>
					<div class="flex items-center justify-between text-xs">
						<span class="text-slate-300 group-hover:text-white transition font-medium">{p.label}</span>
						<span class="font-mono-num text-[11px] text-slate-400">
							<span class="text-slate-200 font-semibold">{p.score}</span>/{p.max}
						</span>
					</div>
					<div class="h-1.5 rounded-full bg-slate-800/90 overflow-hidden">
						<div
							class="h-full rounded-full transition-all duration-500 {pct >= 75
								? 'bg-emerald-400'
								: pct >= 45
									? 'bg-amber-400'
									: 'bg-rose-400'}"
							style="width: {pct}%"
						></div>
					</div>
				</button>
			{/each}
		</div>
	</div>

	<!-- Top Priority CFO Action -->
	<button
		type="button"
		onclick={() =>
			onAskLuna(
				`Help me act on my #1 financial priority: "${profile.health_score.top_priority}". Give me a concrete 30-day plan.`
			)}
		class="w-full text-left p-3.5 rounded-xl bg-emerald-500/8 hover:bg-emerald-500/14 border border-emerald-500/25 hover:border-emerald-500/45 transition cursor-pointer group space-y-1"
	>
		<div class="flex items-center justify-between gap-2 text-[11px] font-semibold text-emerald-300">
			<span class="flex items-center gap-1.5">
				<Sparkles class="w-3.5 h-3.5" /> #1 CFO Priority
			</span>
			<span class="inline-flex items-center gap-1 text-[10px] group-hover:translate-x-0.5 transition-transform">
				Ask Luna <ArrowRight class="w-3 h-3" />
			</span>
		</div>
		<p class="text-xs text-slate-200 leading-relaxed">
			{profile.health_score.top_priority}
		</p>
	</button>
</div>
