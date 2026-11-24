<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { auth } from '$lib/stores/auth.svelte';
	import { ApiError } from '$lib/api/client';
	import {
		Sparkles,
		ShieldCheck,
		Layers,
		ArrowRight,
		Eye,
		EyeOff,
		Landmark,
		TrendingUp,
		Check,
		AlertTriangle,
		Lock,
		Mail,
		User as UserIcon
	} from 'lucide-svelte';

	const CURRENCY_OPTIONS = [
		{ code: 'GEL', symbol: '₾', name: 'Georgian Lari' },
		{ code: 'USD', symbol: '$', name: 'US Dollar' },
		{ code: 'EUR', symbol: '€', name: 'Euro' },
		{ code: 'GBP', symbol: '£', name: 'British Pound' },
		{ code: 'CAD', symbol: 'C$', name: 'Canadian Dollar' },
		{ code: 'AUD', symbol: 'A$', name: 'Australian Dollar' }
	];

	let mode = $state<'login' | 'register'>(
		page.url.searchParams.get('mode') === 'register' ? 'register' : 'login'
	);
	let email = $state('');
	let password = $state('');
	let showPassword = $state(false);
	let fullName = $state('');
	let baseCurrency = $state('GEL');
	let submitting = $state(false);
	let errorMsg = $state<string | null>(null);

	$effect(() => {
		if (!auth.loading && auth.user) {
			goto('/');
		}
	});

	let passwordScore = $derived.by(() => {
		if (!password) return 0;
		let score = 0;
		if (password.length >= 8) score += 1;
		if (password.length >= 12) score += 1;
		if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
		if (/[0-9]/.test(password) || /[^A-Za-z0-9]/.test(password)) score += 1;
		return score;
	});

	let passwordStrengthMeta = $derived.by(() => {
		if (!password) return { label: '', color: 'bg-slate-800', text: 'text-slate-500' };
		if (passwordScore <= 1) return { label: 'Weak', color: 'bg-rose-500', text: 'text-rose-400' };
		if (passwordScore === 2) return { label: 'Fair', color: 'bg-amber-400', text: 'text-amber-300' };
		if (passwordScore === 3) return { label: 'Good', color: 'bg-cyan-400', text: 'text-cyan-300' };
		return { label: 'Strong', color: 'bg-emerald-400', text: 'text-emerald-400' };
	});

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		errorMsg = null;
		submitting = true;
		try {
			if (mode === 'login') {
				await auth.login(email.trim(), password);
			} else {
				await auth.register(email.trim(), password, fullName.trim(), baseCurrency);
			}
			goto('/');
		} catch (err) {
			errorMsg =
				err instanceof ApiError
					? err.message
					: 'Unable to authenticate. Please check your connection.';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="min-h-dvh grid lg:grid-cols-12 bg-slate-950 relative overflow-hidden">
	<!-- Subtle Background Ambient Orbs -->
	<div
		class="pointer-events-none absolute -top-40 -left-32 h-[420px] w-[420px] rounded-full bg-emerald-500/10 blur-3xl"
	></div>
	<div
		class="pointer-events-none absolute -bottom-40 right-0 h-[380px] w-[380px] rounded-full bg-cyan-500/10 blur-3xl"
	></div>

	<!-- Left Showcase Panel (Desktop) -->
	<div
		class="hidden lg:flex lg:col-span-6 xl:col-span-7 flex-col justify-between p-10 xl:p-14 bg-gradient-to-br from-slate-900/90 via-slate-950 to-emerald-950/35 border-r border-slate-800/70 relative"
	>
		<!-- Brand Header -->
		<div class="flex items-center justify-between gap-4 relative z-10">
			<div class="flex items-center gap-3">
				<div
					class="h-11 w-11 rounded-2xl bg-gradient-to-br from-emerald-400/20 to-cyan-500/15 border border-emerald-500/35 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-950/40"
				>
					<Sparkles class="w-5 h-5" />
				</div>
				<div>
					<span class="text-xl font-bold tracking-tight text-white">Financinio</span>
					<p class="text-xs text-slate-400">AI Personal Finance & Wealth OS</p>
				</div>
			</div>

			<span
				class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-[11px] font-semibold"
			>
				<span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
				Luna Personal CFO Live
			</span>
		</div>

		<!-- Hero Value & Interactive Preview -->
		<div class="space-y-7 max-w-xl my-auto py-8 relative z-10">
			<div class="space-y-3">
				<h1 class="text-4xl xl:text-[42px] font-bold tracking-tight text-white leading-[1.12]">
					Master your cash flow & wealth with <span class="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-300">AI you control</span>.
				</h1>
				<p class="text-slate-400 text-sm xl:text-base leading-relaxed">
					Import Bank of Georgia PDFs, CSVs, Excel sheets, or receipts in seconds. Every row is reconciled, categorized by self-learning Upstash Vector memory, and approved by you before touching your ledger.
				</p>
			</div>

			<!-- Simulated Live Cockpit Preview Card -->
			<div class="rounded-2xl bg-slate-950/85 border border-slate-800/90 p-5 space-y-4 shadow-2xl">
				<div class="flex items-center justify-between gap-3">
					<div>
						<div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
							Wealth Cockpit Preview
						</div>
						<div class="text-2xl font-bold font-mono-num text-white mt-0.5 flex items-baseline gap-2">
							<span>₾ 48,920.00</span>
							<span class="text-xs font-semibold text-emerald-400 inline-flex items-center gap-0.5">
								<TrendingUp class="w-3.5 h-3.5" /> +14.2%
							</span>
						</div>
					</div>
					<div class="px-3 py-1.5 rounded-xl bg-emerald-500/12 border border-emerald-500/30 text-right">
						<div class="text-[10px] text-emerald-300 font-medium">Health Score</div>
						<div class="text-sm font-bold font-mono-num text-white">86 / 100</div>
					</div>
				</div>

				<div class="p-3 rounded-xl bg-gradient-to-r from-violet-500/10 via-cyan-500/8 to-transparent border border-violet-500/20 flex items-start gap-2.5 text-xs">
					<Sparkles class="w-4 h-4 text-violet-300 shrink-0 mt-0.5" />
					<p class="text-slate-300 leading-relaxed">
						<strong class="text-white">Luna CFO:</strong> Your emergency fund covers <strong class="text-emerald-300">5.4 months</strong> of expenses. Redirecting ₾ 240/mo from dining hits your 6-month target 4 months early.
					</p>
				</div>
			</div>

			<!-- 3 Key Pillars -->
			<div class="grid sm:grid-cols-3 gap-3">
				<div class="p-3.5 rounded-xl bg-slate-900/55 border border-slate-800/80 space-y-1.5">
					<Landmark class="w-4 h-4 text-orange-400" />
					<div class="text-xs font-semibold text-white">BOG GE PDF Engine</div>
					<p class="text-[11px] text-slate-400 leading-relaxed">
						0-token Georgian PDF parser with exact balance math.
					</p>
				</div>
				<div class="p-3.5 rounded-xl bg-slate-900/55 border border-slate-800/80 space-y-1.5">
					<Layers class="w-4 h-4 text-cyan-400" />
					<div class="text-xs font-semibold text-white">Self-Learning AI</div>
					<p class="text-[11px] text-slate-400 leading-relaxed">
						Rules → Upstash Vector → LLM with 1-click HITL review.
					</p>
				</div>
				<div class="p-3.5 rounded-xl bg-slate-900/55 border border-slate-800/80 space-y-1.5">
					<ShieldCheck class="w-4 h-4 text-emerald-400" />
					<div class="text-xs font-semibold text-white">Private & Portable</div>
					<p class="text-[11px] text-slate-400 leading-relaxed">
						Privacy blur mode, audit logs & instant CSV/JSON export.
					</p>
				</div>
			</div>
		</div>

		<p class="text-[11px] text-slate-500 relative z-10">
			Powered by FastAPI · SvelteKit · Neon Postgres · Upstash Vector · LangGraph · LangSmith
		</p>
	</div>

	<!-- Right Auth Column -->
	<div class="lg:col-span-6 xl:col-span-5 flex items-center justify-center p-5 sm:p-10 relative z-10">
		<div class="w-full max-w-md space-y-6">
			<!-- Mobile Brand Mark -->
			<div class="lg:hidden flex flex-col items-center text-center gap-2">
				<div
					class="h-12 w-12 rounded-2xl bg-gradient-to-br from-emerald-400/20 to-cyan-500/15 border border-emerald-500/35 flex items-center justify-center text-emerald-400"
				>
					<Sparkles class="w-6 h-6" />
				</div>
				<div>
					<span class="text-2xl font-bold tracking-tight text-white">Financinio</span>
					<p class="text-xs text-slate-400">AI Personal Finance & Wealth OS</p>
				</div>
			</div>

			<div class="card-surface rounded-2xl p-6 sm:p-8 space-y-6 border border-slate-800/90 shadow-2xl">
				<!-- Mode Switcher -->
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-950/90 border border-slate-800">
					<button
						type="button"
						onclick={() => {
							mode = 'login';
							errorMsg = null;
						}}
						class="py-2.5 text-xs sm:text-sm font-semibold rounded-lg transition cursor-pointer {mode === 'login'
							? 'bg-slate-800 text-white shadow'
							: 'text-slate-400 hover:text-slate-200'}"
					>
						Sign In
					</button>
					<button
						type="button"
						onclick={() => {
							mode = 'register';
							errorMsg = null;
						}}
						class="py-2.5 text-xs sm:text-sm font-semibold rounded-lg transition cursor-pointer {mode === 'register'
							? 'bg-slate-800 text-white shadow'
							: 'text-slate-400 hover:text-slate-200'}"
					>
						Create Account
					</button>
				</div>

				<div>
					<h2 class="text-xl sm:text-2xl font-bold text-white tracking-tight">
						{mode === 'login' ? 'Welcome back' : 'Create your workspace'}
					</h2>
					<p class="text-xs sm:text-sm text-slate-400 mt-1">
						{mode === 'login'
							? 'Sign in to access your financial command center.'
							: 'Set up your personal CFO, smart budgets, and AI statement imports.'}
					</p>
				</div>

				{#if errorMsg}
					<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-200 text-xs sm:text-sm flex items-start gap-2.5">
						<AlertTriangle class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
						<span>{errorMsg}</span>
					</div>
				{/if}

				<form onsubmit={handleSubmit} class="space-y-4">
					{#if mode === 'register'}
						<div>
							<label for="fullName" class="block text-xs font-medium text-slate-300 mb-1.5">
								Full Name
							</label>
							<div class="relative">
								<UserIcon class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
								<input
									id="fullName"
									type="text"
									required
									autocomplete="name"
									bind:value={fullName}
									placeholder="Alex Morgan"
									class="w-full pl-10 pr-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 transition"
								/>
							</div>
						</div>
					{/if}

					<div>
						<label for="email" class="block text-xs font-medium text-slate-300 mb-1.5">
							Email Address
						</label>
						<div class="relative">
							<Mail class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
							<input
								id="email"
								type="email"
								required
								autocomplete="email"
								bind:value={email}
								placeholder="you@domain.com"
								class="w-full pl-10 pr-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 transition"
							/>
						</div>
					</div>

					<div>
						<div class="flex items-center justify-between mb-1.5">
							<label for="password" class="block text-xs font-medium text-slate-300">Password</label>
							{#if mode === 'register' && password}
								<span class="text-[11px] font-semibold {passwordStrengthMeta.text}">
									{passwordStrengthMeta.label}
								</span>
							{/if}
						</div>
						<div class="relative">
							<Lock class="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
							<input
								id="password"
								type={showPassword ? 'text' : 'password'}
								required
								minlength={8}
								autocomplete={mode === 'login' ? 'current-password' : 'new-password'}
								bind:value={password}
								placeholder="Minimum 8 characters"
								class="w-full pl-10 pr-10 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 transition"
							/>
							<button
								type="button"
								onclick={() => (showPassword = !showPassword)}
								aria-label={showPassword ? 'Hide password' : 'Show password'}
								class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white cursor-pointer"
							>
								{#if showPassword}
									<EyeOff class="w-4 h-4" />
								{:else}
									<Eye class="w-4 h-4" />
								{/if}
							</button>
						</div>

						{#if mode === 'register'}
							<div class="mt-2 space-y-1.5">
								<div class="grid grid-cols-4 gap-1.5">
									{#each [1, 2, 3, 4] as seg}
										<div
											class="h-1 rounded-full transition-colors {passwordScore >= seg
												? passwordStrengthMeta.color
												: 'bg-slate-800'}"
										></div>
									{/each}
								</div>
								<div class="flex items-center gap-3 text-[11px] text-slate-500">
									<span class="inline-flex items-center gap-1 {password.length >= 8 ? 'text-emerald-400' : ''}">
										<Check class="w-3 h-3" /> 8+ chars
									</span>
									<span class="inline-flex items-center gap-1 {/[0-9]/.test(password) ? 'text-emerald-400' : ''}">
										<Check class="w-3 h-3" /> Number
									</span>
									<span class="inline-flex items-center gap-1 {/[A-Z]/.test(password) ? 'text-emerald-400' : ''}">
										<Check class="w-3 h-3" /> Uppercase
									</span>
								</div>
							</div>
						{/if}
					</div>

					{#if mode === 'register'}
						<div>
							<span class="block text-xs font-medium text-slate-300 mb-1.5">Base Currency</span>
							<div class="grid grid-cols-3 gap-2">
								{#each CURRENCY_OPTIONS as cur}
									<button
										type="button"
										onclick={() => (baseCurrency = cur.code)}
										class="py-2 px-2.5 rounded-xl border text-left transition cursor-pointer {baseCurrency === cur.code
											? 'bg-emerald-500/15 border-emerald-500/50 text-white'
											: 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'}"
									>
										<div class="text-xs font-bold font-mono-num flex items-center justify-between">
											<span>{cur.symbol} {cur.code}</span>
											{#if baseCurrency === cur.code}
												<Check class="w-3 h-3 text-emerald-400" />
											{/if}
										</div>
										<div class="text-[10px] text-slate-500 truncate mt-0.5">{cur.name}</div>
									</button>
								{/each}
							</div>
						</div>
					{/if}

					<button
						type="submit"
						disabled={submitting}
						class="w-full py-3 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-950 font-semibold text-sm flex items-center justify-center gap-2 transition cursor-pointer shadow-lg shadow-emerald-500/20"
					>
						{#if submitting}
							<span class="h-4 w-4 rounded-full border-2 border-slate-950 border-t-transparent animate-spin"></span>
							{mode === 'login' ? 'Signing in...' : 'Creating workspace...'}
						{:else}
							{mode === 'login' ? 'Sign In to Workspace' : 'Create Free Workspace'}
							<ArrowRight class="w-4 h-4" />
						{/if}
					</button>
				</form>

				<div class="pt-2 border-t border-slate-800/80 text-center text-xs text-slate-400">
					{#if mode === 'login'}
						New to Financinio?
						<button
							type="button"
							onclick={() => {
								mode = 'register';
								errorMsg = null;
							}}
							class="text-emerald-400 hover:text-emerald-300 font-semibold ml-1 cursor-pointer"
						>
							Create an account
						</button>
					{:else}
						Already have a workspace?
						<button
							type="button"
							onclick={() => {
								mode = 'login';
								errorMsg = null;
							}}
							class="text-emerald-400 hover:text-emerald-300 font-semibold ml-1 cursor-pointer"
						>
							Sign in
						</button>
					{/if}
				</div>
			</div>

			<div class="flex items-center justify-center gap-4 text-[11px] text-slate-500">
				<span class="inline-flex items-center gap-1">
					<ShieldCheck class="w-3.5 h-3.5 text-emerald-500/80" /> Encrypted Sessions
				</span>
				<span>·</span>
				<span>Zero Ads</span>
				<span>·</span>
				<span>Full Data Export</span>
			</div>
		</div>
	</div>
</div>
