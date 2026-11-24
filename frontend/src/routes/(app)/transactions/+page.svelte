<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import type { Account, Category, Transaction } from '$lib/api/types';
	import { formatDate, formatMoney } from '$lib/utils/format';
	import TransactionDetailDrawer from '$lib/components/transactions/TransactionDetailDrawer.svelte';
	import {
		Plus,
		Search,
		Trash2,
		X,
		Sparkles,
		ArrowLeftRight,
		ArrowUpRight,
		ArrowDownRight,
		Download,
		Eye,
		EyeOff,
		Calendar,
		RotateCcw,
		LayoutList,
		Table2,
		ChevronLeft,
		ChevronRight,
		CheckCircle2,
		AlertTriangle,
		Tag,
		Brain
	} from 'lucide-svelte';

	const PRIVACY_KEY = 'financinio_privacy_mode';
	const PAGE_SIZE = 50;

	type DatePreset = 'all' | 'this_month' | 'last_30d' | 'last_month' | 'last_90d' | 'custom';

	let transactions = $state<Transaction[]>([]);
	let total = $state(0);
	let offset = $state(0);
	let accounts = $state<Account[]>([]);
	let categories = $state<Category[]>([]);
	let loading = $state(true);
	let exporting = $state(false);
	let error = $state<string | null>(null);
	let toastMsg = $state<string | null>(null);
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	// Display & Privacy
	let privacyMode = $state(false);
	let viewMode = $state<'grouped' | 'table'>('grouped');

	// Server + Client Filters
	let search = $state('');
	let searchDebounce: ReturnType<typeof setTimeout> | null = null;
	let filterAccount = $state('');
	let filterCategory = $state('');
	let filterDirection = $state('');
	let datePreset = $state<DatePreset>('all');
	let dateFrom = $state('');
	let dateTo = $state('');
	let onlyUncategorized = $state(false);
	let onlyImported = $state(false);
	let hideTransfers = $state(false);

	// Selection & Bulk Actions
	let selectedIds = $state<Set<string>>(new Set());
	let bulkCategoryId = $state('');
	let bulkBusy = $state(false);

	// Inspector Drawer & Modals
	let inspectedTx = $state<Transaction | null>(null);
	let deleteConfirmIds = $state<string[]>([]);
	let deleteConfirmLabel = $state('');
	let deleting = $state(false);

	// Quick-add modal
	let showAddModal = $state(false);
	let formAccountId = $state('');
	let formCategoryId = $state('');
	let formDirection = $state<'outflow' | 'inflow'>('outflow');
	let formAmount = $state('');
	let formDate = $state(new Date().toISOString().slice(0, 10));
	let formMerchant = $state('');
	let formNotes = $state('');
	let formTagsRaw = $state('');
	let formIsTransfer = $state(false);
	let formTransferAccountId = $state('');
	let saving = $state(false);

	let accountsMap = $derived(new Map(accounts.map((a) => [a.id, a])));
	let categoriesMap = $derived(new Map(categories.map((c) => [c.id, c])));
	let baseCcy = $derived(auth.user?.base_currency || 'USD');

	function showToast(msg: string) {
		toastMsg = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => {
			toastMsg = null;
		}, 3200);
	}

	function isoDate(d: Date): string {
		const y = d.getFullYear();
		const m = String(d.getMonth() + 1).padStart(2, '0');
		const day = String(d.getDate()).padStart(2, '0');
		return `${y}-${m}-${day}`;
	}

	function applyDatePreset(preset: DatePreset) {
		datePreset = preset;
		const now = new Date();
		if (preset === 'all') {
			dateFrom = '';
			dateTo = '';
		} else if (preset === 'this_month') {
			dateFrom = isoDate(new Date(now.getFullYear(), now.getMonth(), 1));
			dateTo = isoDate(now);
		} else if (preset === 'last_30d') {
			const start = new Date(now);
			start.setDate(start.getDate() - 30);
			dateFrom = isoDate(start);
			dateTo = isoDate(now);
		} else if (preset === 'last_month') {
			const firstPrev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
			const lastPrev = new Date(now.getFullYear(), now.getMonth(), 0);
			dateFrom = isoDate(firstPrev);
			dateTo = isoDate(lastPrev);
		} else if (preset === 'last_90d') {
			const start = new Date(now);
			start.setDate(start.getDate() - 90);
			dateFrom = isoDate(start);
			dateTo = isoDate(now);
		}
		if (preset !== 'custom') {
			offset = 0;
			loadFiltered();
		}
	}

	async function loadAll() {
		loading = true;
		error = null;
		const paramAccId = page.url.searchParams.get('account');
		if (paramAccId && !filterAccount) {
			filterAccount = paramAccId;
		}
		try {
			const [accs, cats, txRes] = await Promise.all([
				api.listAccounts(),
				api.listCategories(),
				api.listTransactions({
					search: search.trim() || undefined,
					account_id: filterAccount || undefined,
					category_id: filterCategory || undefined,
					direction: filterDirection || undefined,
					date_from: dateFrom || undefined,
					date_to: dateTo || undefined,
					limit: PAGE_SIZE,
					offset
				})
			]);
			accounts = accs;
			categories = cats;
			transactions = txRes.items;
			total = txRes.total;
			if (!formAccountId && accs.length > 0) formAccountId = accs[0].id;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Failed to load transactions';
		} finally {
			loading = false;
		}
	}

	async function loadFiltered(resetOffset = false) {
		if (resetOffset) offset = 0;
		selectedIds = new Set();
		try {
			const txRes = await api.listTransactions({
				search: search.trim() || undefined,
				account_id: filterAccount || undefined,
				category_id: filterCategory || undefined,
				direction: filterDirection || undefined,
				date_from: dateFrom || undefined,
				date_to: dateTo || undefined,
				limit: PAGE_SIZE,
				offset
			});
			transactions = txRes.items;
			total = txRes.total;
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'Filter failed';
		}
	}

	function handleSearchInput() {
		if (searchDebounce) clearTimeout(searchDebounce);
		searchDebounce = setTimeout(() => {
			loadFiltered(true);
		}, 280);
	}

	function resetAllFilters() {
		search = '';
		filterAccount = '';
		filterCategory = '';
		filterDirection = '';
		datePreset = 'all';
		dateFrom = '';
		dateTo = '';
		onlyUncategorized = false;
		onlyImported = false;
		hideTransfers = false;
		offset = 0;
		loadFiltered(true);
	}

	onMount(() => {
		if (typeof window !== 'undefined') {
			privacyMode = localStorage.getItem(PRIVACY_KEY) === '1';
		}
		loadAll();
	});

	function togglePrivacy() {
		privacyMode = !privacyMode;
		if (typeof window !== 'undefined') {
			localStorage.setItem(PRIVACY_KEY, privacyMode ? '1' : '0');
		}
	}

	// Client-side smart filter refinement (Uncategorized / AI Imported / Hide Transfers)
	let uncategorizedCount = $derived(
		transactions.filter((t) => {
			if (!t.category_id) return true;
			const cat = categoriesMap.get(t.category_id);
			return cat?.name.toLowerCase() === 'uncategorized';
		}).length
	);

	let visibleTransactions = $derived.by(() => {
		return transactions.filter((t) => {
			if (onlyUncategorized) {
				const cat = t.category_id ? categoriesMap.get(t.category_id) : null;
				const isUncat = !t.category_id || cat?.name.toLowerCase() === 'uncategorized';
				if (!isUncat) return false;
			}
			if (onlyImported && !t.source_document_id) return false;
			if (hideTransfers && t.is_transfer) return false;
			return true;
		});
	});

	let hasActiveFilters = $derived(
		Boolean(
			search.trim() ||
				filterAccount ||
				filterCategory ||
				filterDirection ||
				dateFrom ||
				dateTo ||
				onlyUncategorized ||
				onlyImported ||
				hideTransfers
		)
	);

	// Live Filtered Summary Strip metrics
	let summaryStats = $derived.by(() => {
		let inflow = 0;
		let outflow = 0;
		let nonTransferCount = 0;
		let absTotal = 0;
		const ccys = new Set<string>();

		for (const tx of visibleTransactions) {
			ccys.add(tx.currency);
			if (tx.is_transfer) continue;
			const amt = Number.parseFloat(tx.amount) || 0;
			nonTransferCount += 1;
			absTotal += amt;
			if (tx.direction === 'inflow') inflow += amt;
			else outflow += amt;
		}
		const displayCcy = ccys.size === 1 ? Array.from(ccys)[0] : baseCcy;
		return {
			count: visibleTransactions.length,
			inflow,
			outflow,
			net: inflow - outflow,
			avg: nonTransferCount > 0 ? absTotal / nonTransferCount : 0,
			displayCcy
		};
	});

	// Date-Grouped Ledger sections with friendly labels & daily net subtotal
	function friendlyDateHeading(iso: string): string {
		const today = isoDate(new Date());
		const yest = new Date();
		yest.setDate(yest.getDate() - 1);
		const yesterday = isoDate(yest);
		if (iso === today) return `Today · ${formatDate(iso)}`;
		if (iso === yesterday) return `Yesterday · ${formatDate(iso)}`;
		return formatDate(iso);
	}

	let groupedByDate = $derived.by(() => {
		const map = new Map<string, { date: string; label: string; net: number; currency: string; items: Transaction[] }>();
		for (const tx of visibleTransactions) {
			const key = tx.occurred_at.slice(0, 10);
			let group = map.get(key);
			if (!group) {
				group = {
					date: key,
					label: friendlyDateHeading(key),
					net: 0,
					currency: tx.currency,
					items: []
				};
				map.set(key, group);
			}
			group.items.push(tx);
			if (!tx.is_transfer) {
				const amt = Number.parseFloat(tx.amount) || 0;
				group.net += tx.direction === 'inflow' ? amt : -amt;
			}
		}
		return Array.from(map.values());
	});

	// Multi-select helpers
	let allVisibleSelected = $derived(
		visibleTransactions.length > 0 && visibleTransactions.every((t) => selectedIds.has(t.id))
	);

	let selectedSummary = $derived.by(() => {
		let net = 0;
		let ccy = baseCcy;
		const ccys = new Set<string>();
		for (const tx of visibleTransactions) {
			if (!selectedIds.has(tx.id)) continue;
			ccys.add(tx.currency);
			const amt = Number.parseFloat(tx.amount) || 0;
			net += tx.direction === 'inflow' ? amt : -amt;
		}
		if (ccys.size === 1) ccy = Array.from(ccys)[0];
		return { count: selectedIds.size, net, ccy };
	});

	function toggleSelect(id: string) {
		const next = new Set(selectedIds);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selectedIds = next;
	}

	function toggleSelectAll() {
		if (allVisibleSelected) {
			selectedIds = new Set();
		} else {
			selectedIds = new Set(visibleTransactions.map((t) => t.id));
		}
	}

	async function handleBulkCategorize() {
		if (selectedIds.size === 0 || !bulkCategoryId || bulkBusy) return;
		bulkBusy = true;
		error = null;
		try {
			const ids = Array.from(selectedIds);
			const res = await api.bulkCategorizeTransactions(
				ids,
				bulkCategoryId === '__none__' ? null : bulkCategoryId,
				true
			);
			selectedIds = new Set();
			bulkCategoryId = '';
			await loadFiltered();
			showToast(`Categorized ${res.updated} transactions & trained Upstash Vector memory!`);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Bulk categorization failed';
		} finally {
			bulkBusy = false;
		}
	}

	function requestDeleteSingle(tx: Transaction) {
		deleteConfirmIds = [tx.id];
		deleteConfirmLabel = `"${tx.merchant_clean}" (${formatMoney(tx.amount, tx.currency)})`;
	}

	function requestDeleteBulk() {
		if (selectedIds.size === 0) return;
		deleteConfirmIds = Array.from(selectedIds);
		deleteConfirmLabel = `${deleteConfirmIds.length} selected transactions`;
	}

	async function confirmDelete() {
		if (deleteConfirmIds.length === 0 || deleting) return;
		deleting = true;
		error = null;
		try {
			const ids = [...deleteConfirmIds];
			for (const id of ids) {
				await api.deleteTransaction(id);
			}
			if (inspectedTx && ids.includes(inspectedTx.id)) {
				inspectedTx = null;
			}
			deleteConfirmIds = [];
			selectedIds = new Set();
			await loadFiltered();
			showToast(
				ids.length === 1
					? 'Transaction deleted & account balance recalculated.'
					: `Deleted ${ids.length} transactions & recalculated balances.`
			);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Delete failed';
		} finally {
			deleting = false;
		}
	}

	async function handleInlineCategoryChange(tx: Transaction, newCategoryId: string) {
		try {
			const updated = await api.updateTransaction(tx.id, {
				category_id: newCategoryId || null
			});
			transactions = transactions.map((t) => (t.id === tx.id ? updated : t));
			if (inspectedTx?.id === tx.id) inspectedTx = updated;
			if (newCategoryId) {
				showToast(`Category updated & learned for "${tx.merchant_clean}" in Upstash Vector.`);
			}
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Category update failed';
		}
	}

	async function handleCreate(e: SubmitEvent) {
		e.preventDefault();
		if (!formAccountId) {
			error = 'Please create an account first.';
			return;
		}
		saving = true;
		error = null;
		try {
			const tags = formTagsRaw
				.split(',')
				.map((t) => t.trim().toLowerCase().replace(/\s+/g, '-'))
				.filter(Boolean);
			await api.createTransaction({
				account_id: formAccountId,
				category_id: formCategoryId || null,
				amount: formAmount,
				direction: formDirection,
				occurred_at: formDate,
				merchant: formMerchant.trim(),
				notes: formNotes.trim() || undefined,
				tags: tags.length > 0 ? tags : undefined,
				is_transfer: formIsTransfer,
				transfer_account_id: formIsTransfer && formTransferAccountId ? formTransferAccountId : null
			});
			showAddModal = false;
			formAmount = '';
			formMerchant = '';
			formNotes = '';
			formTagsRaw = '';
			formIsTransfer = false;
			formTransferAccountId = '';
			await loadFiltered(true);
			showToast('Transaction added to ledger.');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Could not save transaction';
		} finally {
			saving = false;
		}
	}

	async function handleExportCsv() {
		exporting = true;
		error = null;
		try {
			const blob = await api.downloadTransactionsCsv();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `financinio-transactions-${isoDate(new Date())}.csv`;
			a.click();
			URL.revokeObjectURL(url);
			showToast('Exported full ledger to CSV.');
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'CSV export failed';
		} finally {
			exporting = false;
		}
	}

	let pageStart = $derived(total === 0 ? 0 : offset + 1);
	let pageEnd = $derived(Math.min(total, offset + transactions.length));
	let hasPrev = $derived(offset > 0);
	let hasNext = $derived(offset + PAGE_SIZE < total);

	function goPrevPage() {
		if (!hasPrev) return;
		offset = Math.max(0, offset - PAGE_SIZE);
		loadFiltered();
	}

	function goNextPage() {
		if (!hasNext) return;
		offset += PAGE_SIZE;
		loadFiltered();
	}
