<script lang="ts">
	import { onDestroy } from 'svelte';
	import {
		ShieldCheck,
		FileSearch,
		Brain,
		CheckCircle2,
		Landmark,
		Sparkles
	} from 'lucide-svelte';

	interface Props {
		mode: 'bog' | 'general';
		filename: string;
	}

	let { mode, filename }: Props = $props();

	let activeStage = $state(0);

	const stages = $derived(
		mode === 'bog'
			? [
					{
						label: 'Securing & storing Bank of Georgia PDF',
						sub: 'SHA-256 checksum + encrypted object storage'
					},
					{
						label: 'Extracting Georgian text & table coordinates',
						sub: 'Parsing ობიექტი, MCC codes, multi-currency GEL/USD/EUR'
					},
					{
						label: 'Reconciling opening & closing balances',
						sub: 'Verifying every debit, credit, and commission deterministically'
					},
					{
						label: 'Deduplicating & staging HITL review queue',
						sub: '0 AI tokens · Matching against Upstash Vector & personal rules'
					}
				]
			: [
					{
						label: 'Securing & uploading financial document',
						sub: 'Detecting CSV, Excel, PDF statement, or receipt image'
					},
					{
						label: 'Running LangGraph extraction pipeline',
						sub: 'Extracting dates, amounts, currencies, and merchant narratives'
					},
					{
						label: 'Categorizing via Rules → Vector Memory → AI',
						sub: 'Querying Upstash Vector for your confirmed merchant history'
					},
					{
						label: 'Building your Human-in-the-Loop review queue',
						sub: 'Checking duplicate fingerprints before touching Neon ledger'
					}
				]
	);

	const timer = setInterval(() => {
		if (activeStage < 3) activeStage += 1;
	}, 1600);

	onDestroy(() => clearInterval(timer));
</script>

<div
	class="relative overflow-hidden rounded-2xl border p-6 sm:p-8 {mode === 'bog'
		? 'bg-gradient-to-br from-orange-950/40 via-slate-950 to-slate-950 border-orange-500/35'
		: 'bg-gradient-to-br from-emerald-950/35 via-slate-950 to-cyan-950/30 border-emerald-500/35'}"
>
	<!-- Animated Glow Accent -->
	<div
		class="pointer-events-none absolute -top-24 -right-24 h-56 w-56 rounded-full blur-3xl opacity-25 {mode === 'bog'
			? 'bg-orange-500'
			: 'bg-emerald-500'}"
	></div>

	<div class="relative z-10 max-w-xl mx-auto space-y-6">
		<div class="flex items-center gap-3.5">
			<div
				class="h-12 w-12 rounded-2xl flex items-center justify-center border shrink-0 animate-pulse {mode === 'bog'
					? 'bg-orange-500/15 border-orange-500/40 text-orange-300'
					: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'}"
			>
				{#if mode === 'bog'}
					<Landmark class="w-6 h-6" />
				{:else}
					<Sparkles class="w-6 h-6" />
				{/if}
			</div>
			<div class="min-w-0">
				<div class="text-xs font-semibold uppercase tracking-wider {mode === 'bog' ? 'text-orange-300' : 'text-emerald-300'}">
					{mode === 'bog' ? 'Bank of Georgia Deterministic Engine' : 'LangGraph AI Ingestion Pipeline'}
				</div>
				<h3 class="text-base font-bold text-white truncate mt-0.5">{filename}</h3>
			</div>
		</div>

		<!-- Stepper -->
		<div class="space-y-3">
			{#each stages as step, idx}
				{@const done = idx < activeStage}
				{@const current = idx === activeStage}
				<div
					class="flex items-start gap-3 p-3 rounded-xl border transition-all duration-300 {current
						? mode === 'bog'
							? 'bg-orange-500/10 border-orange-500/35'
							: 'bg-emerald-500/10 border-emerald-500/35'
						: done
							? 'bg-slate-900/60 border-slate-800/80 opacity-85'
							: 'bg-slate-950/40 border-slate-800/40 opacity-45'}"
				>
					<div class="mt-0.5 shrink-0">
						{#if done}
							<CheckCircle2 class="w-4 h-4 text-emerald-400" />
						{:else if current}
							<span
								class="block h-4 w-4 rounded-full border-2 border-t-transparent animate-spin {mode === 'bog'
									? 'border-orange-400'
									: 'border-emerald-400'}"
							></span>
						{:else if idx === 1}
							<FileSearch class="w-4 h-4 text-slate-500" />
						{:else if idx === 2}
							<Brain class="w-4 h-4 text-slate-500" />
						{:else}
							<ShieldCheck class="w-4 h-4 text-slate-500" />
						{/if}
					</div>
					<div class="min-w-0">
						<div class="text-xs font-semibold {current ? 'text-white' : done ? 'text-slate-200' : 'text-slate-400'}">
							{step.label}
						</div>
						<div class="text-[11px] text-slate-400 mt-0.5">{step.sub}</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>
