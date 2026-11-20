<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth.svelte';
	import { ApiError } from '$lib/api/client';
	import { Sparkles, ShieldCheck, Layers, ArrowRight } from 'lucide-svelte';

	let mode = $state<'login' | 'register'>('login');
	let email = $state('');
	let password = $state('');
	let fullName = $state('');
	let baseCurrency = $state('USD');
	let submitting = $state(false);
	let errorMsg = $state<string | null>(null);

	$effect(() => {
		if (!auth.loading && auth.user) {
			goto('/');
		}
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		errorMsg = null;
		submitting = true;
		try {
			if (mode === 'login') {
				await auth.login(email, password);
			} else {
				await auth.register(email, password, fullName, baseCurrency);
			}
			goto('/');
		} catch (err) {
			errorMsg = err instanceof ApiError ? err.message : 'Unable to authenticate. Please check your connection.';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="min-h-screen grid lg:grid-cols-2 bg-slate-950">
	<!-- Left brand & value panel -->
	<div class="hidden lg:flex flex-col justify-between p-12 bg-gradient-to-br from-slate-900 via-slate-950 to-emerald-950/40 border-r border-slate-800/70">
		<div class="flex items-center gap-3">
			<div class="h-10 w-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
				<Sparkles class="w-5 h-5" />
			</div>
			<div>
				<span class="text-xl font-bold tracking-tight text-white">Financinio</span>
				<p class="text-xs text-slate-400">AI Personal Finance & Wealth</p>
			</div>
		</div>

		<div class="space-y-8 max-w-lg">
			<h1 class="text-4xl font-bold tracking-tight text-white leading-tight">
				Your cash flow, net worth, and documents — organized by <span class="text-emerald-400">AI you control</span>.
			</h1>
			<p class="text-slate-400 text-base leading-relaxed">
				Drop in CSV, Excel, PDF bank statements, or receipts. Our LangGraph pipeline parses, deduplicates, categorizes with Upstash Vector memory, and pauses for your one-click review before touching your ledger.
			</p>

			<div class="grid gap-4 pt-2">
				<div class="flex items-start gap-3.5 p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
					<Layers class="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
					<div>
						<div class="text-sm font-semibold text-white">Self-Learning 3-Tier Categorization</div>
						<p class="text-xs text-slate-400 mt-0.5">Deterministic rules, Upstash Vector merchant memory, and structured LLM classification.</p>
					</div>
				</div>
				<div class="flex items-start gap-3.5 p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
					<ShieldCheck class="w-5 h-5 text-cyan-400 mt-0.5 shrink-0" />
					<div>
						<div class="text-sm font-semibold text-white">Human-in-the-Loop Ledger Integrity</div>
						<p class="text-xs text-slate-400 mt-0.5">Balance reconciliation, fingerprint deduplication, and explicit approval before commit.</p>
					</div>
				</div>
			</div>
		</div>

		<p class="text-xs text-slate-500">
			Powered by FastAPI · SvelteKit · Neon Postgres · Upstash Vector · LangChain · LangGraph · LangSmith
		</p>
	</div>

	<!-- Right auth form -->
	<div class="flex items-center justify-center p-6 sm:p-12">
		<div class="w-full max-w-md space-y-8">
			<div class="lg:hidden flex items-center gap-3 justify-center">
				<div class="h-10 w-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
					<Sparkles class="w-5 h-5" />
				</div>
				<span class="text-2xl font-bold text-white">Financinio</span>
			</div>

			<div class="card-surface rounded-2xl p-8 space-y-6">
				<div>
					<h2 class="text-2xl font-semibold text-white">
						{mode === 'login' ? 'Welcome back' : 'Create your workspace'}
					</h2>
					<p class="text-sm text-slate-400 mt-1">
						{mode === 'login'
							? 'Sign in to access your financial command center.'
							: 'Start tracking cash flow and importing statements with AI.'}
					</p>
				</div>

				<!-- Mode switcher -->
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-950/80 border border-slate-800">
					<button
						type="button"
						onclick={() => { mode = 'login'; errorMsg = null; }}
						class="py-2 text-sm font-medium rounded-lg transition {mode === 'login'
							? 'bg-slate-800 text-white shadow'
							: 'text-slate-400 hover:text-slate-200'}"
					>
						Sign In
					</button>
					<button
						type="button"
						onclick={() => { mode = 'register'; errorMsg = null; }}
						class="py-2 text-sm font-medium rounded-lg transition {mode === 'register'
							? 'bg-slate-800 text-white shadow'
							: 'text-slate-400 hover:text-slate-200'}"
					>
						Create Account
					</button>
				</div>

				{#if errorMsg}
					<div class="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
						{errorMsg}
					</div>
				{/if}

				<form onsubmit={handleSubmit} class="space-y-4">
					{#if mode === 'register'}
						<div>
							<label for="fullName" class="block text-xs font-medium text-slate-300 mb-1.5">Full Name</label>
							<input
								id="fullName"
								type="text"
								required
								bind:value={fullName}
								placeholder="Alex Morgan"
								class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
							/>
						</div>
					{/if}

					<div>
						<label for="email" class="block text-xs font-medium text-slate-300 mb-1.5">Email Address</label>
						<input
							id="email"
							type="email"
							required
							bind:value={email}
							placeholder="you@domain.com"
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
						/>
					</div>

					<div>
						<label for="password" class="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
						<input
							id="password"
							type="password"
							required
							minlength={8}
							bind:value={password}
							placeholder="Minimum 8 characters"
							class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
						/>
					</div>

					{#if mode === 'register'}
						<div>
							<label for="currency" class="block text-xs font-medium text-slate-300 mb-1.5">Base Currency</label>
							<select
								id="currency"
								bind:value={baseCurrency}
								class="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
							>
								<option value="USD">USD — US Dollar</option>
								<option value="EUR">EUR — Euro</option>
								<option value="GBP">GBP — British Pound</option>
								<option value="GEL">GEL — Georgian Lari</option>
								<option value="CAD">CAD — Canadian Dollar</option>
								<option value="AUD">AUD — Australian Dollar</option>
							</select>
						</div>
					{/if}

					<button
						type="submit"
						disabled={submitting}
						class="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-950 font-semibold text-sm flex items-center justify-center gap-2 transition cursor-pointer"
					>
						{submitting ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Workspace'}
						<ArrowRight class="w-4 h-4" />
					</button>
				</form>
			</div>
		</div>
	</div>
</div>