</script>

<div class="space-y-5 pb-20">
	<!-- TOP HEADER -->
	<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
		<div>
			<h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-white">Transactions</h1>
			<p class="text-xs sm:text-sm text-slate-400 mt-0.5">
				{total} ledger {total === 1 ? 'entry' : 'entries'} · Click any row to inspect, edit tags, or create an auto-rule
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<button
				type="button"
				onclick={togglePrivacy}
				title={privacyMode ? 'Show amounts' : 'Hide amounts (Privacy Mode)'}
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

			<button
				type="button"
				disabled={exporting}
				onclick={handleExportCsv}
				class="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition cursor-pointer disabled:opacity-50"
			>
				<Download class="w-3.5 h-3.5 text-emerald-400" />
				<span>{exporting ? 'Exporting...' : 'Export CSV'}</span>
			</button>

			<button
				type="button"
				onclick={() => (showAddModal = true)}
				class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs transition cursor-pointer shadow-sm"
			>
				<Plus class="w-4 h-4" />
				<span>Quick Add</span>
			</button>
		</div>
	</div>

	<!-- Floating Toast Notification -->
	{#if toastMsg}
		<div class="p-3 rounded-xl bg-emerald-500/12 border border-emerald-500/35 text-emerald-200 text-xs flex items-center justify-between gap-3">
			<span class="flex items-center gap-2">
				<Brain class="w-4 h-4 text-emerald-400 shrink-0" />
				{toastMsg}
			</span>
			<button type="button" onclick={() => (toastMsg = null)} class="text-emerald-300 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	{#if error}
		<div class="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-3">
			<span>{error}</span>
			<button type="button" onclick={() => (error = null)} class="text-rose-200 hover:text-white cursor-pointer">✕</button>
		</div>
	{/if}

	<!-- 1. LIVE FILTERED SUMMARY STRIP -->
	<div class="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
		<div class="card-surface rounded-2xl p-4">
			<div class="text-[11px] font-medium text-slate-400">Matching Entries</div>
			<div class="text-xl sm:text-2xl font-bold text-white font-mono-num mt-1">
				{summaryStats.count}
				<span class="text-xs font-normal text-slate-500">/ {total}</span>
			</div>
			<div class="text-[10px] text-slate-500 mt-1">
				Avg ticket:
				<span class="font-mono-num text-slate-300 {privacyMode ? 'privacy-blur' : ''}">
					{formatMoney(summaryStats.avg, summaryStats.displayCcy)}
				</span>
			</div>
		</div>

		<div class="card-surface rounded-2xl p-4">
			<div class="text-[11px] font-medium text-slate-400 flex items-center justify-between">
				<span>Total Inflow</span>
				<ArrowDownRight class="w-3.5 h-3.5 text-emerald-400" />
			</div>
			<div class="text-xl sm:text-2xl font-bold text-emerald-400 font-mono-num mt-1 {privacyMode ? 'privacy-blur' : ''}">
				+{formatMoney(summaryStats.inflow, summaryStats.displayCcy)}
			</div>
			<div class="text-[10px] text-slate-500 mt-1">Excludes internal transfers</div>
		</div>

		<div class="card-surface rounded-2xl p-4">
			<div class="text-[11px] font-medium text-slate-400 flex items-center justify-between">
				<span>Total Outflow</span>
				<ArrowUpRight class="w-3.5 h-3.5 text-rose-400" />
			</div>
			<div class="text-xl sm:text-2xl font-bold text-rose-400 font-mono-num mt-1 {privacyMode ? 'privacy-blur' : ''}">
				-{formatMoney(summaryStats.outflow, summaryStats.displayCcy)}
			</div>
			<div class="text-[10px] text-slate-500 mt-1">Excludes internal transfers</div>
		</div>

		<div class="card-surface rounded-2xl p-4 border-emerald-500/15">
			<div class="text-[11px] font-medium text-slate-400">Net Cash Flow</div>
			<div
				class="text-xl sm:text-2xl font-bold font-mono-num mt-1 {summaryStats.net >= 0
					? 'text-cyan-300'
					: 'text-rose-400'} {privacyMode ? 'privacy-blur' : ''}"
			>
				{summaryStats.net >= 0 ? '+' : ''}{formatMoney(summaryStats.net, summaryStats.displayCcy)}
			</div>
			<div class="text-[10px] text-slate-500 mt-1">Current filtered view</div>
		</div>
	</div>

	<!-- 2. POWER FILTER BAR & DATE PRESETS -->
	<div class="card-surface rounded-2xl p-4 space-y-3.5">
		<!-- Date Range Presets + View Switch -->
		<div class="flex flex-wrap items-center justify-between gap-2.5">
			<div class="flex flex-wrap items-center gap-1.5">
				<Calendar class="w-3.5 h-3.5 text-slate-400 mr-0.5 hidden sm:inline" />
				{#each [
					['all', 'All Time'],
					['this_month', 'This Month'],
					['last_30d', 'Last 30d'],
					['last_month', 'Last Month'],
					['last_90d', 'Last 90d'],
					['custom', 'Custom']
				] as [preset, label]}
					<button
						type="button"
						onclick={() => applyDatePreset(preset as DatePreset)}
						class="px-2.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer {datePreset === preset
							? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
							: 'bg-slate-950/70 text-slate-400 hover:text-white border border-slate-800'}"
					>
						{label}
					</button>
				{/each}
			</div>

			<div class="inline-flex p-0.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
				<button
					type="button"
					onclick={() => (viewMode = 'grouped')}
					class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition cursor-pointer {viewMode === 'grouped'
						? 'bg-slate-800 text-white'
						: 'text-slate-400 hover:text-white'}"
				>
					<LayoutList class="w-3.5 h-3.5" /> Grouped
				</button>
				<button
					type="button"
					onclick={() => (viewMode = 'table')}
					class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition cursor-pointer {viewMode === 'table'
						? 'bg-slate-800 text-white'
						: 'text-slate-400 hover:text-white'}"
				>
					<Table2 class="w-3.5 h-3.5" /> Table
				</button>
			</div>
		</div>

		{#if datePreset === 'custom'}
			<div class="flex flex-wrap items-center gap-2.5 pt-1">
				<div class="flex items-center gap-2 text-xs">
					<label for="df" class="text-slate-400">From:</label>
					<input
						id="df"
						type="date"
						bind:value={dateFrom}
						onchange={() => loadFiltered(true)}
						class="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>
				<div class="flex items-center gap-2 text-xs">
					<label for="dt" class="text-slate-400">To:</label>
					<input
						id="dt"
						type="date"
						bind:value={dateTo}
						onchange={() => loadFiltered(true)}
						class="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>
			</div>
		{/if}

		<!-- Search & Dropdowns -->
		<div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
			<div class="relative">
				<Search class="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
				<input
					type="text"
					bind:value={search}
					oninput={handleSearchInput}
					placeholder="Search merchant, memo, notes..."
					class="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
				/>
			</div>
			<select
				bind:value={filterAccount}
				onchange={() => loadFiltered(true)}
				class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
			>
				<option value="">All Accounts</option>
				{#each accounts as acc}
					<option value={acc.id}>{acc.name} ({acc.currency})</option>
				{/each}
			</select>
			<select
				bind:value={filterCategory}
				onchange={() => loadFiltered(true)}
				class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
			>
				<option value="">All Categories</option>
				{#each categories as cat}
					<option value={cat.id}>{cat.name}</option>
				{/each}
			</select>
			<select
				bind:value={filterDirection}
				onchange={() => loadFiltered(true)}
				class="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
			>
				<option value="">All Directions</option>
				<option value="outflow">Expenses (Outflow)</option>
				<option value="inflow">Income (Inflow)</option>
			</select>
		</div>

		<!-- Smart Chips & Reset -->
		<div class="flex flex-wrap items-center justify-between gap-2 pt-0.5">
			<div class="flex flex-wrap items-center gap-2">
				<button
					type="button"
					onclick={() => (onlyUncategorized = !onlyUncategorized)}
					class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold transition cursor-pointer {onlyUncategorized
						? 'bg-amber-500/20 border-amber-500/40 text-amber-200'
						: 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white'}"
				>
					Uncategorized
					{#if uncategorizedCount > 0}
						<span class="px-1.5 py-0.2 rounded-full bg-amber-500/25 text-amber-300 font-mono-num text-[10px]">
							{uncategorizedCount}
						</span>
					{/if}
				</button>

				<button
					type="button"
					onclick={() => (onlyImported = !onlyImported)}
					class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold transition cursor-pointer {onlyImported
						? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-200'
						: 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white'}"
				>
					<Sparkles class="w-3 h-3" /> AI Imported
				</button>

				<button
					type="button"
					onclick={() => (hideTransfers = !hideTransfers)}
					class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-semibold transition cursor-pointer {hideTransfers
						? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-200'
						: 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white'}"
				>
					<ArrowLeftRight class="w-3 h-3" /> Hide Transfers
				</button>
			</div>

			<div class="flex items-center gap-3">
				{#if visibleTransactions.length > 0}
					<label class="inline-flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer">
						<input
							type="checkbox"
							checked={allVisibleSelected}
							onchange={toggleSelectAll}
							class="rounded border-slate-700"
						/>
						Select all ({visibleTransactions.length})
					</label>
				{/if}

				{#if hasActiveFilters}
					<button
						type="button"
						onclick={resetAllFilters}
						class="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-300 hover:text-rose-200 cursor-pointer"
					>
						<RotateCcw class="w-3 h-3" /> Reset Filters
					</button>
				{/if}
			</div>
		</div>
	</div>

	<!-- 3. LEDGER VIEW (DATE-GROUPED OR COMPACT TABLE) -->
	{#if loading}
		<div class="space-y-3">
			{#each Array(5) as _}
				<div class="card-surface rounded-2xl h-16 animate-pulse"></div>
			{/each}
		</div>
	{:else if visibleTransactions.length === 0}
		<div class="card-surface rounded-2xl p-12 text-center space-y-3">
			<p class="text-sm text-slate-400">No transactions match your current filters.</p>
			<div class="flex items-center justify-center gap-3">
				{#if hasActiveFilters}
					<button
						type="button"
						onclick={resetAllFilters}
						class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white cursor-pointer"
					>
						Reset Filters
					</button>
				{/if}
				<a href="/imports" class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-slate-950">
					Import Bank Statement →
				</a>
			</div>
		</div>
	{:else if viewMode === 'grouped'}
		<!-- DATE-GROUPED LEDGER VIEW (Desktop & Mobile Native) -->
		<div class="space-y-4">
			{#each groupedByDate as group}
				<div class="card-surface rounded-2xl overflow-hidden">
					<!-- Date Header with Daily Net Subtotal -->
					<div class="px-4 py-2.5 bg-slate-900/75 border-b border-slate-800/80 flex items-center justify-between gap-2 text-xs">
						<span class="font-semibold text-slate-200">{group.label}</span>
						<span class="font-mono-num text-[11px] text-slate-400">
							Daily net:
							<span
								class="font-semibold {group.net >= 0 ? 'text-emerald-400' : 'text-slate-200'} {privacyMode ? 'privacy-blur' : ''}"
							>
								{group.net >= 0 ? '+' : ''}{formatMoney(group.net, group.currency)}
							</span>
						</span>
					</div>

					<div class="divide-y divide-slate-800/60">
						{#each group.items as tx}
							{@const acc = accountsMap.get(tx.account_id)}
							{@const isSelected = selectedIds.has(tx.id)}
							<div
								role="button"
								tabindex="0"
								onclick={() => (inspectedTx = tx)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										inspectedTx = tx;
									}
								}}
								class="px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition cursor-pointer outline-none {isSelected
									? 'bg-emerald-500/8'
									: 'hover:bg-slate-900/55'}"
							>
								<div class="flex items-start sm:items-center gap-3 min-w-0 flex-1">
									<!-- Multi-select Checkbox -->
									<input
										type="checkbox"
										checked={isSelected}
										onclick={(e) => e.stopPropagation()}
										onchange={() => toggleSelect(tx.id)}
										aria-label="Select {tx.merchant_clean}"
										class="mt-1 sm:mt-0 rounded border-slate-700 cursor-pointer shrink-0"
									/>

									<!-- Direction Icon -->
									<div
										class="h-9 w-9 rounded-xl flex items-center justify-center shrink-0 {tx.is_transfer
											? 'bg-slate-800/90 text-cyan-300'
											: tx.direction === 'inflow'
												? 'bg-emerald-500/15 text-emerald-400'
												: 'bg-slate-800 text-slate-300'}"
									>
										{#if tx.is_transfer}
											<ArrowLeftRight class="w-4 h-4" />
										{:else if tx.direction === 'inflow'}
											<ArrowDownRight class="w-4 h-4" />
										{:else}
											<ArrowUpRight class="w-4 h-4" />
										{/if}
									</div>

									<!-- Merchant & Rich Metadata -->
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-1.5 flex-wrap">
											<span class="text-sm font-semibold text-white truncate max-w-[260px] sm:max-w-md">
												{tx.merchant_clean}
											</span>
											{#if tx.is_transfer}
												<span class="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300 text-[10px] font-semibold">
													Transfer
												</span>
											{/if}
											{#if tx.tags?.includes('bank-of-georgia')}
												<span class="px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-300 text-[10px] font-semibold">
													BOG
												</span>
											{:else if tx.source_document_id}
												<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 text-[10px]">
													<Sparkles class="w-2.5 h-2.5" /> Import
												</span>
											{/if}
										</div>

										<div class="flex items-center gap-1.5 flex-wrap mt-1 text-[11px] text-slate-400">
											{#if acc}
												<span class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[10px]">
													{acc.name}
												</span>
											{/if}
											{#if tx.notes}
												<span class="truncate max-w-[200px] text-slate-400">· {tx.notes}</span>
											{/if}
											{#each (tx.tags || []).filter((t) => t !== 'imported' && t !== 'bank-of-georgia').slice(0, 3) as tag}
												<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-[10px] text-cyan-300">
													<Tag class="w-2.5 h-2.5" />{tag}
												</span>
											{/each}
										</div>
									</div>
								</div>

								<!-- Right side: Inline Category + Amount + Delete -->
								<div class="flex items-center justify-between sm:justify-end gap-3 pl-7 sm:pl-0 shrink-0">
									<select
										value={tx.category_id ?? ''}
										onclick={(e) => e.stopPropagation()}
										onchange={(e) =>
											handleInlineCategoryChange(tx, (e.currentTarget as HTMLSelectElement).value)}
										aria-label="Category for {tx.merchant_clean}"
										class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 max-w-[165px] cursor-pointer"
									>
										<option value="">Uncategorized</option>
										{#each categories as cat}
											<option value={cat.id}>{cat.name}</option>
										{/each}
									</select>

									<div
										class="text-sm font-bold font-mono-num min-w-[92px] text-right {tx.direction === 'inflow'
											? 'text-emerald-400'
											: 'text-white'} {privacyMode ? 'privacy-blur' : ''}"
									>
										{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
									</div>

									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											requestDeleteSingle(tx);
										}}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer"
										title="Delete transaction"
										aria-label="Delete transaction"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<!-- COMPACT SPREADSHEET TABLE VIEW -->
		<div class="card-surface rounded-2xl overflow-hidden">
			<div class="overflow-x-auto">
				<table class="w-full text-left border-collapse">
					<thead>
						<tr class="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-900/60">
							<th class="py-3 px-4 w-10">
								<input
									type="checkbox"
									checked={allVisibleSelected}
									onchange={toggleSelectAll}
									class="rounded border-slate-700 cursor-pointer"
								/>
							</th>
							<th class="py-3 px-3">Date</th>
							<th class="py-3 px-3">Merchant</th>
							<th class="py-3 px-3">Account</th>
							<th class="py-3 px-3">Category</th>
							<th class="py-3 px-4 text-right">Amount</th>
							<th class="py-3 px-3 text-right w-10"></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-slate-800/60 text-sm">
						{#each visibleTransactions as tx}
							{@const acc = accountsMap.get(tx.account_id)}
							{@const isSelected = selectedIds.has(tx.id)}
							<tr
								onclick={() => (inspectedTx = tx)}
								class="transition cursor-pointer {isSelected ? 'bg-emerald-500/8' : 'hover:bg-slate-900/50'}"
							>
								<td class="py-2.5 px-4" onclick={(e) => e.stopPropagation()}>
									<input
										type="checkbox"
										checked={isSelected}
										onchange={() => toggleSelect(tx.id)}
										class="rounded border-slate-700 cursor-pointer"
									/>
								</td>
								<td class="py-2.5 px-3 text-slate-400 whitespace-nowrap text-xs font-mono-num">
									{formatDate(tx.occurred_at)}
								</td>
								<td class="py-2.5 px-3 max-w-xs">
									<div class="flex items-center gap-1.5">
										<span class="font-medium text-white truncate">{tx.merchant_clean}</span>
										{#if tx.is_transfer}
											<span class="px-1.5 py-0.5 rounded bg-cyan-500/15 text-[10px] text-cyan-300">Transfer</span>
										{/if}
										{#if tx.tags?.includes('bank-of-georgia')}
											<span class="px-1.5 py-0.5 rounded bg-orange-500/15 text-[10px] text-orange-300">BOG</span>
										{/if}
									</div>
									{#if tx.notes}
										<div class="text-[11px] text-slate-500 truncate">{tx.notes}</div>
									{/if}
								</td>
								<td class="py-2.5 px-3 text-xs text-slate-300 whitespace-nowrap">
									{acc?.name ?? '—'}
								</td>
								<td class="py-2.5 px-3" onclick={(e) => e.stopPropagation()}>
									<select
										value={tx.category_id ?? ''}
										onchange={(e) =>
											handleInlineCategoryChange(tx, (e.currentTarget as HTMLSelectElement).value)}
										class="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
									>
										<option value="">Uncategorized</option>
										{#each categories as cat}
											<option value={cat.id}>{cat.name}</option>
										{/each}
									</select>
								</td>
								<td
									class="py-2.5 px-4 text-right font-mono-num text-xs font-semibold whitespace-nowrap {tx.direction === 'inflow'
										? 'text-emerald-400'
										: 'text-slate-100'} {privacyMode ? 'privacy-blur' : ''}"
								>
									{tx.direction === 'inflow' ? '+' : '-'}{formatMoney(tx.amount, tx.currency)}
								</td>
								<td class="py-2.5 px-3 text-right" onclick={(e) => e.stopPropagation()}>
									<button
										type="button"
										onclick={() => requestDeleteSingle(tx)}
										class="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
										title="Delete transaction"
									>
										<Trash2 class="w-3.5 h-3.5" />
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}

	<!-- SERVER PAGINATION FOOTER -->
	{#if total > PAGE_SIZE}
		<div class="flex items-center justify-between gap-4 pt-1 text-xs text-slate-400">
			<span class="font-mono-num">Showing {pageStart}–{pageEnd} of {total}</span>
			<div class="flex items-center gap-2">
				<button
					type="button"
					disabled={!hasPrev}
					onclick={goPrevPage}
					class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 disabled:opacity-40 cursor-pointer"
				>
					<ChevronLeft class="w-3.5 h-3.5" /> Previous
				</button>
				<button
					type="button"
					disabled={!hasNext}
					onclick={goNextPage}
					class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 disabled:opacity-40 cursor-pointer"
				>
					Next <ChevronRight class="w-3.5 h-3.5" />
				</button>
			</div>
		</div>
	{/if}
</div>

<!-- 4. FLOATING MULTI-SELECT BULK ACTION BAR -->
{#if selectedSummary.count > 0}
	<div class="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 w-[calc(100%-2rem)] max-w-2xl">
		<div class="rounded-2xl bg-slate-900/95 backdrop-blur-md border border-emerald-500/40 shadow-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
			<div class="flex items-center gap-2.5 text-xs">
				<span class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono-num font-bold">
					{selectedSummary.count} selected
				</span>
				<span class="text-slate-300 font-mono-num {privacyMode ? 'privacy-blur' : ''}">
					Net {selectedSummary.net >= 0 ? '+' : ''}{formatMoney(selectedSummary.net, selectedSummary.ccy)}
				</span>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<select
					bind:value={bulkCategoryId}
					class="px-2.5 py-1.5 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
				>
					<option value="">Bulk categorize...</option>
					<option value="__none__">Clear Category (Uncategorized)</option>
					{#each categories as cat}
						<option value={cat.id}>{cat.name}</option>
					{/each}
				</select>
				<button
					type="button"
					disabled={!bulkCategoryId || bulkBusy}
					onclick={handleBulkCategorize}
					class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold cursor-pointer disabled:opacity-45"
				>
					<CheckCircle2 class="w-3.5 h-3.5" />
					{bulkBusy ? 'Applying...' : 'Apply'}
				</button>
				<button
					type="button"
					onclick={requestDeleteBulk}
					class="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/35 text-rose-300 text-xs font-semibold cursor-pointer"
				>
					<Trash2 class="w-3.5 h-3.5" /> Delete
				</button>
				<button
					type="button"
					onclick={() => (selectedIds = new Set())}
					class="p-1.5 rounded-lg text-slate-400 hover:text-white cursor-pointer"
					title="Clear selection"
					aria-label="Clear selection"
				>
					<X class="w-4 h-4" />
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- 5. TRANSACTION DETAIL & EDIT SLIDE-OVER DRAWER -->
<TransactionDetailDrawer
	transaction={inspectedTx}
	{accounts}
	{categories}
	{privacyMode}
	onClose={() => (inspectedTx = null)}
	onSaved={(updated) => {
		transactions = transactions.map((t) => (t.id === updated.id ? updated : t));
		showToast(`Updated "${updated.merchant_clean}" & recalculated balance.`);
	}}
	onRequestDelete={(tx) => requestDeleteSingle(tx)}
/>

<!-- QUICK ADD TRANSACTION MODAL -->
{#if showAddModal}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-md p-6 space-y-5 border border-slate-700/80">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-white">Add Transaction</h2>
				<button
					type="button"
					onclick={() => (showAddModal = false)}
					class="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<form onsubmit={handleCreate} class="space-y-4">
				<div class="grid grid-cols-2 p-1 rounded-xl bg-slate-950 border border-slate-800">
					<button
						type="button"
						onclick={() => (formDirection = 'outflow')}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {formDirection === 'outflow'
							? 'bg-rose-500/20 text-rose-300 border border-rose-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowUpRight class="w-3.5 h-3.5" /> Expense
					</button>
					<button
						type="button"
						onclick={() => (formDirection = 'inflow')}
						class="py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer {formDirection === 'inflow'
							? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/35'
							: 'text-slate-400 hover:text-white border border-transparent'}"
					>
						<ArrowDownRight class="w-3.5 h-3.5" /> Income
					</button>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="tx-amount" class="block text-xs font-medium text-slate-300 mb-1">Amount</label>
						<input
							id="tx-amount"
							type="number"
							step="0.01"
							min="0.01"
							required
							bind:value={formAmount}
							placeholder="0.00"
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white font-mono-num focus:outline-none focus:border-emerald-500"
						/>
					</div>
					<div>
						<label for="tx-date" class="block text-xs font-medium text-slate-300 mb-1">Date</label>
						<input
							id="tx-date"
							type="date"
							required
							bind:value={formDate}
							class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<div>
					<label for="tx-merchant" class="block text-xs font-medium text-slate-300 mb-1">Merchant / Payee</label>
					<input
						id="tx-merchant"
						type="text"
						required
						bind:value={formMerchant}
						placeholder="Yandex Go, Carrefour, Monthly Salary..."
						class="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white focus:outline-none focus:border-emerald-500"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="tx-acc" class="block text-xs font-medium text-slate-300 mb-1">Account</label>
						<select
							id="tx-acc"
							bind:value={formAccountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							{#each accounts as acc}
								<option value={acc.id}>{acc.name} ({acc.currency})</option>
							{/each}
						</select>
					</div>
					<div>
						<label for="tx-cat" class="block text-xs font-medium text-slate-300 mb-1">Category</label>
						<select
							id="tx-cat"
							bind:value={formCategoryId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							<option value="">Uncategorized</option>
							{#each categories as cat}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label for="tx-notes" class="block text-xs font-medium text-slate-300 mb-1">Notes</label>
						<input
							id="tx-notes"
							type="text"
							bind:value={formNotes}
							placeholder="Optional memo..."
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
					<div>
						<label for="tx-tags" class="block text-xs font-medium text-slate-300 mb-1">Tags (comma-separated)</label>
						<input
							id="tx-tags"
							type="text"
							bind:value={formTagsRaw}
							placeholder="work, travel..."
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						/>
					</div>
				</div>

				<label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
					<input type="checkbox" bind:checked={formIsTransfer} class="rounded border-slate-700" />
					Internal transfer between my accounts
				</label>

				{#if formIsTransfer}
					<div>
						<label for="tx-peer" class="block text-xs font-medium text-slate-300 mb-1">Destination Account</label>
						<select
							id="tx-peer"
							bind:value={formTransferAccountId}
							class="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-emerald-500"
						>
							<option value="">Select target account...</option>
							{#each accounts.filter((a) => a.id !== formAccountId) as acc}
								<option value={acc.id}>{acc.name} ({acc.currency})</option>
							{/each}
						</select>
					</div>
				{/if}

				<div class="flex items-center justify-end gap-2.5 pt-2">
					<button
						type="button"
						onclick={() => (showAddModal = false)}
						class="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={saving}
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-50"
					>
						{saving ? 'Saving...' : 'Save Transaction'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- SAFE DELETE CONFIRMATION MODAL -->
{#if deleteConfirmIds.length > 0}
	<div class="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
		<div class="card-surface rounded-2xl w-full max-w-sm p-6 space-y-4 border border-rose-500/35">
			<div class="flex items-start gap-3">
				<div class="h-10 w-10 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
					<AlertTriangle class="w-5 h-5" />
				</div>
				<div>
					<h2 class="text-base font-semibold text-white">
						Delete {deleteConfirmIds.length === 1 ? 'Transaction' : `${deleteConfirmIds.length} Transactions`}?
					</h2>
					<p class="text-xs text-slate-400 mt-0.5">
						{deleteConfirmLabel} will be permanently removed and affected account balances recalculated automatically.
					</p>
				</div>
			</div>

			<div class="flex items-center justify-end gap-2 pt-1">
				<button
					type="button"
					disabled={deleting}
					onclick={() => (deleteConfirmIds = [])}
					class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
				>
					Cancel
				</button>
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
