<script lang="ts">
	import { page } from '$app/state';
	import {
		Sparkles,
		Home,
		ArrowLeft,
		RefreshCw,
		Compass,
		ShieldAlert,
		LayoutDashboard,
		Wallet,
		ArrowLeftRight,
		PieChart,
		UploadCloud,
		Copy,
		Check
	} from 'lucide-svelte';

	let status = $derived(page.status);
	let is404 = $derived(status === 404);
	let isAuthErr = $derived(status === 401 || status === 403);
	let errorMessage = $derived(page.error?.message || '');
	let currentPath = $derived(page.url.pathname);

	let copied = $state(false);
	let showDetails = $state(false);

	const QUICK_LINKS = [
		{ href: '/', label: 'Dashboard', desc: 'CFO overview', icon: LayoutDashboard },
		{ href: '/advisor', label: 'Luna AI', desc: 'Personal CFO chat', icon: Sparkles },
		{ href: '/accounts', label: 'Accounts', desc: 'Balances & cards', icon: Wallet },
		{ href: '/transactions', label: 'Transactions', desc: 'Full ledger', icon: ArrowLeftRight },
		{ href: '/budgets', label: 'Budgets', desc: 'Monthly pacing', icon: PieChart },
		{ href: '/imports', label: 'AI Imports', desc: 'BOG PDF & CSV', icon: UploadCloud }
	];

	function goBack() {
		if (typeof window !== 'undefined' && window.history.length > 1) {
			window.history.back();
		} else if (typeof window !== 'undefined') {
			window.location.href = '/';
		}
	}

	function reloadPage() {
		if (typeof window !== 'undefined') {
			window.location.reload();
		}
	}

	async function copyDiagnostics() {
		const text = `Financinio Error Report\nStatus: ${status}\nPath: ${currentPath}\nMessage: ${errorMessage || 'N/A'}\nTime: ${new Date().toISOString()}`;
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// ignore clipboard failures
		}
	}
</script>

<svelte:head>
	<title>{is404 ? '404 · Page Not Found' : `Error ${status}`} — Financinio</title>
</svelte:head>

