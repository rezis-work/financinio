<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { auth } from '$lib/stores/auth.svelte';
	import {
		LayoutDashboard,
		Wallet,
		ArrowLeftRight,
		UploadCloud,
		PieChart,
		Repeat,
		Target,
		Settings,
		LogOut,
		Sparkles,
		Menu,
		X
	} from 'lucide-svelte';

	let { children } = $props();
	let mobileOpen = $state(false);

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: LayoutDashboard },
		{ href: '/advisor', label: 'Luna AI Advisor', icon: Sparkles },
		{ href: '/accounts', label: 'Accounts', icon: Wallet },
		{ href: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
		{ href: '/budgets', label: 'Budgets', icon: PieChart },
		{ href: '/recurring', label: 'Recurring', icon: Repeat },
		{ href: '/wealth', label: 'Wealth & Goals', icon: Target },
		{ href: '/imports', label: 'AI Imports', icon: UploadCloud },
		{ href: '/settings', label: 'Settings', icon: Settings }
	];

	$effect(() => {
		if (!auth.loading && !auth.user) {
			goto('/login');
		}
	});

	async function handleLogout() {
		await auth.logout();
		goto('/login');
	}

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

{#if auth.loading}
	<div class="min-h-screen flex items-center justify-center bg-slate-950 text-slate-400 text-sm">
		Loading Financinio...
	</div>
{:else if auth.user}
	<div class="min-h-screen flex bg-slate-950 text-slate-100">
		<!-- Desktop Sidebar -->
		<aside class="hidden md:flex md:w-64 md:flex-col border-r border-slate-800/80 bg-slate-950/90 p-5 justify-between sticky top-0 h-screen">
			<div class="space-y-8">
				<a href="/" class="flex items-center gap-3 px-2">
					<div class="h-9 w-9 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
						<Sparkles class="w-4 h-4" />
					</div>
					<div>
						<div class="font-bold text-white tracking-tight">Financinio</div>
						<div class="text-[11px] text-slate-400">Personal Finance AI</div>
					</div>
				</a>

				<nav class="space-y-1">
					{#each navItems as item}
						{@const Icon = item.icon}
						<a
							href={item.href}
							class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition {isActive(item.href)
								? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/25'
								: 'text-slate-400 hover:text-slate-100 hover:bg-slate-900/70 border border-transparent'}"
						>
							<Icon class="w-4 h-4" />
							{item.label}
						</a>
					{/each}
				</nav>
			</div>

			<div class="pt-4 border-t border-slate-800/80 space-y-3">
				<div class="px-2">
					<div class="text-sm font-medium text-white truncate">{auth.user.full_name}</div>
					<div class="text-xs text-slate-400 truncate">{auth.user.email}</div>
				</div>
				<button
					type="button"
					onclick={handleLogout}
					class="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 transition cursor-pointer"
				>
					<LogOut class="w-4 h-4" />
					Sign Out
				</button>
			</div>
		</aside>

		<!-- Main content -->
		<div class="flex-1 flex flex-col min-w-0">
			<!-- Mobile header -->
			<header class="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-800/80 bg-slate-950/90 sticky top-0 z-30">
				<a href="/" class="flex items-center gap-2.5">
					<div class="h-8 w-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
						<Sparkles class="w-4 h-4" />
					</div>
					<span class="font-bold text-white">Financinio</span>
				</a>
				<button
					type="button"
					onclick={() => (mobileOpen = !mobileOpen)}
					class="p-2 rounded-lg text-slate-300 hover:bg-slate-900"
					aria-label="Toggle Menu"
				>
					{#if mobileOpen}
						<X class="w-5 h-5" />
					{:else}
						<Menu class="w-5 h-5" />
					{/if}
				</button>
			</header>

			{#if mobileOpen}
				<div class="md:hidden border-b border-slate-800 bg-slate-900/95 p-3 space-y-1">
					{#each navItems as item}
						{@const Icon = item.icon}
						<a
							href={item.href}
							onclick={() => (mobileOpen = false)}
							class="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium {isActive(item.href)
								? 'bg-emerald-500/15 text-emerald-300'
								: 'text-slate-300 hover:bg-slate-800'}"
						>
							<Icon class="w-4 h-4" />
							{item.label}
						</a>
					{/each}
					<button
						type="button"
						onclick={handleLogout}
						class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-rose-300 hover:bg-rose-500/10"
					>
						<LogOut class="w-4 h-4" />
						Sign Out
					</button>
				</div>
			{/if}

			<main class="flex-1 p-5 sm:p-8 max-w-7xl w-full mx-auto">
				{@render children()}
			</main>
		</div>
	</div>
{/if}
