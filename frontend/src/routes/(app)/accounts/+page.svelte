<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { Account, Category } from '$lib/api/types';
	import { auth } from '$lib/stores/auth.svelte';
	import { formatMoney } from '$lib/utils/format';
	import AccountFormModal from '$lib/components/accounts/AccountFormModal.svelte';
	import TransferModal from '$lib/components/accounts/TransferModal.svelte';
	import ReconcileModal from '$lib/components/accounts/ReconcileModal.svelte';
	import AccountDetailDrawer from '$lib/components/accounts/AccountDetailDrawer.svelte';
	import {
		Plus,
		Wallet,
		CreditCard,
		Landmark,
		PiggyBank,
		Banknote,
		TrendingUp,
		Trash2,
		Pencil,
		Archive,
		RotateCcw,
		ArrowLeftRight,
		Eye,
		EyeOff,
		Scale,
		ExternalLink,
		X,
		AlertTriangle,
		CheckCircle2
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';

	let allAccounts = $state<Account[]>([]);
	let categoriesMap = $state<Map<string, Category>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);
	let successMsg = $state<string | null>(null);

	let privacyMode = $state(false);
	let filterGroup = $state<'all' | 'banking' | 'debt' | 'investments'>('all');
	let showArchived = $state(false);

	// Modals & Drawer state
	let formModalOpen = $state(false);
	let editingAccount = $state<Account | null>(null);

	let transferModalOpen = $state(false);
	let transferFromId = $state('');

	let reconcileModalOpen = $state(false);
	let reconcileAccount = $state<Account | null>(null);

	let inspectedAccountId = $state<string | null>(null);
	let inspectedAccount = $derived(
		allAccounts.find((a) => a.id === inspectedAccountId) ?? null
	);

	let deleteTarget = $state<Account | null>(null);
	let deleteTxCount = $state<number | null>(null);
	let deleting = $state(false);

	let baseCcy = $derived(auth.user?.base_currency || 'USD');

	async function loadData(silent = false) {
		if (!silent) loading = true;
		error = null;
		try {
			const [accs, cats] = await Promise.all([
				api.listAccounts(true),
				api.listCategories().catch(() => [] as Category[])
			]);
			allAccounts = accs;
			categoriesMap = new Map(cats.map((c) => [c.id, c]));
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load accounts';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadData();
	});

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	let activeAccounts = $derived(allAccounts.filter((a) => !a.is_archived));
	let archivedAccounts = $derived(allAccounts.filter((a) => a.is_archived));

	// Balance Sheet Metrics across active accounts
	let balanceSheet = $derived.by(() => {
		let liquidCash = 0;
		let investedAssets = 0;
		let totalDebt = 0;
		const byCurrency = new Map<string, number>();

		for (const acc of activeAccounts) {
			const bal = Number.parseFloat(acc.current_balance) || 0;
			const ccy = acc.currency.toUpperCase();
			byCurrency.set(ccy, (byCurrency.get(ccy) ?? 0) + bal);

			if (bal < 0) {
				totalDebt += Math.abs(bal);
			} else if (acc.type === 'investment') {
				investedAssets += bal;
			} else {
				liquidCash += bal;
			}
		}

		const netBalance = liquidCash + investedAssets - totalDebt;
		const grossPool = liquidCash + investedAssets + totalDebt;
		const cashPct = grossPool > 0 ? Math.round((liquidCash / grossPool) * 100) : 0;
		const invPct = grossPool > 0 ? Math.round((investedAssets / grossPool) * 100) : 0;
		const debtPct = grossPool > 0 ? Math.max(0, 100 - cashPct - invPct) : 0;

		const currencyTotals = Array.from(byCurrency.entries()).sort((a, b) =>
			a[0] === baseCcy ? -1 : b[0] === baseCcy ? 1 : a[0].localeCompare(b[0])
		);

		return {
			liquidCash,
			investedAssets,
			totalDebt,
			netBalance,
			cashPct,
			invPct,
			debtPct,
			currencyTotals
		};
	});

	function matchesFilter(acc: Account): boolean {
		if (filterGroup === 'all') return true;
		if (filterGroup === 'banking')
			return acc.type === 'checking' || acc.type === 'savings' || acc.type === 'cash';
		if (filterGroup === 'debt') return acc.type === 'credit' || acc.type === 'loan';
		if (filterGroup === 'investments') return acc.type === 'investment';
		return true;
	}

	let groupedSections = $derived.by(() => {
		const filtered = activeAccounts.filter(matchesFilter);
		const groups: Array<{ id: string; title: string; subtitle: string; items: Account[] }> = [
			{
				id: 'banking',
				title: 'Banking & Cash',
				subtitle: 'Checking, savings & cash wallets',
				items: filtered.filter(
					(a) => a.type === 'checking' || a.type === 'savings' || a.type === 'cash'
				)
			},
			{
				id: 'investments',
				title: 'Investments',
				subtitle: 'Brokerage & long-term wealth accounts',
				items: filtered.filter((a) => a.type === 'investment')
			},
			{
				id: 'debt',
				title: 'Credit & Debt',
				subtitle: 'Credit cards & loans',
				items: filtered.filter((a) => a.type === 'credit' || a.type === 'loan')
			}
		];
		return groups.filter((g) => g.items.length > 0);
	});

	function openCreateModal() {
		editingAccount = null;
		formModalOpen = true;
	}

	function openEditModal(acc: Account) {
		editingAccount = acc;
		formModalOpen = true;
	}

	function openTransferModal(fromAccountId = '') {
		transferFromId = fromAccountId;
		transferModalOpen = true;
	}

	function openReconcileModal(acc: Account) {
		reconcileAccount = acc;
		reconcileModalOpen = true;
	}

	async function handleToggleArchive(acc: Account) {
		error = null;
		successMsg = null;
		try {
			const nextState = !acc.is_archived;
			await api.updateAccount(acc.id, { is_archived: nextState });
			await loadData(true);
			successMsg = nextState
				? `Archived "${acc.name}". Historical transactions remain intact.`
				: `Restored "${acc.name}" to your active accounts.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not update archive status';
		}
	}

	async function requestDelete(acc: Account) {
		deleteTarget = acc;
		deleteTxCount = null;
		try {
			const res = await api.listTransactions({ account_id: acc.id, limit: 1 });
			deleteTxCount = res.total;
		} catch {
			deleteTxCount = null;
		}
	}

	async function confirmDelete() {
		if (!deleteTarget || deleting) return;
		const target = deleteTarget;
		deleting = true;
		error = null;
		successMsg = null;
		try {
			await api.deleteAccount(target.id);
			if (inspectedAccountId === target.id) inspectedAccountId = null;
			deleteTarget = null;
			await loadData(true);
			successMsg = `Permanently deleted "${target.name}".`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Failed to delete account';
		} finally {
			deleting = false;
		}
	}
</script>

<div class="space-y-6">
	<!-- TOP HEADER -->
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">Accounts</h1>
			<p class="text-xs sm:text-sm text-slate-400 mt-0.5">
				{activeAccounts.length} active {activeAccounts.length === 1 ? 'account' : 'accounts'}
				{#if archivedAccounts.length > 0}
					· {archivedAccounts.length} archived
				{/if}
				· Click any account to inspect activity or reconcile
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<button
				type="button"
				onclick={togglePrivacy}
				title={privacyMode ? 'Show balances' : 'Hide balances (Privacy Mode)'}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition cursor-pointer {privacyMode
					? 'bg-cyan-500/15 border-cyan-500/35 text-cyan-300'
					: 'bg-slate-900/90 hover:bg-slate-800 border-slate-800 text-slate-300'}"
			>
				{#if privacyMode}
					<EyeOff class="w-3.5 h-3.5" />
					<span class="hidden sm:inline">Hidden</span>
				{:else}
					<Eye class="w-3.5 h-3.5" />
					<span class="hidden sm:inline">Privacy</span>
				{/if}
			</button>

			{#if activeAccounts.length >= 2}
				<button
					type="button"
					onclick={() => openTransferModal()}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 text-cyan-200 text-xs font-semibold transition cursor-pointer"
				>
					<ArrowLeftRight class="w-3.5 h-3.5 text-cyan-400" />
					<span>Transfer</span>
				</button>
			{/if}

			<button
				type="button"
				onclick={openCreateModal}
				class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs transition cursor-pointer shadow-sm"
			>
				<Plus class="w-4 h-4" />
				<span>Add Account</span>
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
			<span>{error}</span>
			<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}
	{#if successMsg}
		<div class="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3">
			<span class="flex items-center gap-2">
				<CheckCircle2 class="w-4 h-4 shrink-0" />
				{successMsg}
			</span>
			<button type="button" onclick={() => (successMsg = null)} class="text-emerald-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	{#if loading}
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each Array(4) as _}
				<div class="card-surface rounded-2xl h-24 animate-pulse"></div>
			{/each}
		</div>
		<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<div class="card-surface rounded-2xl h-44 animate-pulse"></div>
			{/each}
		</div>
	{:else}
		<!-- 1. EXECUTIVE BALANCE SHEET & MULTI-CURRENCY STRIP -->
		{#if activeAccounts.length > 0}
			<div class="space-y-4">
				<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
					<div class="card-surface rounded-2xl p-4 sm:p-5">
						<div class="flex items-center justify-between text-xs text-slate-400 font-medium">
							<span>Liquid Cash</span>
							<Wallet class="w-4 h-4 text-emerald-400" />
						</div>
						<div class="text-2xl font-bold text-white font-mono-num mt-2 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(balanceSheet.liquidCash, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-500 mt-1">Checking, savings & cash</div>
					</div>

					<div class="card-surface rounded-2xl p-4 sm:p-5">
						<div class="flex items-center justify-between text-xs text-slate-400 font-medium">
							<span>Invested Assets</span>
							<TrendingUp class="w-4 h-4 text-cyan-400" />
						</div>
						<div class="text-2xl font-bold text-cyan-300 font-mono-num mt-2 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(balanceSheet.investedAssets, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-500 mt-1">Long-term investments</div>
					</div>

					<div class="card-surface rounded-2xl p-4 sm:p-5">
						<div class="flex items-center justify-between text-xs text-slate-400 font-medium">
							<span>Total Debt</span>
							<CreditCard class="w-4 h-4 text-rose-400" />
						</div>
						<div class="text-2xl font-bold text-rose-400 font-mono-num mt-2 {privacyMode ? 'privacy-blur' : ''}">
							{formatMoney(balanceSheet.totalDebt, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-500 mt-1">Credit cards & loans</div>
					</div>

					<div class="card-surface rounded-2xl p-4 sm:p-5 border-emerald-500/20">
						<div class="flex items-center justify-between text-xs text-slate-400 font-medium">
							<span>Net Balance</span>
							<Landmark class="w-4 h-4 text-emerald-400" />
						</div>
						<div
							class="text-2xl font-bold font-mono-num mt-2 {balanceSheet.netBalance >= 0
								? 'text-emerald-400'
								: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
						>
							{formatMoney(balanceSheet.netBalance, baseCcy)}
						</div>
						<div class="text-[11px] text-slate-500 mt-1">Assets minus liabilities</div>
					</div>
				</div>

				<!-- Native Multi-Currency Totals Bar + Asset Allocation Bar -->
				<div class="card-surface rounded-2xl p-4 sm:p-5 grid lg:grid-cols-12 gap-4 items-center">
					<div class="lg:col-span-7 space-y-2">
						<div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
							Native Balances by Currency
						</div>
						<div class="flex flex-wrap gap-2">
							{#each balanceSheet.currencyTotals as [ccy, total]}
								<div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950/85 border border-slate-800 text-xs">
									<span class="font-mono-num font-bold text-emerald-400">{ccy}</span>
									<span
										class="font-mono-num font-semibold {total < 0 ? 'text-rose-400' : 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
									>
										{formatMoney(total, ccy)}
									</span>
								</div>
							{/each}
						</div>
					</div>

					<div class="lg:col-span-5 space-y-2 lg:border-l lg:border-slate-800/80 lg:pl-5">
						<div class="flex items-center justify-between text-[11px] text-slate-400">
							<span class="font-semibold uppercase tracking-wider">Asset Allocation</span>
							<span class="font-mono-num">
								{balanceSheet.cashPct}% Cash · {balanceSheet.invPct}% Inv · {balanceSheet.debtPct}% Debt
							</span>
						</div>
						<div class="h-2.5 rounded-full bg-slate-900 overflow-hidden flex gap-0.5">
							{#if balanceSheet.cashPct > 0}
								<div
									title="Liquid Cash: {balanceSheet.cashPct}%"
									class="h-full bg-emerald-400 transition-all"
									style="width: {balanceSheet.cashPct}%"
								></div>
							{/if}
							{#if balanceSheet.invPct > 0}
								<div
									title="Invested Assets: {balanceSheet.invPct}%"
									class="h-full bg-cyan-400 transition-all"
									style="width: {balanceSheet.invPct}%"
								></div>
							{/if}
							{#if balanceSheet.debtPct > 0}
								<div
									title="Debt: {balanceSheet.debtPct}%"
									class="h-full bg-rose-400 transition-all"
									style="width: {balanceSheet.debtPct}%"
								></div>
							{/if}
						</div>
					</div>
				</div>
			</div>
		{/if}

		<!-- 2. FILTER PILLS & ARCHIVED TOGGLE -->
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="inline-flex flex-wrap p-1 rounded-xl bg-slate-900/90 border border-slate-800 text-xs gap-0.5">
				{#each [
					['all', `All (${activeAccounts.length})`],
					['banking', 'Banking & Cash'],
					['investments', 'Investments'],
					['debt', 'Credit & Debt']
				] as [val, label]}
					<button
						type="button"
						onclick={() => (filterGroup = val as 'all' | 'banking' | 'debt' | 'investments')}
						class="px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer {filterGroup === val
							? 'bg-emerald-500/20 text-emerald-300'
							: 'text-slate-400 hover:text-white'}"
					>
						{label}
					</button>
				{/each}
			</div>

			{#if archivedAccounts.length > 0}
				<button
					type="button"
					onclick={() => (showArchived = !showArchived)}
					class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-medium transition cursor-pointer {showArchived
						? 'bg-amber-500/15 border-amber-500/35 text-amber-300'
						: 'bg-slate-900/80 border-slate-800 text-slate-400 hover:text-white'}"
				>
					<Archive class="w-3.5 h-3.5" />
					{showArchived ? 'Hide' : 'Show'} Archived ({archivedAccounts.length})
				</button>
			{/if}
		</div>

		<!-- EMPTY STATE -->
		{#if activeAccounts.length === 0 && (!showArchived || archivedAccounts.length === 0)}
			<div class="card-surface rounded-2xl p-12 text-center space-y-3">
				<Wallet class="w-10 h-10 text-emerald-400 mx-auto" />
				<h2 class="text-lg font-semibold text-white">No active accounts yet</h2>
				<p class="text-sm text-slate-400 max-w-md mx-auto">
					Add your Bank of Georgia, TBC, Revolut, Wise, credit card, or cash wallet with one-click presets to track live balances.
				</p>
				<button
					type="button"
					onclick={openCreateModal}
					class="mt-2 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm cursor-pointer"
				>
					<Plus class="w-4 h-4" />
					Create First Account
				</button>
			</div>
		{:else}
			<!-- GROUPED ACCOUNT CARDS -->
			<div class="space-y-6">
				{#each groupedSections as section}
					<div class="space-y-3">
						<div class="flex items-baseline justify-between px-0.5">
							<div>
								<h2 class="text-sm font-semibold text-white">{section.title}</h2>
								<p class="text-[11px] text-slate-500">{section.subtitle}</p>
							</div>
							<span class="text-xs font-mono-num text-slate-500">
								{section.items.length} {section.items.length === 1 ? 'account' : 'accounts'}
							</span>
						</div>

						<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
							{#each section.items as acc}
								{@const bal = Number.parseFloat(acc.current_balance) || 0}
								{@const init = Number.parseFloat(acc.initial_balance) || 0}
								{@const delta = bal - init}
								<div
									role="button"
									tabindex="0"
									onclick={() => (inspectedAccountId = acc.id)}
									onkeydown={(e) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											inspectedAccountId = acc.id;
										}
									}}
									class="card-surface card-surface-hover rounded-2xl p-5 flex flex-col justify-between gap-4 relative overflow-hidden text-left cursor-pointer group outline-none focus:ring-2 focus:ring-emerald-500/50"
								>
									<!-- Brand Color Top Strip -->
									<div
										class="absolute top-0 inset-x-0 h-1"
										style="background-color: {acc.color || '#10b981'}"
									></div>

									<div class="flex items-start justify-between gap-3">
										<div class="flex items-center gap-3 min-w-0">
											<div
												class="h-10 w-10 rounded-xl flex items-center justify-center border border-white/10 shrink-0"
												style="background-color: {acc.color}22; color: {acc.color}"
											>
												{#if acc.type === 'credit'}
													<CreditCard class="w-5 h-5" />
												{:else if acc.type === 'savings'}
													<PiggyBank class="w-5 h-5" />
												{:else if acc.type === 'cash'}
													<Banknote class="w-5 h-5" />
												{:else if acc.type === 'loan' || acc.type === 'investment'}
													<Landmark class="w-5 h-5" />
												{:else}
													<Wallet class="w-5 h-5" />
												{/if}
											</div>
											<div class="min-w-0">
												<div class="font-semibold text-white truncate">{acc.name}</div>
												<div class="text-xs text-slate-400 capitalize truncate">
													{acc.type}{acc.institution ? ` · ${acc.institution}` : ''}
												</div>
											</div>
										</div>
										<span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-[10px] font-mono-num font-semibold text-slate-300 shrink-0">
											{acc.currency}
										</span>
									</div>

									<div class="space-y-1">
										<div class="text-[11px] text-slate-400">Current Balance</div>
										<div
											class="text-2xl font-bold font-mono-num {bal < 0 ? 'text-rose-400' : 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
										>
											{formatMoney(acc.current_balance, acc.currency)}
										</div>
										<div class="text-[11px] font-mono-num flex items-center gap-1.5">
											<span class="text-slate-500">Since opening:</span>
											<span
												class="font-semibold {delta >= 0 ? 'text-emerald-400' : 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
											>
												{delta >= 0 ? '+' : ''}{formatMoney(delta, acc.currency)}
											</span>
										</div>
									</div>

									<!-- Quick-Action Footer Bar -->
									<div class="pt-3 border-t border-slate-800/80 flex items-center justify-between gap-1">
										<div class="flex items-center gap-1">
											<a
												href="/transactions?account={acc.id}"
												onclick={(e) => e.stopPropagation()}
												class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900/90 hover:bg-slate-800 text-[11px] text-slate-300 hover:text-white transition"
												title="View account ledger"
											>
												<ExternalLink class="w-3 h-3" /> Ledger
											</a>
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													openReconcileModal(acc);
												}}
												class="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900/90 hover:bg-slate-800 text-[11px] text-slate-300 hover:text-emerald-300 transition cursor-pointer"
												title="Reconcile balance"
											>
												<Scale class="w-3 h-3" /> Reconcile
											</button>
										</div>

										<div class="flex items-center gap-0.5">
											{#if activeAccounts.length >= 2}
												<button
													type="button"
													onclick={(e) => {
														e.stopPropagation();
														openTransferModal(acc.id);
													}}
													class="p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition cursor-pointer"
													title="Transfer from this account"
												>
													<ArrowLeftRight class="w-3.5 h-3.5" />
												</button>
											{/if}
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													openEditModal(acc);
												}}
												class="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
												title="Edit account"
											>
												<Pencil class="w-3.5 h-3.5" />
											</button>
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													handleToggleArchive(acc);
												}}
												class="p-1.5 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-amber-500/10 transition cursor-pointer"
												title="Archive account"
											>
												<Archive class="w-3.5 h-3.5" />
											</button>
											<button
												type="button"
												onclick={(e) => {
													e.stopPropagation();
													requestDelete(acc);
												}}
												class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer"
												title="Delete account"
											>
												<Trash2 class="w-3.5 h-3.5" />
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}

				{#if groupedSections.length === 0 && activeAccounts.length > 0}
					<div class="card-surface rounded-2xl p-8 text-center text-xs text-slate-400">
						No active accounts match the selected filter.
					</div>
				{/if}

				<!-- ARCHIVED ACCOUNTS SECTION -->
				{#if showArchived && archivedAccounts.length > 0}
					<div class="space-y-3 pt-2 border-t border-slate-800/80">
						<div class="flex items-baseline justify-between px-0.5">
							<div>
								<h2 class="text-sm font-semibold text-amber-300">Archived Accounts</h2>
								<p class="text-[11px] text-slate-500">Excluded from active balance totals; historical records preserved</p>
							</div>
						</div>
						<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
							{#each archivedAccounts as acc}
								<div
									role="button"
									tabindex="0"
									onclick={() => (inspectedAccountId = acc.id)}
									onkeydown={(e) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											inspectedAccountId = acc.id;
										}
									}}
									class="card-surface rounded-2xl p-5 opacity-75 hover:opacity-100 transition flex flex-col justify-between gap-4 cursor-pointer border-amber-500/20"
								>
									<div class="flex items-start justify-between gap-2">
										<div class="min-w-0">
											<div class="font-semibold text-slate-200 truncate">{acc.name}</div>
											<div class="text-xs text-slate-500 capitalize">
												{acc.type}{acc.institution ? ` · ${acc.institution}` : ''}
											</div>
										</div>
										<span class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[10px] font-semibold uppercase">
											Archived
										</span>
									</div>
									<div class="text-xl font-bold font-mono-num text-slate-300 {privacyMode ? 'privacy-blur' : ''}">
										{formatMoney(acc.current_balance, acc.currency)}
									</div>
									<div class="flex items-center justify-between pt-2 border-t border-slate-800/80">
										<button
											type="button"
											onclick={(e) => {
												e.stopPropagation();
												handleToggleArchive(acc);
											}}
											class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-xs font-semibold cursor-pointer"
										>
											<RotateCcw class="w-3.5 h-3.5" /> Restore
										</button>
										<button
											type="button"
											onclick={(e) => {
												e.stopPropagation();
												requestDelete(acc);
											}}
											class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-rose-400 hover:bg-rose-500/10 text-xs cursor-pointer"
										>
											<Trash2 class="w-3.5 h-3.5" /> Delete
										</button>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<!-- Create / Edit Account Modal -->
<AccountFormModal
	bind:open={formModalOpen}
	{editingAccount}
	onSaved={() => loadData(true)}
/>

<!-- Internal Transfer Modal -->
<TransferModal
	bind:open={transferModalOpen}
	accounts={allAccounts}
	initialFromId={transferFromId}
	onTransferred={async () => {
		await loadData(true);
		successMsg = 'Internal transfer recorded and both account balances updated.';
	}}
/>

<!-- Balance Reconciliation Modal -->
<ReconcileModal
	bind:open={reconcileModalOpen}
	account={reconcileAccount}
	onReconciled={async () => {
		await loadData(true);
		successMsg = `Balance reconciled for "${reconcileAccount?.name || 'account'}".`;
	}}
/>

<!-- Account Detail Slide-Over Drawer -->
<AccountDetailDrawer
	account={inspectedAccount}
	{categoriesMap}
	{privacyMode}
	onClose={() => (inspectedAccountId = null)}
	onEdit={(acc) => openEditModal(acc)}
	onTransfer={(acc) => openTransferModal(acc.id)}
	onReconcile={(acc) => openReconcileModal(acc)}
	onToggleArchive={(acc) => handleToggleArchive(acc)}
	onRequestDelete={(acc) => requestDelete(acc)}
/>

<!-- Safe Delete Confirmation Modal -->
{#if deleteTarget}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-rose-500/35">
			<div class="flex items-start justify-between gap-3">
				<div class="flex items-center gap-2.5">
					<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
						<AlertTriangle class="w-5 h-5" />
					</div>
					<div>
						<h2 class="text-base font-semibold text-white">Delete "{deleteTarget.name}"?</h2>
						<p class="text-xs text-slate-400">
							{deleteTarget.currency} · Balance {formatMoney(deleteTarget.current_balance, deleteTarget.currency)}
						</p>
					</div>
				</div>
				<button
					type="button"
					disabled={deleting}
					onclick={() => (deleteTarget = null)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<div class="p-3.5 rounded-xl bg-rose-500/8 border border-rose-500/25 text-xs text-rose-200 leading-relaxed space-y-1.5">
				<p>
					This action is permanent and will delete
					<strong>
						{deleteTxCount === null
							? 'all transactions'
							: `${deleteTxCount} ${deleteTxCount === 1 ? 'transaction' : 'transactions'}`}
					</strong>
					and import batches linked to this account.
				</p>
				{#if !deleteTarget.is_archived}
					<p class="text-slate-300">
						Want to keep your historical charts intact? Choose <strong>Archive Instead</strong> to hide it safely.
					</p>
				{/if}
			</div>

			<div class="flex flex-wrap items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={deleting}
					onclick={() => (deleteTarget = null)}
					class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
				{#if !deleteTarget.is_archived}
					<button
						type="button"
						disabled={deleting}
						onclick={async () => {
							const t = deleteTarget;
							deleteTarget = null;
							if (t) await handleToggleArchive(t);
						}}
						class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/35 text-amber-200 text-xs font-semibold cursor-pointer"
					>
						<Archive class="w-3.5 h-3.5" /> Archive Instead
					</button>
				{/if}
				<button
					type="button"
					disabled={deleting}
					onclick={confirmDelete}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
				>
					<Trash2 class="w-3.5 h-3.5" />
					{deleting ? 'Deleting...' : 'Delete Permanently'}
				</button>
			</div>
		</div>
	</div>
{/if}