<div class="min-h-dvh w-full bg-slate-950 text-slate-100 relative overflow-hidden flex items-center justify-center px-4 py-12">
	<!-- Ambient Aurora Glow -->
	<div
		class="pointer-events-none absolute -top-32 left-1/2 -translate-x-1/2 w-[520px] h-[520px] rounded-full blur-3xl {is404
			? 'bg-emerald-500/10'
			: 'bg-rose-500/12'}"
	></div>
	<div
		class="pointer-events-none absolute -bottom-40 right-1/4 w-[380px] h-[380px] rounded-full blur-3xl {is404
			? 'bg-cyan-500/10'
			: 'bg-amber-500/10'}"
	></div>

	<div class="relative z-10 w-full max-w-2xl space-y-8 text-center">
		<!-- Brand Pill -->
		<a
			href="/"
			class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 hover:border-emerald-500/40 transition"
		>
			<Sparkles class="w-3.5 h-3.5 text-emerald-400" />
			<span class="text-xs font-bold tracking-tight text-white">Financinio</span>
			<span class="text-[10px] text-slate-400 font-mono-num">· HTTP {status}</span>
		</a>

		<!-- Animated Visual Hero -->
		<div class="relative flex flex-col items-center justify-center py-2">
			<!-- Large Watermark Status Code -->
			<div
				class="text-[6.5rem] sm:text-[9rem] font-extrabold font-mono-num leading-none tracking-tighter select-none bg-gradient-to-b {is404
					? 'from-emerald-400/25 via-cyan-400/15 to-transparent'
					: 'from-rose-400/25 via-amber-400/15 to-transparent'} bg-clip-text text-transparent"
				aria-hidden="true"
			>
				{status}
			</div>

			<!-- Floating Orbital Badge centered over watermark -->
			<div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 fin-float">
				<div class="relative h-20 w-20 sm:h-24 sm:w-24 flex items-center justify-center">
					<svg viewBox="0 0 100 100" class="absolute inset-0 w-full h-full fin-orbit" aria-hidden="true">
						<circle
							cx="50"
							cy="50"
							r="45"
							fill="none"
							stroke={is404 ? 'rgba(52, 211, 153, 0.45)' : 'rgba(251, 113, 133, 0.45)'}
							stroke-width="2.5"
							stroke-dasharray="70 215"
							stroke-linecap="round"
						/>
					</svg>
					<div
						class="h-14 w-14 sm:h-16 sm:w-16 rounded-2xl border flex items-center justify-center shadow-2xl {is404
							? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300 shadow-emerald-950/60'
							: 'bg-rose-500/15 border-rose-500/35 text-rose-300 shadow-rose-950/60'}"
					>
						{#if is404}
							<Compass class="w-7 h-7 sm:w-8 sm:h-8" />
						{:else}
							<ShieldAlert class="w-7 h-7 sm:w-8 sm:h-8" />
						{/if}
					</div>
				</div>
			</div>
		</div>

		<!-- Heading & Description -->
		<div class="space-y-2.5 max-w-lg mx-auto">
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">
				{#if is404}
					This page isn't in your ledger.
				{:else if isAuthErr}
					Access restricted
				{:else}
					Something went off-balance.
				{/if}
			</h1>
			<p class="text-sm text-slate-400 leading-relaxed">
				{#if is404}
					The route
					<code class="px-2 py-0.5 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono-num text-xs">
						{currentPath}
					</code>
					could not be found. It may have been moved or typed incorrectly.
				{:else if isAuthErr}
					You don't have permission to view this page, or your session has expired. Sign in again to continue.
				{:else}
					An unexpected error interrupted this screen. Your financial data in Neon is completely safe — try reloading or returning to your Dashboard.
				{/if}
			</p>
		</div>

		<!-- Primary Action Buttons -->
		<div class="flex flex-wrap items-center justify-center gap-2.5">
			<a
				href={isAuthErr ? '/login' : '/'}
				class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm transition shadow-lg shadow-emerald-950/40"
			>
				<Home class="w-4 h-4" />
				{isAuthErr ? 'Sign In' : 'Back to Dashboard'}
			</a>

			<button
				type="button"
				onclick={goBack}
				class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-sm font-medium transition cursor-pointer"
			>
				<ArrowLeft class="w-4 h-4" />
				Go Back
			</button>

			{#if !is404}
				<button
					type="button"
					onclick={reloadPage}
					class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 text-cyan-200 text-sm font-semibold transition cursor-pointer"
				>
					<RefreshCw class="w-4 h-4" />
					Try Again
				</button>
			{/if}
		</div>

		<!-- Quick Jump Grid (for 404) or Technical Diagnostic Drawer (for 500/other errors) -->
		{#if is404}
			<div class="card-surface rounded-2xl p-4 sm:p-5 text-left space-y-3">
				<div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400 px-1">
					Quick Jump
				</div>
				<div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
					{#each QUICK_LINKS as item}
						{@const Icon = item.icon}
						<a
							href={item.href}
							class="flex items-center gap-2.5 p-2.5 rounded-xl bg-slate-950/70 hover:bg-slate-900 border border-slate-800/80 hover:border-emerald-500/35 transition group"
						>
							<div class="h-8 w-8 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-emerald-400 shrink-0 group-hover:scale-105 transition-transform">
								<Icon class="w-4 h-4" />
							</div>
							<div class="min-w-0">
								<div class="text-xs font-semibold text-white truncate">{item.label}</div>
								<div class="text-[10px] text-slate-500 truncate">{item.desc}</div>
							</div>
						</a>
					{/each}
				</div>
			</div>
		{:else}
			<div class="card-surface rounded-2xl p-4 text-left space-y-3 max-w-md mx-auto">
				<div class="flex items-center justify-between gap-2">
					<button
						type="button"
						onclick={() => (showDetails = !showDetails)}
						class="text-xs font-semibold text-slate-300 hover:text-white cursor-pointer"
					>
						{showDetails ? 'Hide' : 'Show'} Error Diagnostics
					</button>
					<button
						type="button"
						onclick={copyDiagnostics}
						class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 cursor-pointer"
					>
						{#if copied}
							<Check class="w-3 h-3 text-emerald-400" />
							<span class="text-emerald-400">Copied</span>
						{:else}
							<Copy class="w-3 h-3" /> Copy
						{/if}
					</button>
				</div>

				{#if showDetails}
					<div class="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono-num text-[11px] text-slate-400 space-y-1 break-all">
						<div><span class="text-slate-500">Status:</span> <span class="text-rose-300">{status}</span></div>
						<div><span class="text-slate-500">Path:</span> {currentPath}</div>
						{#if errorMessage}
							<div><span class="text-slate-500">Message:</span> {errorMessage}</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>
